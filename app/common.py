"""Shared bootstrap + sidebar controls + cached data used by every page.

Every page in app/pages/ starts with:

    from common import get_bundle, render_sidebar_controls

`render_sidebar_controls()` draws the global date-range selector and the
"Active"/"Went Dark" threshold controls in the sidebar, persisting choices
in st.session_state so they carry over as the user navigates between pages.
`get_bundle()` recomputes every derived table (creator summary, activation
states, KPIs, momentum, went-dark, new activations, email segments) from
the current controls -- cheap enough on mock/demo-sized data to just
recompute on every rerun rather than cache.
"""
from __future__ import annotations

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from creatoriq_dashboard.config import AppConfig, load_config  # noqa: E402
from creatoriq_dashboard.data_access import load_inputs  # noqa: E402
from creatoriq_dashboard.activation_analytics import (  # noqa: E402
    ActivationContext,
    build_outreach_queue,
    compute_activation_funnel,
    compute_activation_trends,
    compute_cohort_activation,
    compute_extended_kpis,
    compute_struggle_segments,
    enrich_activation_fields,
)
from creatoriq_dashboard.metrics import (  # noqa: E402
    DATE_RANGE_PRESETS,
    RawData,
    build_activity_events,
    build_creator_summary,
    build_daily_activity,
    classify_creators,
    combine_activity_timelines,
    compute_data_quality,
    compute_email_segments,
    compute_kpis,
    compute_momentum,
    compute_new_activations,
    compute_went_dark,
    detect_spikes,
    resolve_date_range,
)

DATA_CACHE_TTL_SECONDS = 300


@st.cache_resource
def get_config() -> AppConfig:
    return load_config()


@st.cache_data(ttl=DATA_CACHE_TTL_SECONDS, show_spinner="Loading CreatorIQ data...")
def _get_raw_inputs(_config_mode: str) -> tuple[dict[str, pd.DataFrame], dict[str, str | None]]:
    # _config_mode is only in the signature to bust the cache when the user
    # flips demo/live mode; the actual config object isn't hashable-friendly.
    config = get_config()
    inputs, sync_status = load_inputs(config)
    return (
        {
            "creators": inputs.creators,
            "posts": inputs.posts,
            "links": inputs.links,
            "email_events": inputs.email_events,
            "link_clicks": inputs.link_clicks,
        },
        sync_status,
    )


def get_raw_data() -> tuple[RawData, dict[str, str | None]]:
    config = get_config()
    raw, sync_status = _get_raw_inputs(config.mode)
    return (
        RawData(
            creators=raw["creators"],
            posts=raw["posts"],
            links=raw["links"],
            email_events=raw["email_events"],
            link_clicks=raw.get("link_clicks"),
        ),
        sync_status,
    )


def render_mode_badge() -> None:
    st.sidebar.caption("🔒 **Internal use only** — not shared with creators.")
    config = get_config()
    if config.is_demo:
        st.sidebar.info(
            "**Demo mode** — showing synthetic sample data.\n\nSet `CREATORIQ_DASHBOARD_MODE=live` "
            "in `.env` once your CreatorIQ API credentials are configured."
        )
    else:
        st.sidebar.success(f"**Live mode** — reading cached data synced from {config.base_url}")


def render_sidebar_controls() -> dict:
    """Draws the global date-range + activation-threshold controls in the
    sidebar and returns the resolved values every page needs:
    {range_start, range_end, preset, active_days, went_dark_days}.
    """
    config = get_config()
    render_mode_badge()

    st.sidebar.divider()
    st.sidebar.subheader("📅 Date range")
    if "date_range_preset" not in st.session_state:
        st.session_state["date_range_preset"] = "Last 30 days"
    preset = st.sidebar.selectbox("Range", DATE_RANGE_PRESETS, key="date_range_preset")

    custom_start = custom_end = None
    if preset == "Custom":
        col1, col2 = st.sidebar.columns(2)
        default_start = (pd.Timestamp.now() - pd.Timedelta(days=30)).date()
        if "custom_range_start" not in st.session_state:
            st.session_state["custom_range_start"] = default_start
        if "custom_range_end" not in st.session_state:
            st.session_state["custom_range_end"] = pd.Timestamp.now().date()
        custom_start = col1.date_input("Start", key="custom_range_start")
        custom_end = col2.date_input("End", key="custom_range_end")

    range_start, range_end = resolve_date_range(preset, custom_start, custom_end)

    st.sidebar.divider()
    st.sidebar.subheader("⚙️ Activation settings")
    if "active_days" not in st.session_state:
        st.session_state["active_days"] = config.settings.get("activation", "active_days", default=30)
    if "went_dark_days" not in st.session_state:
        st.session_state["went_dark_days"] = config.settings.get("activation", "went_dark_days", default=60)

    active_days = st.sidebar.number_input(
        "Days considered 'Active'",
        min_value=1,
        max_value=365,
        step=1,
        key="active_days",
        help="A creator who posted or created a link within this many days counts as Active.",
    )
    went_dark_days = st.sidebar.number_input(
        "Days before 'Went Dark'",
        min_value=1,
        max_value=730,
        step=1,
        key="went_dark_days",
        help="A previously-active creator who's been quiet for at least this many days is flagged Went Dark.",
    )
    if went_dark_days <= active_days:
        st.sidebar.warning("'Went Dark' should be greater than 'Active' — adjusting automatically.")
        went_dark_days = active_days + 1

    return {
        "range_start": range_start,
        "range_end": range_end,
        "preset": preset,
        "active_days": int(active_days),
        "went_dark_days": int(went_dark_days),
    }


