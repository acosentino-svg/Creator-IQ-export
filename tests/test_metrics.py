from __future__ import annotations

import pandas as pd
import pytest

from creatoriq_dashboard.config import Settings
from creatoriq_dashboard.metrics import (
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

NOW = pd.Timestamp.now(tz="UTC")


def days_ago(n: int) -> pd.Timestamp:
    return NOW - pd.Timedelta(days=n)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        raw={
            "activation": {
                "active_window_days": 14,
                "at_risk_window_days": 30,
                "dormant_window_days": 60,
                "score_weights": {"recency": 0.4, "frequency": 0.35, "diversity": 0.15, "trend": 0.10},
                "frequency_window_days": 30,
            },
            "email_engagement": {
                "recent_open_window_days": 30,
                "cold_after_days": 45,
                "cold_after_consecutive_unopened_sends": 3,
            },
            "spike_detection": {
                "baseline_window_days": 28,
                "min_count_for_spike": 3,
                "z_score_threshold": 2.0,
            },
        }
    )


@pytest.fixture
def inputs() -> ActivationInputs:
    creators = pd.DataFrame(
        {
            "creator_id": ["c1", "c2", "c3", "c4"],
            "name": ["Active Amy", "Risky Rick", "Dormant Dana", "Never Nora"],
            "tier": ["VIP", "Core", "Core", "New"],
            "status": ["Active"] * 4,
            "joined_date": [days_ago(200)] * 4,
        }
    )
    posts = pd.DataFrame(
        {
            "post_id": ["p1", "p2", "p3", "p4"],
            "creator_id": ["c1", "c1", "c2", "c3"],
            "posted_at": [days_ago(2), days_ago(10), days_ago(40), days_ago(90)],
        }
    )
    links = pd.DataFrame(
        {
            "event_id": ["l1"],
            "creator_id": ["c1"],
            "clicked_at": [days_ago(1)],
        }
    )
    email_events = pd.DataFrame(
        {
            "event_id": ["e1", "e2", "e3", "e4"],
            "creator_id": ["c1", "c2", "c3", "c4"],
            "sent_at": [days_ago(5), days_ago(5), days_ago(50), days_ago(3)],
            "opened_at": [days_ago(5) + pd.Timedelta(hours=1), pd.NaT, pd.NaT, pd.NaT],
        }
    )
    return ActivationInputs(creators=creators, posts=posts, links=links, email_events=email_events)


def test_compute_last_activity(inputs: ActivationInputs):
    last_activity = compute_last_activity(inputs)
    assert set(last_activity["creator_id"]) == {"c1", "c2", "c3", "c4"}

    amy = last_activity.set_index("creator_id").loc["c1"]
    assert amy["post_count_all_time"] == 2
    assert amy["link_click_count_all_time"] == 1
    assert amy["days_since_last_active"] == 1  # last link click was 1 day ago

    nora = last_activity.set_index("creator_id").loc["c4"]
    assert pd.isna(nora["last_active_at"])


def test_segment_creators(inputs: ActivationInputs, settings: Settings):
    last_activity = compute_last_activity(inputs)
    segmented = segment_creators(last_activity, settings)
    segments = segmented.set_index("creator_id")["activation_segment"]

    assert segments["c1"] == "Active"  # active 1 day ago
    assert segments["c2"] == "At Risk"  # last active 40 days ago (30 < 40 <= 60)
    assert segments["c3"] == "Dormant"  # last active 90 days ago (> 60)
    assert segments["c4"] == "Never Activated"  # no posts/links ever


def test_compute_activation_scores_are_bounded(inputs: ActivationInputs, settings: Settings):
    last_activity = compute_last_activity(inputs)
    segmented = segment_creators(last_activity, settings)
    scored = compute_activation_scores(inputs, segmented, settings)

    assert (scored["activation_score"] >= 0).all()
    assert (scored["activation_score"] <= 100).all()
    # The most recently/most frequently active creator should score highest.
    top = scored.sort_values("activation_score", ascending=False).iloc[0]
    assert top["creator_id"] == "c1"


def test_compute_email_engagement(inputs: ActivationInputs, settings: Settings):
    engagement = compute_email_engagement(inputs.email_events, settings)
    by_id = engagement.set_index("creator_id")

    assert by_id.loc["c1", "opens_total"] == 1
    assert by_id.loc["c1", "open_rate"] == 1.0
    assert by_id.loc["c2", "opens_total"] == 0
    assert bool(by_id.loc["c3", "is_cold"]) is True  # sent 50 days ago, never opened


def test_compute_email_engagement_empty(settings: Settings):
    empty = pd.DataFrame(columns=["creator_id", "sent_at", "opened_at"])
    result = compute_email_engagement(empty, settings)
    assert result.empty


def test_build_daily_activity_and_timeline_combination():
    posts = pd.DataFrame({"posted_at": [days_ago(1), days_ago(1), days_ago(2)]})
    links = pd.DataFrame({"clicked_at": [days_ago(1)]})

    posts_timeline = build_daily_activity(posts, "posted_at", "Posts")
    links_timeline = build_daily_activity(links, "clicked_at", "Link Clicks")
    combined = combine_activity_timelines(posts_timeline, links_timeline)

    assert set(combined["activity_type"]) == {"Posts", "Link Clicks"}
    assert combined[combined["activity_type"] == "Posts"]["count"].sum() == 3


def test_detect_spikes_flags_anomalous_day():
    dates = pd.date_range(end=NOW.normalize(), periods=40, freq="D")
    counts = [1] * 39 + [50]  # last day is a huge spike
    timeline = pd.DataFrame({"date": dates.date, "activity_type": "Posts", "count": counts})

    result = detect_spikes(timeline, baseline_window_days=28, min_count_for_spike=3, z_score_threshold=2.0)
    last_day = result.iloc[-1]
    assert last_day["is_spike"]
    assert last_day["z_score"] > 2.0


def test_detect_spikes_respects_min_count_floor():
    dates = pd.date_range(end=NOW.normalize(), periods=40, freq="D")
    counts = [0] * 39 + [2]  # technically a jump, but below the min-count floor
    timeline = pd.DataFrame({"date": dates.date, "activity_type": "Posts", "count": counts})

    result = detect_spikes(timeline, baseline_window_days=28, min_count_for_spike=3, z_score_threshold=2.0)
    assert not result.iloc[-1]["is_spike"]


def test_build_needs_attention_prioritizes_low_scores(inputs: ActivationInputs, settings: Settings):
    last_activity = compute_last_activity(inputs)
    segmented = segment_creators(last_activity, settings)
    scored = compute_activation_scores(inputs, segmented, settings)
    email_engagement = compute_email_engagement(inputs.email_events, settings)

    needs_attention = build_needs_attention(scored, email_engagement)
    assert "c1" not in set(needs_attention["creator_id"])  # Amy is Active, shouldn't need attention
    assert "c4" in set(needs_attention["creator_id"])  # Nora never activated
