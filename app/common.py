"""Shared bootstrap + cached data/metrics helpers used by every Streamlit page."""
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
from creatoriq_dashboard.metrics import (  # noqa: E402
    ActivationInputs,
    build_daily_activity,
    build_needs_attention,
    combine_activity_timelines,
    compute_activation_scores,
    compute_email_engagement,
    compute_last_activity,
    detect_spikes,
    segment_creators,
)

DATA_CACHE_TTL_SECONDS = 300


@st.cache_resource
def get_config() -> AppConfig:
    return load_config()


@st.cache_data(ttl=DATA_CACHE_TTL_SECONDS, show_spinner="Loading CreatorIQ data...")
def get_raw_inputs(_config_mode: str) -> tuple[dict[str, pd.DataFrame], dict[str, str | None]]:
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
        },
        sync_status,
    )


def get_activation_inputs() -> tuple[ActivationInputs, dict[str, str | None]]:
    config = get_config()
    raw, sync_status = get_raw_inputs(config.mode)
    return (
        ActivationInputs(
            creators=raw["creators"],
            posts=raw["posts"],
            links=raw["links"],
            email_events=raw["email_events"],
        ),
        sync_status,
    )


@st.cache_data(ttl=DATA_CACHE_TTL_SECONDS)
def compute_dashboard_bundle(_config_mode: str):
    """One-stop computation of every derived table the pages need, so each
    page doesn't recompute activation scores / spikes independently.
    """
    config = get_config()
    inputs, sync_status = load_inputs(config)

    last_activity = compute_last_activity(inputs)
    segmented = segment_creators(last_activity, config.settings)
    scored = compute_activation_scores(inputs, segmented, config.settings)
    email_engagement = compute_email_engagement(inputs.email_events, config.settings)
    needs_attention = build_needs_attention(scored, email_engagement)

    posts_timeline = build_daily_activity(inputs.posts, "posted_at", "Posts")
    links_timeline = build_daily_activity(inputs.links, "clicked_at", "Link Clicks")
    timeline = combine_activity_timelines(posts_timeline, links_timeline)
    spike_cfg = config.settings.get("spike_detection", default={}) or {}
    spikes = detect_spikes(
        timeline,
        baseline_window_days=spike_cfg.get("baseline_window_days", 28),
        min_count_for_spike=spike_cfg.get("min_count_for_spike", 3),
        z_score_threshold=spike_cfg.get("z_score_threshold", 2.0),
    )

    return {
        "inputs": inputs,
        "sync_status": sync_status,
        "scored": scored,
        "email_engagement": email_engagement,
        "needs_attention": needs_attention,
        "timeline": timeline,
        "spikes": spikes,
    }


def get_bundle():
    config = get_config()
    return compute_dashboard_bundle(config.mode)


def render_mode_badge() -> None:
    config = get_config()
    if config.is_demo:
        st.sidebar.info("**Demo mode** — showing synthetic sample data.\n\nSet `CREATORIQ_DASHBOARD_MODE=live` "
                         "in `.env` once your CreatorIQ API credentials are configured.")
    else:
        st.sidebar.success(f"**Live mode** — reading cached data synced from {config.base_url}")
