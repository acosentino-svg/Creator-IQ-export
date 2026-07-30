"""Deep activation analytics: funnel stages, cohorts, trends, struggle
segments, and outreach priority scoring.

Consumed by dashboard pages and the chat assistant.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from creatoriq_dashboard.metrics import UTC_NOW, _to_datetime_utc

FUNNEL_STEPS = [
    ("enrolled", "Enrolled in program"),
    ("ever_linked", "Ever created a link"),
    ("ever_posted", "Ever published a post"),
    ("ever_activated", "Ever activated (link or post)"),
    ("fully_activated", "Fully activated (link AND post)"),
    ("activated_within_14d", "Activated within 14 days of joining"),
    ("activated_within_30d", "Activated within 30 days of joining"),
    ("repeat_active", "Repeat active (2+ actions, active recently)"),
]

STRUGGLE_SEGMENT_META: dict[str, dict] = {
    "posted_no_link": {
        "label": "Posted but never linked",
        "priority": 1,
        "intervention": "Commission miss — send 'you're leaving money on the table' email with one-click link setup.",
        "email_template": "missing_commission",
    },
    "linked_no_post": {
        "label": "Linked but never posted",
        "priority": 2,
        "intervention": "Content block — send a 'what to post this week' pack with captions and product picks.",
        "email_template": "what_to_post",
    },
    "ghost": {
        "label": "Ghost (joined 14+ days, zero activity)",
        "priority": 3,
        "intervention": "Onboarding failure — simplify first step to 'create one link' with a 2-minute video.",
        "email_template": "first_link_nudge",
    },
    "email_clicked_stuck": {
        "label": "Clicked email recently, still no link",
        "priority": 4,
        "intervention": "High intent, blocked — personal outreach or live office hours invite.",
        "email_template": "personal_followup",
    },
    "email_opened_stuck": {
        "label": "Opens emails but no activity",
        "priority": 5,
        "intervention": "Engaged but passive — stronger CTA, limited-time bonus, or social proof.",
        "email_template": "stronger_cta",
    },
    "one_and_done": {
        "label": "One-and-done (activated once, gone quiet)",
        "priority": 6,
        "intervention": "Re-activation — show what they earned (or could earn) from a second post.",
        "email_template": "second_post_nudge",
    },
    "new_monitor": {
        "label": "New joiner (<14 days, no activity yet)",
        "priority": 7,
        "intervention": "Monitor — wait until day 7, then send first-link reminder if still idle.",
        "email_template": "wait",
    },
    "cooling": {
        "label": "Cooling off (was active, quiet 30–60 days)",
        "priority": 8,
        "intervention": "Prevent churn — trending products email or 'creators like you posted X'.",
        "email_template": "trending_content",
    },
    "went_dark": {
        "label": "Went dark (posted & linked, now quiet)",
        "priority": 9,
        "intervention": "Win-back campaign — new incentive, program updates, or fit reassessment.",
        "email_template": "win_back",
    },
}


@dataclass
class ActivationContext:
    summary: pd.DataFrame
    classified: pd.DataFrame
    active_days: int = 30
    went_dark_days: int = 60
    ghost_days: int = 14


def enrich_activation_fields(summary: pd.DataFrame) -> pd.DataFrame:
    """Add boolean flags and timing fields used across analytics + chat."""
    df = summary.copy()
    now = UTC_NOW()

    if "joined_date" not in df.columns:
        df["joined_date"] = pd.NaT
    df["joined_date"] = pd.to_datetime(df["joined_date"], utc=True, errors="coerce")

    for col in ("first_post", "last_post", "first_link", "last_link", "first_activity_at", "last_activity_at"):
        if col not in df.columns:
            df[col] = pd.NaT
        df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")

    df["days_since_join"] = (now - df["joined_date"]).dt.days
    df["has_ever_posted"] = df["first_post"].notna()
    df["has_ever_linked"] = df["first_link"].notna()
    df["has_ever_activated"] = df["has_ever_posted"] | df["has_ever_linked"]
    df["is_fully_activated"] = df["has_ever_posted"] & df["has_ever_linked"]

    df["days_join_to_first_link"] = (df["first_link"] - df["joined_date"]).dt.days
    df["days_join_to_first_post"] = (df["first_post"] - df["joined_date"]).dt.days
    df["days_join_to_first_activity"] = (df["first_activity_at"] - df["joined_date"]).dt.days

    df["activated_within_14d"] = df["days_join_to_first_activity"].between(0, 14, inclusive="both")
    df["activated_within_30d"] = df["days_join_to_first_activity"].between(0, 30, inclusive="both")

    event_count = (
        df.get("lifetime_post_count", 0).fillna(0).astype(int)
        + df.get("lifetime_link_count", 0).fillna(0).astype(int)
    )
    df["total_activity_events"] = event_count
    df["is_repeat_creator"] = event_count >= 2

    return df


def compute_activation_funnel(enriched: pd.DataFrame) -> pd.DataFrame:
    """Cumulative funnel with step counts and conversion rates."""
    total = len(enriched)
    if total == 0:
        return pd.DataFrame(columns=["step_id", "step_label", "count", "pct_of_enrolled", "pct_of_previous"])

    def step(step_id: str, label: str, mask: pd.Series) -> dict:
        count = int(mask.sum())
        return {"step_id": step_id, "step_label": label, "count": count}

    repeat_mask = enriched["is_repeat_creator"] & enriched["has_ever_activated"]
    if "days_since_last_activity" in enriched.columns:
        repeat_mask = repeat_mask & (enriched["days_since_last_activity"] <= 30)

    steps = [
        step("enrolled", "Enrolled in program", pd.Series(True, index=enriched.index)),
        step("ever_linked", "Ever created a link", enriched["has_ever_linked"]),
        step("ever_posted", "Ever published a post", enriched["has_ever_posted"]),
        step("ever_activated", "Ever activated (link or post)", enriched["has_ever_activated"]),
        step("fully_activated", "Fully activated (link AND post)", enriched["is_fully_activated"]),
        step("activated_within_14d", "Activated within 14 days of joining", enriched["activated_within_14d"]),
        step("activated_within_30d", "Activated within 30 days of joining", enriched["activated_within_30d"]),
        step("repeat_active", "Repeat active (2+ actions, active recently)", repeat_mask),
    ]

    out = pd.DataFrame(steps)
    out["pct_of_enrolled"] = (out["count"] / total * 100).round(1)
    prev = total
    conversions = []
    for count in out["count"]:
        conversions.append(round(count / prev * 100, 1) if prev > 0 else 0.0)
        prev = count if count > 0 else prev
    out["pct_of_previous"] = conversions
    return out


def compute_extended_kpis(enriched: pd.DataFrame, classified: pd.DataFrame) -> dict:
    total = len(enriched)
    if total == 0:
        return {}

    ever_activated = int(enriched["has_ever_activated"].sum())
    fully = int(enriched["is_fully_activated"].sum())
    within_14 = int(enriched["activated_within_14d"].sum())
    within_30 = int(enriched["activated_within_30d"].sum())

    eligible_14 = int((enriched["days_since_join"] >= 14).sum())
    eligible_30 = int((enriched["days_since_join"] >= 30).sum())

    mature = enriched[enriched["days_since_join"] >= 14]
    ghost_count = int((~mature["has_ever_activated"]).sum()) if not mature.empty else 0

    return {
        "total_creators": total,
        "ever_activated_count": ever_activated,
        "ever_activated_rate": round(ever_activated / total * 100, 1),
        "fully_activated_count": fully,
        "fully_activated_rate": round(fully / total * 100, 1),
        "linked_only_count": int((enriched["has_ever_linked"] & ~enriched["has_ever_posted"]).sum()),
        "posted_only_count": int((enriched["has_ever_posted"] & ~enriched["has_ever_linked"]).sum()),
        "activated_within_14d_count": within_14,
        "activated_within_14d_rate": round(within_14 / eligible_14 * 100, 1) if eligible_14 else 0.0,
        "activated_within_30d_count": within_30,
        "activated_within_30d_rate": round(within_30 / eligible_30 * 100, 1) if eligible_30 else 0.0,
        "ghost_count": ghost_count,
        "ghost_rate": round(ghost_count / len(mature) * 100, 1) if len(mature) else 0.0,
        "median_days_to_first_activity": _median(enriched["days_join_to_first_activity"]),
        "median_days_join_to_link": _median(enriched["days_join_to_first_link"]),
        "median_days_join_to_post": _median(enriched["days_join_to_first_post"]),
        "active_creators": int((classified["activation_state"] == "Active").sum()) if not classified.empty else 0,
        "never_activated_creators": int((classified["activation_state"] == "Never Activated").sum())
        if not classified.empty
        else 0,
        "went_dark_creators": int((classified["activation_state"] == "Went Dark").sum()) if not classified.empty else 0,
    }


def _median(series: pd.Series) -> float | None:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return None
    return round(float(clean.median()), 1)


def compute_cohort_activation(enriched: pd.DataFrame) -> pd.DataFrame:
    """Per join-month cohort: size, ever-activated %, 14d/30d activation %."""
    df = enriched.dropna(subset=["joined_date"]).copy()
    if df.empty:
        return pd.DataFrame(
            columns=[
                "cohort_month",
                "cohort_size",
                "ever_activated_pct",
                "activated_14d_pct",
                "activated_30d_pct",
                "median_days_to_activate",
            ]
        )

    df["cohort_month"] = df["joined_date"].dt.to_period("M").astype(str)
    rows = []
    for cohort, group in df.groupby("cohort_month", sort=True):
        size = len(group)
        ever_pct = group["has_ever_activated"].mean() * 100
        eligible_14 = group[group["days_since_join"] >= 14]
        eligible_30 = group[group["days_since_join"] >= 30]
        rows.append(
            {
                "cohort_month": cohort,
                "cohort_size": size,
                "ever_activated_pct": round(ever_pct, 1),
                "activated_14d_pct": round(eligible_14["activated_within_14d"].mean() * 100, 1)
                if len(eligible_14)
                else None,
                "activated_30d_pct": round(eligible_30["activated_within_30d"].mean() * 100, 1)
                if len(eligible_30)
                else None,
                "median_days_to_activate": _median(group["days_join_to_first_activity"]),
            }
        )
    return pd.DataFrame(rows)


def compute_activation_trends(enriched: pd.DataFrame, posts: pd.DataFrame, links: pd.DataFrame) -> pd.DataFrame:
    """Weekly enrollments, first-time activations, and rolling activation rate."""
    frames = []

    if not enriched.empty and "joined_date" in enriched.columns:
        joins = enriched.dropna(subset=["joined_date"]).copy()
        joins["week"] = joins["joined_date"].dt.to_period("W").astype(str)
        join_counts = joins.groupby("week").size().rename("new_enrollments").reset_index()
        frames.append(join_counts)

    activation_rows = []
    if not enriched.empty:
        activated = enriched[enriched["has_ever_activated"] & enriched["first_activity_at"].notna()]
        for _, row in activated.iterrows():
            activation_rows.append(
                {"week": str(pd.Timestamp(row["first_activity_at"]).to_period("W"))}
            )
    if activation_rows:
        act = pd.DataFrame(activation_rows)
        act_counts = act.groupby("week").size().rename("first_activations").reset_index()
        frames.append(act_counts)

    if not frames:
        return pd.DataFrame(columns=["week", "new_enrollments", "first_activations", "activation_rate"])

    trend = frames[0]
    for extra in frames[1:]:
        trend = trend.merge(extra, on="week", how="outer")
    trend = trend.fillna(0)
    for col in ("new_enrollments", "first_activations"):
        if col not in trend.columns:
            trend[col] = 0
        trend[col] = trend[col].astype(int)
    trend["activation_rate"] = np.where(
        trend["new_enrollments"] > 0,
        (trend["first_activations"] / trend["new_enrollments"] * 100).round(1),
        0.0,
    )
    return trend.sort_values("week").reset_index(drop=True)


def assign_struggle_segment(row: pd.Series, ghost_days: int = 14, active_days: int = 30, went_dark_days: int = 60) -> str:
    """Mutually exclusive outreach segment (first match wins)."""
    has_post = bool(row.get("has_ever_posted"))
    has_link = bool(row.get("has_ever_linked"))
    days_join = row.get("days_since_join", 999)
    days_since_activity = row.get("days_since_last_activity", np.nan)
    days_since_open = row.get("days_since_last_email_open", np.nan)
    days_since_click = row.get("days_since_last_email_click", np.nan)
    state = row.get("activation_state", "")

    if has_post and not has_link:
        return "posted_no_link"
    if has_link and not has_post:
        return "linked_no_post"
    if not has_post and not has_link:
        if pd.notna(days_join) and days_join < ghost_days:
            return "new_monitor"
        return "ghost"
    if pd.notna(days_since_click) and days_since_click <= 30 and not has_link:
        return "email_clicked_stuck"
    if pd.notna(days_since_open) and days_since_open <= 30 and not has_post and not has_link:
        return "email_opened_stuck"
    if row.get("total_activity_events", 0) <= 1 and pd.notna(days_since_activity) and days_since_activity >= went_dark_days:
        return "one_and_done"
    if state == "Inactive":
        return "cooling"
    if state == "Went Dark":
        return "went_dark"
    return "healthy"


def compute_struggle_segments(
    enriched: pd.DataFrame,
    classified: pd.DataFrame,
    ghost_days: int = 14,
    active_days: int = 30,
    went_dark_days: int = 60,
) -> pd.DataFrame:
    """Segment summary with counts, priority, and recommended intervention."""
    merged = enriched.merge(
        classified[["creator_id", "activation_state"]],
        on="creator_id",
        how="left",
        suffixes=("", "_cls"),
    )
    merged["struggle_segment"] = merged.apply(
        lambda row: assign_struggle_segment(
            row, ghost_days=ghost_days, active_days=active_days, went_dark_days=went_dark_days
        ),
        axis=1,
    )

    rows = []
    for seg_id, meta in STRUGGLE_SEGMENT_META.items():
        members = merged[merged["struggle_segment"] == seg_id]
        rows.append(
            {
                "segment_id": seg_id,
                "segment_label": meta["label"],
                "creator_count": len(members),
                "priority": meta["priority"],
                "recommended_intervention": meta["intervention"],
                "email_template": meta["email_template"],
            }
        )
    healthy = merged[merged["struggle_segment"] == "healthy"]
    rows.append(
        {
            "segment_id": "healthy",
            "segment_label": "Healthy / active",
            "creator_count": len(healthy),
            "priority": 99,
            "recommended_intervention": "No outreach needed — consider for ambassador/champion program.",
            "email_template": "none",
        }
    )
    return pd.DataFrame(rows).sort_values("priority").reset_index(drop=True)


def build_outreach_queue(
    enriched: pd.DataFrame,
    classified: pd.DataFrame,
    ghost_days: int = 14,
    exclude_healthy: bool = True,
) -> pd.DataFrame:
    """Creator-level outreach queue sorted by segment priority."""
    merged = enriched.merge(classified[["creator_id", "activation_state"]], on="creator_id", how="left")
    merged["struggle_segment"] = merged.apply(assign_struggle_segment, axis=1)

    if exclude_healthy:
        merged = merged[merged["struggle_segment"] != "healthy"]

    meta = pd.DataFrame(
        [{"segment_id": k, **v} for k, v in STRUGGLE_SEGMENT_META.items()]
    )[["segment_id", "label", "priority", "intervention"]]
    meta = meta.rename(columns={"label": "segment_label", "intervention": "recommended_intervention"})

    queue = merged.merge(meta, left_on="struggle_segment", right_on="segment_id", how="left")
    queue = queue.sort_values(["priority", "days_since_join"], ascending=[True, False])

    display_cols = [
        c
        for c in [
            "name",
            "handle",
            "email",
            "tier",
            "struggle_segment",
            "segment_label",
            "priority",
            "days_since_join",
            "days_since_last_activity",
            "days_since_last_email_open",
            "first_link",
            "first_post",
            "recommended_intervention",
        ]
        if c in queue.columns
    ]
    return queue[display_cols].reset_index(drop=True)


def filter_first_activations(
    enriched: pd.DataFrame,
    range_start: pd.Timestamp,
    range_end: pd.Timestamp,
) -> pd.DataFrame:
    """Creators whose first-ever activity (link or post) falls in the date range."""
    df = enriched.copy()
    mask = (
        df["first_activity_at"].notna()
        & (df["first_activity_at"] >= range_start)
        & (df["first_activity_at"] <= range_end)
    )
    return df[mask].sort_values("first_activity_at", ascending=False)


def filter_first_posts(
    enriched: pd.DataFrame,
    range_start: pd.Timestamp,
    range_end: pd.Timestamp,
) -> pd.DataFrame:
    df = enriched.copy()
    mask = df["first_post"].notna() & (df["first_post"] >= range_start) & (df["first_post"] <= range_end)
    return df[mask].sort_values("first_post", ascending=False)


def filter_first_links(
    enriched: pd.DataFrame,
    range_start: pd.Timestamp,
    range_end: pd.Timestamp,
) -> pd.DataFrame:
    df = enriched.copy()
    mask = df["first_link"].notna() & (df["first_link"] >= range_start) & (df["first_link"] <= range_end)
    return df[mask].sort_values("first_link", ascending=False)


def creators_in_segment(enriched: pd.DataFrame, classified: pd.DataFrame, segment_id: str) -> pd.DataFrame:
    merged = enriched.merge(classified[["creator_id", "activation_state"]], on="creator_id", how="left")
    merged["struggle_segment"] = merged.apply(assign_struggle_segment, axis=1)
    if segment_id == "never_activated":
        return merged[~merged["has_ever_activated"]]
    if segment_id == "active":
        return merged[merged["activation_state"] == "Active"]
    if segment_id == "healthy":
        return merged[merged["struggle_segment"] == "healthy"]
    return merged[merged["struggle_segment"] == segment_id]
