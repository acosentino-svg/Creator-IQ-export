"""Business logic for the activation dashboard: creator summaries,
activation-state classification, momentum/spike scoring, went-dark
follow-up recommendations, and email engagement cross-segments.

Every function here takes plain pandas DataFrames in the normalized schema
(see README) and returns plain DataFrames/dicts, so this module can be unit
tested without any network, database, or Streamlit dependency.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

UTC_NOW = lambda: pd.Timestamp.now(tz="UTC")  # noqa: E731

DATE_RANGE_PRESETS = ["Last 7 days", "Last 30 days", "Last 60 days", "Last 90 days", "This Month", "Custom"]


def _to_datetime_utc(series: pd.Series | None) -> pd.Series:
    if series is None:
        return pd.Series(dtype="datetime64[ns, UTC]")
    return pd.to_datetime(series, utc=True, errors="coerce")


@dataclass
class RawData:
    creators: pd.DataFrame
    posts: pd.DataFrame
    links: pd.DataFrame  # trackable link *creation* events (Link Generator), not click deltas
    email_events: pd.DataFrame
    link_clicks: pd.DataFrame | None = None  # optional day-over-day click activity from post snapshots


# Backwards-compatible alias (older code/tests may still import this name).
ActivationInputs = RawData


# ---------------------------------------------------------------------------
# Date range helper (drives the global sidebar selector)
# ---------------------------------------------------------------------------


def resolve_date_range(
    preset: str,
    custom_start: pd.Timestamp | None = None,
    custom_end: pd.Timestamp | None = None,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Turn a preset label (or "Custom" + explicit dates) into a concrete
    (start, end) UTC timestamp pair, inclusive of "today".
    """
    now = UTC_NOW()
    end = now
    if preset == "Last 7 days":
        start = now - pd.Timedelta(days=7)
    elif preset == "Last 30 days":
        start = now - pd.Timedelta(days=30)
    elif preset == "Last 60 days":
        start = now - pd.Timedelta(days=60)
    elif preset == "Last 90 days":
        start = now - pd.Timedelta(days=90)
    elif preset == "This Month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif preset == "Custom":
        start = pd.Timestamp(custom_start, tz="UTC") if custom_start is not None else now - pd.Timedelta(days=30)
        end = pd.Timestamp(custom_end, tz="UTC") if custom_end is not None else now
    else:
        start = now - pd.Timedelta(days=30)
    return start, end


# ---------------------------------------------------------------------------
# Activity timelines (program-wide trend chart + spike detection)
# ---------------------------------------------------------------------------


def build_daily_activity(df: pd.DataFrame, date_col: str, label: str, value_col: str | None = None) -> pd.DataFrame:
    """Collapse a raw event/post table into a daily series.

    By default counts rows per day (one row = one discrete event). Pass
    `value_col` to sum a numeric column per day instead (used when a signal
    is a delta/volume rather than a discrete per-row event).

    Returns columns: date, activity_type, count
    """
    if df.empty or date_col not in df.columns:
        return pd.DataFrame(columns=["date", "activity_type", "count"])
    dates = _to_datetime_utc(df[date_col]).dt.date
    if value_col and value_col in df.columns:
        values = pd.to_numeric(df[value_col], errors="coerce").fillna(0)
        counts = values.groupby(dates).sum().sort_index()
    else:
        counts = dates.value_counts().sort_index()
    out = counts.rename_axis("date").reset_index(name="count")
    out["activity_type"] = label
    return out[["date", "activity_type", "count"]]


def combine_activity_timelines(*timelines: pd.DataFrame) -> pd.DataFrame:
    frames = [t for t in timelines if not t.empty]
    if not frames:
        return pd.DataFrame(columns=["date", "activity_type", "count"])
    combined = pd.concat(frames, ignore_index=True)
    return combined.sort_values(["activity_type", "date"]).reset_index(drop=True)


