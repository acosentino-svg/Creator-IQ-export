"""Business logic for the activation dashboard: activity timelines, spike
detection, activation scoring/segmentation, and email engagement.

Every function here takes plain pandas DataFrames in the normalized schema
(see README / config/field_mappings.yaml) and settings loaded from
config/settings.yaml, so this module can be unit tested without any network
or database access.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import Settings

UTC_NOW = lambda: pd.Timestamp.now(tz="UTC")  # noqa: E731


def _to_datetime_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, errors="coerce")


# ---------------------------------------------------------------------------
# Activity timelines + spike detection
# ---------------------------------------------------------------------------


def build_daily_activity(df: pd.DataFrame, date_col: str, label: str) -> pd.DataFrame:
    """Collapse a raw event/post table into a daily count series.

    Returns columns: date, activity_type, count
    """
    if df.empty or date_col not in df.columns:
        return pd.DataFrame(columns=["date", "activity_type", "count"])
    dates = _to_datetime_utc(df[date_col]).dt.date
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
# Per-creator last-activity + activation segmentation
# ---------------------------------------------------------------------------


@dataclass
class ActivationInputs:
    creators: pd.DataFrame
    posts: pd.DataFrame
    links: pd.DataFrame
    email_events: pd.DataFrame


def compute_last_activity(inputs: ActivationInputs) -> pd.DataFrame:
    """Per creator: last post date, last link-click date, last email open
    date, and the max of all three ("last active at").
    """
    creators = inputs.creators[["creator_id", "name", "tier", "status", "joined_date"]].copy()

    def last_by(df: pd.DataFrame, date_col: str, out_col: str) -> pd.DataFrame:
        if df.empty or date_col not in df.columns or "creator_id" not in df.columns:
            return pd.DataFrame(columns=["creator_id", out_col])
        d = df.copy()
        d[date_col] = _to_datetime_utc(d[date_col])
        agg = d.groupby("creator_id")[date_col].max().reset_index()
        return agg.rename(columns={date_col: out_col})

    last_post = last_by(inputs.posts, "posted_at", "last_post_at")
    last_link = last_by(inputs.links, "clicked_at", "last_link_click_at")
    last_open = last_by(inputs.email_events.dropna(subset=["opened_at"]) if not inputs.email_events.empty else inputs.email_events, "opened_at", "last_email_open_at")

    post_counts = (
        inputs.posts.groupby("creator_id").size().rename("post_count_all_time").reset_index()
        if not inputs.posts.empty
        else pd.DataFrame(columns=["creator_id", "post_count_all_time"])
    )
    link_counts = (
        inputs.links.groupby("creator_id").size().rename("link_click_count_all_time").reset_index()
        if not inputs.links.empty
        else pd.DataFrame(columns=["creator_id", "link_click_count_all_time"])
    )

    merged = creators
    for extra in (last_post, last_link, last_open, post_counts, link_counts):
        merged = merged.merge(extra, on="creator_id", how="left")

    for col in ("last_post_at", "last_link_click_at", "last_email_open_at"):
        if col not in merged.columns:
            merged[col] = pd.NaT
    for col in ("post_count_all_time", "link_click_count_all_time"):
        if col not in merged.columns:
            merged[col] = 0
        merged[col] = merged[col].fillna(0).astype(int)

    merged["last_active_at"] = merged[["last_post_at", "last_link_click_at"]].max(axis=1)
    merged["days_since_last_active"] = (UTC_NOW() - merged["last_active_at"]).dt.days
    merged["days_since_last_email_open"] = (UTC_NOW() - merged["last_email_open_at"]).dt.days
    return merged


def segment_creators(last_activity: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    active_window = settings.get("activation", "active_window_days", default=14)
    at_risk_window = settings.get("activation", "at_risk_window_days", default=30)
    dormant_window = settings.get("activation", "dormant_window_days", default=60)

    df = last_activity.copy()

    def classify(row) -> str:
        days = row["days_since_last_active"]
        if pd.isna(row["last_active_at"]):
            return "Never Activated"
        if days <= active_window:
            return "Active"
        if days <= at_risk_window:
            return "Cooling Off"
        if days <= dormant_window:
            return "At Risk"
        return "Dormant"

    df["activation_segment"] = df.apply(classify, axis=1)
    return df


# ---------------------------------------------------------------------------
# Composite activation score (0-100)
# ---------------------------------------------------------------------------


def _minmax_scale(series: pd.Series) -> pd.Series:
    if series.empty:
        return series
    lo, hi = series.min(), series.max()
    if pd.isna(lo) or pd.isna(hi) or hi == lo:
        return pd.Series(0.0, index=series.index)
    return (series - lo) / (hi - lo)


def compute_activation_scores(
    inputs: ActivationInputs,
    last_activity: pd.DataFrame,
    settings: Settings,
) -> pd.DataFrame:
    """Composite 0-100 activation score per creator:

    - recency: how recently they last posted/link-clicked (decays with age)
    - frequency: volume of qualifying actions in the trailing window
    - diversity: did they engage across posts + links (vs. only one channel)
    - trend: are they accelerating or decelerating vs. the prior period
    """
    weights = settings.get("activation", "score_weights", default={}) or {}
    w_recency = weights.get("recency", 0.4)
    w_frequency = weights.get("frequency", 0.35)
    w_diversity = weights.get("diversity", 0.15)
    w_trend = weights.get("trend", 0.10)
    freq_window = settings.get("activation", "frequency_window_days", default=30)

    now = UTC_NOW()
    window_start = now - pd.Timedelta(days=freq_window)
    prior_window_start = now - pd.Timedelta(days=2 * freq_window)

    def count_in_window(df: pd.DataFrame, date_col: str, start, end) -> pd.Series:
        if df.empty or date_col not in df.columns:
            return pd.Series(dtype=int)
        d = df.copy()
        d[date_col] = _to_datetime_utc(d[date_col])
        mask = (d[date_col] >= start) & (d[date_col] < end)
        return d.loc[mask].groupby("creator_id").size()

    posts_recent = count_in_window(inputs.posts, "posted_at", window_start, now)
    links_recent = count_in_window(inputs.links, "clicked_at", window_start, now)
    posts_prior = count_in_window(inputs.posts, "posted_at", prior_window_start, window_start)
    links_prior = count_in_window(inputs.links, "clicked_at", prior_window_start, window_start)

    df = last_activity.copy().set_index("creator_id")
    df["posts_recent"] = posts_recent.reindex(df.index).fillna(0)
    df["links_recent"] = links_recent.reindex(df.index).fillna(0)
    df["posts_prior"] = posts_prior.reindex(df.index).fillna(0)
    df["links_prior"] = links_prior.reindex(df.index).fillna(0)

    # Recency: exponential decay, half-life = active_window_days.
    half_life = settings.get("activation", "active_window_days", default=14) or 14
    days_since = df["days_since_last_active"].fillna(9999)
    recency_component = np.power(0.5, days_since / half_life)

    frequency_raw = df["posts_recent"] + df["links_recent"]
    frequency_component = _minmax_scale(frequency_raw)

    has_posts = df["posts_recent"] > 0
    has_links = df["links_recent"] > 0
    diversity_component = (has_posts.astype(int) + has_links.astype(int)) / 2.0

    current_total = df["posts_recent"] + df["links_recent"]
    prior_total = df["posts_prior"] + df["links_prior"]
    trend_delta = current_total - prior_total
    trend_component = _minmax_scale(trend_delta)

    score = (
        w_recency * recency_component
        + w_frequency * frequency_component
        + w_diversity * diversity_component
        + w_trend * trend_component
    )
    df["activation_score"] = (score * 100).round(1)

    return df.reset_index()


# ---------------------------------------------------------------------------
# Email engagement
# ---------------------------------------------------------------------------


def compute_email_engagement(email_events: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    """Per creator: send/open counts, open rate, recency, and a `is_cold`
    flag for creators who've gone quiet on email specifically (which may
    warrant a different outreach channel, e.g. SMS/DM/manager call).
    """
    recent_window = settings.get("email_engagement", "recent_open_window_days", default=30)
    cold_after_days = settings.get("email_engagement", "cold_after_days", default=45)
    cold_after_n_sends = settings.get(
        "email_engagement", "cold_after_consecutive_unopened_sends", default=3
    )

    if email_events.empty:
        return pd.DataFrame(
            columns=[
                "creator_id",
                "sends_total",
                "opens_total",
                "open_rate",
                "last_sent_at",
                "last_open_at",
                "days_since_last_open",
                "consecutive_unopened_sends",
                "opened_recently",
                "is_cold",
            ]
        )

    events = email_events.copy()
    events["sent_at"] = _to_datetime_utc(events["sent_at"])
    events["opened_at"] = _to_datetime_utc(events.get("opened_at"))

    def per_creator(group: pd.DataFrame) -> pd.Series:
        group = group.sort_values("sent_at")
        sends_total = len(group)
        opens_total = int(group["opened_at"].notna().sum())
        last_sent_at = group["sent_at"].max()
        last_open_at = group["opened_at"].max() if opens_total else pd.NaT

        consecutive_unopened = 0
        for opened in reversed(group["opened_at"].tolist()):
            if pd.isna(opened):
                consecutive_unopened += 1
            else:
                break

        return pd.Series(
            {
                "sends_total": sends_total,
                "opens_total": opens_total,
                "open_rate": round(opens_total / sends_total, 3) if sends_total else 0.0,
                "last_sent_at": last_sent_at,
                "last_open_at": last_open_at,
                "consecutive_unopened_sends": consecutive_unopened,
            }
        )

    per_creator_df = events.groupby("creator_id").apply(per_creator, include_groups=False).reset_index()
    per_creator_df["days_since_last_open"] = (UTC_NOW() - per_creator_df["last_open_at"]).dt.days
    per_creator_df["opened_recently"] = per_creator_df["days_since_last_open"].fillna(9999) <= recent_window
    per_creator_df["is_cold"] = (
        per_creator_df["days_since_last_open"].fillna(9999) > cold_after_days
    ) | (per_creator_df["consecutive_unopened_sends"] >= cold_after_n_sends)

    return per_creator_df


# ---------------------------------------------------------------------------
# Needs-attention export (for outreach / Slack digest)
# ---------------------------------------------------------------------------


def build_needs_attention(
    scored: pd.DataFrame,
    email_engagement: pd.DataFrame,
) -> pd.DataFrame:
    """Merge activation segments + email coldness into one prioritized list
    that Community/Creator Managers can action (export to CSV / Slack).
    """
    df = scored.merge(email_engagement, on="creator_id", how="left")
    needs_attention = df[df["activation_segment"].isin(["At Risk", "Dormant", "Never Activated"])].copy()
    needs_attention["is_cold"] = needs_attention["is_cold"].fillna(True)

    def reason(row) -> str:
        reasons = [row["activation_segment"]]
        if row.get("is_cold"):
            reasons.append("Email cold")
        return " + ".join(reasons)

    needs_attention["reason"] = needs_attention.apply(reason, axis=1)
    sort_cols = [c for c in ["activation_score"] if c in needs_attention.columns]
    if sort_cols:
        needs_attention = needs_attention.sort_values(sort_cols)
    return needs_attention