def get_bundle() -> dict:
    """Computes every derived table every page needs from the current
    sidebar controls. Cheap on demo/mock-sized data, so this recomputes
    fresh on every rerun rather than caching (caching would need the
    date-range + threshold controls in the cache key anyway).
    """
    controls = render_sidebar_controls()
    raw, sync_status = get_raw_data()

    range_start, range_end = controls["range_start"], controls["range_end"]
    summary = build_creator_summary(raw, range_start, range_end)
    events = build_activity_events(raw.posts, raw.links)
    classified = classify_creators(
        summary,
        events,
        active_days=controls["active_days"],
        went_dark_days=controls["went_dark_days"],
        range_start=range_start,
        range_end=range_end,
    )
    kpis = compute_kpis(
        classified,
        posts_in_range_total=int(summary["posts_in_range"].sum()) if not summary.empty else 0,
        links_in_range_total=int(summary["links_in_range"].sum()) if not summary.empty else 0,
    )

    config = get_config()
    momentum_cfg = config.settings.get("momentum", default={}) or {}
    momentum = compute_momentum(
        raw,
        recent_days=momentum_cfg.get("recent_window_days", 7),
        baseline_days=momentum_cfg.get("baseline_window_days", 28),
        min_count_for_spike=momentum_cfg.get("min_count_for_spike", 3),
        spike_percentage_threshold=momentum_cfg.get("spike_percentage_threshold", 75),
    )

    went_dark = compute_went_dark(classified)
    new_activations = compute_new_activations(summary, range_start, range_end)
    email_segments = compute_email_segments(summary)

    posts_timeline = build_daily_activity(raw.posts, "posted_at", "Posts")
    link_click_df = raw.link_clicks if raw.link_clicks is not None else pd.DataFrame()
    links_timeline = build_daily_activity(link_click_df, "clicked_at", "Link clicks")
    timeline = combine_activity_timelines(posts_timeline, links_timeline)
    spike_cfg = config.settings.get("momentum", default={}) or {}
    spikes = detect_spikes(
        timeline,
        baseline_window_days=spike_cfg.get("baseline_window_days", 28),
        min_count_for_spike=spike_cfg.get("min_count_for_spike", 3),
        z_score_threshold=2.0,
    )

    enriched = enrich_activation_fields(summary)
    extended_kpis = compute_extended_kpis(enriched, classified)
    funnel = compute_activation_funnel(enriched)
    cohorts = compute_cohort_activation(enriched)
    activation_trends = compute_activation_trends(enriched, raw.posts, raw.links)
    struggle_segments = compute_struggle_segments(enriched, classified)
    outreach_queue = build_outreach_queue(enriched, classified)
    activation_ctx = ActivationContext(
        summary=summary,
        classified=classified,
        active_days=controls["active_days"],
        went_dark_days=controls["went_dark_days"],
    )
    data_quality = compute_data_quality(raw, summary, is_live=not config.is_demo)

    return {
        "controls": controls,
        "raw": raw,
        "sync_status": sync_status,
        "summary": summary,
        "enriched": enriched,
        "classified": classified,
        "kpis": kpis,
        "extended_kpis": extended_kpis,
        "funnel": funnel,
        "cohorts": cohorts,
        "activation_trends": activation_trends,
        "struggle_segments": struggle_segments,
        "outreach_queue": outreach_queue,
        "activation_ctx": activation_ctx,
        "data_quality": data_quality,
        "momentum": momentum,
        "went_dark": went_dark,
        "new_activations": new_activations,
        "email_segments": email_segments,
        "timeline": timeline,
        "spikes": spikes,
    }


def creator_display_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Select only the columns that actually exist -- keeps pages resilient
    to a creator table that's missing an optional field (e.g. on live data
    before every enrichment call has been wired up)."""
    return df[[c for c in columns if c in df.columns]]


def go_to_creator_profile(creator_id: str) -> None:
    st.session_state["selected_creator_id"] = creator_id
    st.switch_page("pages/6_Creator_Profile.py")