def detect_spikes(
    timeline: pd.DataFrame,
    baseline_window_days: int = 28,
    min_count_for_spike: int = 3,
    z_score_threshold: float = 2.0,
) -> pd.DataFrame:
    """Flag daily spikes per activity_type using a rolling z-score.

    A day is a "spike" when its count is at least `min_count_for_spike` AND
    its z-score vs. the trailing `baseline_window_days` (excluding today)
    exceeds `z_score_threshold`.
    """
    if timeline.empty:
        return timeline.assign(rolling_mean=[], rolling_std=[], z_score=[], is_spike=[])

    results = []
    for activity_type, group in timeline.groupby("activity_type"):
        g = group.sort_values("date").copy()
        g["date"] = pd.to_datetime(g["date"])
        g = g.set_index("date").asfreq("D", fill_value=0).reset_index()
        g["activity_type"] = activity_type

        rolling = g["count"].rolling(window=baseline_window_days, min_periods=5)
        g["rolling_mean"] = rolling.mean().shift(1)
        g["rolling_std"] = rolling.std(ddof=0).shift(1)
        # A near-zero baseline std (e.g. a quiet program with a constant trickle of
        # activity) shouldn't make the z-score explode to NaN/undefined -- floor it
        # so a genuine jump still reads as a large, finite z-score.
        effective_std = g["rolling_std"].clip(lower=0.5)
        g["z_score"] = (g["count"] - g["rolling_mean"]) / effective_std
        g["z_score"] = g["z_score"].replace([np.inf, -np.inf], np.nan).fillna(0)
        g["is_spike"] = (g["count"] >= min_count_for_spike) & (g["z_score"] >= z_score_threshold)
        results.append(g)

    out = pd.concat(results, ignore_index=True)
    out["date"] = out["date"].dt.date
    return out.sort_values(["activity_type", "date"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Activity events (unified posts + links, used for gap/momentum analysis)
# ---------------------------------------------------------------------------


def build_activity_events(posts: pd.DataFrame, links: pd.DataFrame) -> pd.DataFrame:
    """One row per creator activity (a post or a link creation):
    creator_id, event_type ("post"/"link"), event_date.
    """
    frames = []
    if not posts.empty and "posted_at" in posts.columns:
        p = posts[["creator_id", "posted_at"]].rename(columns={"posted_at": "event_date"}).copy()
        p["event_type"] = "post"
        frames.append(p)
    if not links.empty and "created_at" in links.columns:
        l = links[["creator_id", "created_at"]].rename(columns={"created_at": "event_date"}).copy()  # noqa: E741
        l["event_type"] = "link"
        frames.append(l)
    if not frames:
        return pd.DataFrame(columns=["creator_id", "event_type", "event_date"])
    events = pd.concat(frames, ignore_index=True)
    events["event_date"] = _to_datetime_utc(events["event_date"])
    return events.dropna(subset=["event_date"]).sort_values(["creator_id", "event_date"]).reset_index(drop=True)


def _compute_gap_stats(events: pd.DataFrame) -> pd.DataFrame:
    """Per creator: the longest gap (in days) between two consecutive
    activities, and how many activities they have in total. Used to tell
    "Consistently Active" (never had a long lapse) apart from "Reactivated"
    (had a long lapse, but is active again now).
    """
    if events.empty:
        return pd.DataFrame(columns=["creator_id", "max_gap_days", "activity_event_count"])

    rows = []
    for creator_id, group in events.groupby("creator_id"):
        dates = group["event_date"].sort_values()
        if len(dates) <= 1:
            max_gap = 0.0
        else:
            diffs = dates.diff().dropna().dt.total_seconds() / 86400.0
            max_gap = float(diffs.max()) if not diffs.empty else 0.0
        rows.append({"creator_id": creator_id, "max_gap_days": max_gap, "activity_event_count": len(dates)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Creator summary (the backbone of the Creator Activity + Creator Profile pages)
# ---------------------------------------------------------------------------


def build_creator_summary(raw: RawData, range_start: pd.Timestamp, range_end: pd.Timestamp) -> pd.DataFrame:
    """One row per creator with every field the Creator Activity page needs:
    identity, tags/status, first/last post & link dates, lifetime counts,
    in-range counts, and email send/open/click recency.
    """
    creators = raw.creators.copy()
    posts = raw.posts.copy()
    links = raw.links.copy()
    emails = raw.email_events.copy()

    if "joined_date" not in creators.columns:
        creators["joined_date"] = pd.NaT
    creators["joined_date"] = pd.to_datetime(creators["joined_date"], utc=True, errors="coerce")

    if not posts.empty:
        posts["posted_at"] = _to_datetime_utc(posts["posted_at"])
    if not links.empty:
        links["created_at"] = _to_datetime_utc(links["created_at"])
    if not emails.empty:
        emails["sent_at"] = _to_datetime_utc(emails.get("sent_at"))
        emails["opened_at"] = _to_datetime_utc(emails.get("opened_at"))
        emails["clicked_at"] = _to_datetime_utc(emails.get("clicked_at"))

    def first_last_count(df: pd.DataFrame, date_col: str, prefix: str) -> pd.DataFrame:
        cols = ["creator_id", f"first_{prefix}", f"last_{prefix}", f"lifetime_{prefix}_count"]
        if df.empty or date_col not in df.columns:
            return pd.DataFrame(columns=cols)
        out = df.groupby("creator_id")[date_col].agg(["min", "max", "count"]).reset_index()
        out.columns = cols
        return out

    def count_in_range(df: pd.DataFrame, date_col: str, out_col: str) -> pd.DataFrame:
        if df.empty or date_col not in df.columns:
            return pd.DataFrame(columns=["creator_id", out_col])
        mask = (df[date_col] >= range_start) & (df[date_col] <= range_end)
        return df.loc[mask].groupby("creator_id").size().rename(out_col).reset_index()

    post_agg = first_last_count(posts, "posted_at", "post")
    link_agg = first_last_count(links, "created_at", "link")
    posts_in_range = count_in_range(posts, "posted_at", "posts_in_range")
    links_in_range = count_in_range(links, "created_at", "links_in_range")

    if not emails.empty:
        email_agg = (
            emails.groupby("creator_id")
            .agg(
                last_email_sent=("sent_at", "max"),
                last_email_opened=("opened_at", "max"),
                last_email_clicked=("clicked_at", "max"),
                emails_sent_total=("sent_at", "count"),
            )
            .reset_index()
        )
    else:
        email_agg = pd.DataFrame(
            columns=["creator_id", "last_email_sent", "last_email_opened", "last_email_clicked", "emails_sent_total"]
        )

    summary = creators.copy()
    for extra in (post_agg, link_agg, posts_in_range, links_in_range, email_agg):
        summary = summary.merge(extra, on="creator_id", how="left")

    date_cols = [
        "first_post",
        "last_post",
        "first_link",
        "last_link",
        "last_email_sent",
        "last_email_opened",
        "last_email_clicked",
    ]
    for col in date_cols:
        if col not in summary.columns:
            summary[col] = pd.NaT
        # Merging in an empty extra frame can leave an all-NaN column as
        # float64/object instead of datetime64 -- force it so later max()/
        # subtraction across columns doesn't hit a dtype mismatch.
        summary[col] = pd.to_datetime(summary[col], utc=True, errors="coerce")

    count_cols = ["lifetime_post_count", "lifetime_link_count", "posts_in_range", "links_in_range", "emails_sent_total"]
    for col in count_cols:
        if col not in summary.columns:
            summary[col] = 0
        summary[col] = pd.to_numeric(summary[col], errors="coerce").fillna(0).astype(int)

    now = UTC_NOW()
    summary["days_since_last_post"] = (now - summary["last_post"]).dt.days
    summary["days_since_last_link"] = (now - summary["last_link"]).dt.days
    summary["days_since_last_email_open"] = (now - summary["last_email_opened"]).dt.days
    summary["days_since_last_email_click"] = (now - summary["last_email_clicked"]).dt.days

    summary["last_activity_at"] = summary[["last_post", "last_link"]].max(axis=1)
    summary["first_activity_at"] = summary[["first_post", "first_link"]].min(axis=1)
    summary["days_since_last_activity"] = (now - summary["last_activity_at"]).dt.days

    return summary


# ---------------------------------------------------------------------------
# Activation-state classification (drives the Overview KPI cards)
# ---------------------------------------------------------------------------


def classify_creators(
    summary: pd.DataFrame,
    activity_events: pd.DataFrame,
    active_days: int,
    went_dark_days: int,
    range_start: pd.Timestamp,
    range_end: pd.Timestamp,
    consistently_active_min_events: int = 3,
) -> pd.DataFrame:
    """Adds `activation_state` (one of: Never Activated, Active, Inactive,
    Went Dark) plus three boolean flags that can co-occur with "Active":
    `is_newly_activated`, `is_reactivated`, `is_consistently_active`.
    """
    df = summary.copy()

    def primary_state(row) -> str:
        if pd.isna(row["last_activity_at"]):
            return "Never Activated"
        days = row["days_since_last_activity"]
        if days <= active_days:
            return "Active"
        if days <= went_dark_days:
            return "Inactive"
        return "Went Dark"

    df["activation_state"] = df.apply(primary_state, axis=1)

    gap_stats = _compute_gap_stats(activity_events)
    df = df.merge(gap_stats, on="creator_id", how="left")
    df["max_gap_days"] = df["max_gap_days"].fillna(0.0)
    df["activity_event_count"] = df["activity_event_count"].fillna(0).astype(int)

    is_active = df["activation_state"] == "Active"
    df["is_newly_activated"] = (
        is_active
        & df["first_activity_at"].notna()
        & (df["first_activity_at"] >= range_start)
        & (df["first_activity_at"] <= range_end)
    )
    df["is_reactivated"] = is_active & (df["max_gap_days"] > went_dark_days) & ~df["is_newly_activated"]
    df["is_consistently_active"] = (
        is_active
        & (df["max_gap_days"] <= went_dark_days)
        & (df["activity_event_count"] >= consistently_active_min_events)
        & ~df["is_newly_activated"]
    )

    return df


def compute_kpis(classified: pd.DataFrame, posts_in_range_total: int, links_in_range_total: int) -> dict:
    counts = classified["activation_state"].value_counts()
    return {
        "total_creators": len(classified),
        "active_creators": int(counts.get("Active", 0)),
        "inactive_creators": int(counts.get("Inactive", 0)),
        "never_activated_creators": int(counts.get("Never Activated", 0)),
        "went_dark_creators": int(counts.get("Went Dark", 0)),
        "newly_activated_creators": int(classified["is_newly_activated"].sum()) if not classified.empty else 0,
        "reactivated_creators": int(classified["is_reactivated"].sum()) if not classified.empty else 0,
        "consistently_active_creators": int(classified["is_consistently_active"].sum()) if not classified.empty else 0,
        "total_posts_in_range": posts_in_range_total,
        "total_links_in_range": links_in_range_total,
    }


def compute_data_quality(raw: RawData, summary: pd.DataFrame, *, is_live: bool) -> dict:
    """Diagnostics for live-mode gaps (posts vs enrollment, link-creation coverage)."""
    enrolled = len(raw.creators)
    posts_in_cache = len(raw.posts)
    unique_posters_in_cache = int(raw.posts["creator_id"].nunique()) if not raw.posts.empty else 0
    creators_with_posts = int(summary["first_post"].notna().sum()) if not summary.empty else 0
    creators_with_links = int(summary["first_link"].notna().sum()) if not summary.empty else 0
    posted_without_link = (
        int((summary["first_post"].notna() & summary["first_link"].isna()).sum()) if not summary.empty else 0
    )
    link_creation_rows = len(raw.links) if raw.links is not None and not raw.links.empty else 0
    link_click_rows = len(raw.link_clicks) if raw.link_clicks is not None and not raw.link_clicks.empty else 0
    post_join_rate = (
        round(creators_with_posts / max(unique_posters_in_cache, 1) * 100, 1) if unique_posters_in_cache else None
    )
    return {
        "enrolled": enrolled,
        "posts_in_cache": posts_in_cache,
        "unique_posters_in_cache": unique_posters_in_cache,
        "creators_with_posts": creators_with_posts,
        "creators_with_link_creations": creators_with_links,
        "posted_without_link": posted_without_link,
        "link_creation_rows": link_creation_rows,
        "link_click_rows": link_click_rows,
        "post_join_rate_pct": post_join_rate,
        "link_creations_unavailable": is_live and link_creation_rows == 0,
        "posts_likely_incomplete": is_live and enrolled > 0 and creators_with_posts < enrolled * 0.01,
    }


# ---------------------------------------------------------------------------
# New Activations page
# ---------------------------------------------------------------------------


def compute_new_activations(summary: pd.DataFrame, range_start: pd.Timestamp, range_end: pd.Timestamp) -> dict:
    df = summary.copy()
    df["days_join_to_first_link"] = (df["first_link"] - df["joined_date"]).dt.days
    df["days_join_to_first_post"] = (df["first_post"] - df["joined_date"]).dt.days
    df["days_first_link_to_first_post"] = (df["first_post"] - df["first_link"]).dt.days

    def in_range(col: str) -> pd.Series:
        return df[col].notna() & (df[col] >= range_start) & (df[col] <= range_end)

    first_time_posters = df[in_range("first_post")].copy()
    first_time_linkers = df[in_range("first_link")].copy()
    linked_no_post = df[df["first_link"].notna() & df["first_post"].isna()].copy()

    return {
        "first_time_posters": first_time_posters,
        "first_time_linkers": first_time_linkers,
        "linked_no_post": linked_no_post,
        "all_with_day_calcs": df,
    }


# ---------------------------------------------------------------------------
# Momentum page ("Spikes This Week")
# ---------------------------------------------------------------------------


def compute_momentum(
    raw: RawData,
    recent_days: int = 7,
    baseline_days: int = 28,
    min_count_for_spike: int = 2,
    spike_percentage_threshold: float = 50.0,
) -> pd.DataFrame:
    """Per-creator table of creators whose recent posting/link-creation
    volume is significantly above their own historical average.
    """
    now = UTC_NOW()
    recent_start = now - pd.Timedelta(days=recent_days)
    baseline_start = recent_start - pd.Timedelta(days=baseline_days)

    posts = raw.posts.copy()
    links = raw.links.copy()
    if not posts.empty:
        posts["posted_at"] = _to_datetime_utc(posts["posted_at"])
    if not links.empty:
        links["created_at"] = _to_datetime_utc(links["created_at"])

    def count_in_window(df: pd.DataFrame, date_col: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
        if df.empty or date_col not in df.columns:
            return pd.Series(dtype=float)
        mask = (df[date_col] >= start) & (df[date_col] < end)
        return df.loc[mask].groupby("creator_id").size().astype(float)

    recent_posts = count_in_window(posts, "posted_at", recent_start, now)
    recent_links = count_in_window(links, "created_at", recent_start, now)
    baseline_posts = count_in_window(posts, "posted_at", baseline_start, recent_start)
    baseline_links = count_in_window(links, "created_at", baseline_start, recent_start)

    all_ids = sorted(set(recent_posts.index) | set(recent_links.index) | set(baseline_posts.index) | set(baseline_links.index))
    columns = [
        "creator_id",
        "posts_this_week",
        "links_this_week",
        "activity_score",
        "historical_average",
        "spike_pct",
        "most_recent_activity",
    ]
    if not all_ids:
        return pd.DataFrame(columns=columns)

    result = pd.DataFrame({"creator_id": all_ids})
    result["posts_this_week"] = result["creator_id"].map(recent_posts).fillna(0).astype(int)
    result["links_this_week"] = result["creator_id"].map(recent_links).fillna(0).astype(int)
    result["activity_score"] = result["posts_this_week"] + result["links_this_week"]

    baseline_total = baseline_posts.reindex(all_ids).fillna(0) + baseline_links.reindex(all_ids).fillna(0)
    baseline_avg = (baseline_total * (recent_days / baseline_days)).round(2)
    result["historical_average"] = result["creator_id"].map(baseline_avg.to_dict()).fillna(0.0)

    def spike_pct(row) -> float:
        if row["historical_average"] <= 0:
            return 100.0 if row["activity_score"] > 0 else 0.0
        return round((row["activity_score"] - row["historical_average"]) / row["historical_average"] * 100, 1)

    result["spike_pct"] = result.apply(spike_pct, axis=1)

    last_post = posts.groupby("creator_id")["posted_at"].max() if not posts.empty else pd.Series(dtype="datetime64[ns, UTC]")
    last_link = links.groupby("creator_id")["created_at"].max() if not links.empty else pd.Series(dtype="datetime64[ns, UTC]")
    combined_last = pd.concat([last_post.rename("a"), last_link.rename("b")], axis=1).max(axis=1)
    result["most_recent_activity"] = pd.to_datetime(
        result["creator_id"].map(combined_last.to_dict()), utc=True, errors="coerce"
    )

    result = result[result["activity_score"] >= min_count_for_spike]
    result = result[result["spike_pct"] >= spike_percentage_threshold]
    return result.sort_values("spike_pct", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Went Dark page
# ---------------------------------------------------------------------------


def compute_went_dark(classified: pd.DataFrame) -> pd.DataFrame:
    df = classified[classified["activation_state"] == "Went Dark"].copy()
    if df.empty:
        df["recommended_action"] = []
        return df

    def recommend(row) -> str:
        click_days = row.get("days_since_last_email_click")
        open_days = row.get("days_since_last_email_open")
        if pd.notna(click_days) and click_days <= 30:
            return "Clicked an email recently -- try a personal outreach call, they're still paying attention."
        if pd.notna(open_days) and open_days <= 45:
            return "Opens emails but hasn't acted -- send a stronger CTA or a limited-time incentive."
        if pd.isna(row["last_email_opened"]):
            return "Not opening email at all -- try SMS/DM or a different outreach channel entirely."
        return "Gone quiet everywhere -- send a re-engagement email or reassess fit for the program."

    df["recommended_action"] = df.apply(recommend, axis=1)
    return df.sort_values("days_since_last_activity", ascending=False)


# ---------------------------------------------------------------------------
# Email Engagement page
# ---------------------------------------------------------------------------


def compute_email_segments(summary: pd.DataFrame) -> dict[str, pd.DataFrame]:
    clicked_no_link = summary[summary["last_email_clicked"].notna() & summary["first_link"].isna()]
    linked_no_post = summary[summary["first_link"].notna() & summary["first_post"].isna()]
    never_opened = summary[summary["last_email_opened"].isna() & (summary["emails_sent_total"] > 0)]
    return {
        "clicked_no_link": clicked_no_link,
        "linked_no_post": linked_no_post,
        "never_opened": never_opened,
    }
