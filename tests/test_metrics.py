from __future__ import annotations

import pandas as pd
import pytest

from creatoriq_dashboard.metrics import (
    RawData,
    build_activity_events,
    build_creator_summary,
    build_daily_activity,
    classify_creators,
    combine_activity_timelines,
    compute_email_segments,
    compute_kpis,
    compute_momentum,
    compute_new_activations,
    compute_went_dark,
    detect_spikes,
    resolve_date_range,
)

NOW = pd.Timestamp.now(tz="UTC")


def days_ago(n: float) -> pd.Timestamp:
    return NOW - pd.Timedelta(days=n)


@pytest.fixture
def raw() -> RawData:
    creators = pd.DataFrame(
        {
            "creator_id": ["c1", "c2", "c3", "c4", "c5"],
            "name": ["Active Amy", "Went Dark Dana", "Never Nora", "Linked Lea", "Reactivated Rae"],
            "handle": ["@amy", "@dana", "@nora", "@lea", "@rae"],
            "email": ["amy@x.com", "dana@x.com", "nora@x.com", "lea@x.com", "rae@x.com"],
            "status": ["Accepted"] * 5,
            "tags": ["VIP", "Core", "New", "Core", "VIP"],
            "joined_date": [days_ago(200)] * 5,
        }
    )
    posts = pd.DataFrame(
        {
            "post_id": ["p1", "p2", "p3", "p4", "p5"],
            "creator_id": ["c1", "c1", "c2", "c5", "c5"],
            "posted_at": [days_ago(2), days_ago(10), days_ago(90), days_ago(3), days_ago(150)],
        }
    )
    links = pd.DataFrame(
        {
            "link_id": ["l1", "l2", "l3"],
            "creator_id": ["c1", "c4", "c2"],
            "created_at": [days_ago(1), days_ago(5), days_ago(95)],
        }
    )
    email_events = pd.DataFrame(
        {
            "event_id": ["e1", "e2", "e3", "e4"],
            "creator_id": ["c1", "c2", "c3", "c4"],
            "sent_at": [days_ago(5), days_ago(5), days_ago(50), days_ago(3)],
            "opened_at": [days_ago(5) + pd.Timedelta(hours=1), pd.NaT, pd.NaT, days_ago(3) + pd.Timedelta(hours=1)],
            "clicked_at": [pd.NaT, pd.NaT, pd.NaT, pd.NaT],
        }
    )
    return RawData(creators=creators, posts=posts, links=links, email_events=email_events)


def test_resolve_date_range_presets():
    start, end = resolve_date_range("Last 7 days")
    assert (end - start).days == 7

    start, end = resolve_date_range("Last 30 days")
    assert (end - start).days == 30


def test_resolve_date_range_custom():
    custom_start = pd.Timestamp("2026-01-01")
    custom_end = pd.Timestamp("2026-01-15")
    start, end = resolve_date_range("Custom", custom_start, custom_end)
    assert start.date() == custom_start.date()
    assert end.date() == custom_end.date()


def test_build_activity_events_combines_posts_and_links(raw: RawData):
    events = build_activity_events(raw.posts, raw.links)
    assert set(events["event_type"]) == {"post", "link"}
    assert len(events) == len(raw.posts) + len(raw.links)


def test_build_creator_summary_basic_fields(raw: RawData):
    start, end = resolve_date_range("Last 30 days")
    summary = build_creator_summary(raw, start, end)
    row = summary.set_index("creator_id").loc["c1"]

    assert row["lifetime_post_count"] == 2
    assert row["lifetime_link_count"] == 1
    assert row["days_since_last_post"] == 2
    assert row["days_since_last_link"] == 1
    assert row["days_since_last_activity"] == 1  # link is more recent than post


def test_build_creator_summary_with_empty_but_shaped_tables():
    """Regression test: on a fresh live-mode setup (no sync has run yet),
    every table is legitimately empty but must still have the right
    columns -- and `joined_date` on an empty creators table previously
    defaulted to object dtype instead of datetime, breaking downstream
    `.dt` accessor calls in compute_new_activations.
    """
    creators = pd.DataFrame(columns=["creator_id", "name", "handle", "email", "status", "tier", "tags", "joined_date"])
    posts = pd.DataFrame(columns=["post_id", "creator_id", "posted_at"])
    links = pd.DataFrame(columns=["link_id", "creator_id", "created_at"])
    email_events = pd.DataFrame(columns=["event_id", "creator_id", "sent_at", "opened_at", "clicked_at"])
    raw = RawData(creators=creators, posts=posts, links=links, email_events=email_events)

    start, end = resolve_date_range("Last 30 days")
    summary = build_creator_summary(raw, start, end)
    assert summary.empty
    assert pd.api.types.is_datetime64_any_dtype(summary["joined_date"])

    result = compute_new_activations(summary, start, end)
    assert result["first_time_posters"].empty
    assert result["all_with_day_calcs"].empty


def test_build_creator_summary_never_activated_creator_has_nat(raw: RawData):
    start, end = resolve_date_range("Last 30 days")
    summary = build_creator_summary(raw, start, end)
    row = summary.set_index("creator_id").loc["c3"]
    assert pd.isna(row["last_post"])
    assert pd.isna(row["last_link"])
    assert pd.isna(row["last_activity_at"])


def test_classify_creators_states(raw: RawData):
    start, end = resolve_date_range("Last 30 days")
    summary = build_creator_summary(raw, start, end)
    events = build_activity_events(raw.posts, raw.links)
    classified = classify_creators(summary, events, active_days=30, went_dark_days=60, range_start=start, range_end=end)
    states = classified.set_index("creator_id")["activation_state"]

    assert states["c1"] == "Active"  # last activity 1 day ago
    assert states["c2"] == "Went Dark"  # posted + linked, quiet 90+ days
    assert states["c3"] == "Never Activated"  # no posts/links ever
    assert states["c4"] == "Active"  # link created 5 days ago


def test_classify_went_dark_requires_post_and_link():
    """Post-only creators who go quiet are Inactive, not Went Dark."""
    creators = pd.DataFrame({"creator_id": ["c1"], "name": ["Post Only"], "joined_date": [days_ago(200)]})
    posts = pd.DataFrame({"post_id": ["p1"], "creator_id": ["c1"], "posted_at": [days_ago(90)]})
    links = pd.DataFrame(columns=["link_id", "creator_id", "created_at"])
    raw = RawData(creators=creators, posts=posts, links=links, email_events=pd.DataFrame())
    start, end = resolve_date_range("Last 30 days")
    summary = build_creator_summary(raw, start, end)
    events = build_activity_events(posts, links)
    classified = classify_creators(summary, events, active_days=30, went_dark_days=60, range_start=start, range_end=end)
    assert classified.iloc[0]["activation_state"] == "Inactive"


def test_classify_active_threshold_responds_to_sidebar(raw: RawData):
    start, end = resolve_date_range("Last 30 days")
    summary = build_creator_summary(raw, start, end)
    events = build_activity_events(raw.posts, raw.links)
    tight = classify_creators(summary, events, active_days=1, went_dark_days=60, range_start=start, range_end=end)
    loose = classify_creators(summary, events, active_days=30, went_dark_days=60, range_start=start, range_end=end)
    assert int((tight["activation_state"] == "Active").sum()) < int((loose["activation_state"] == "Active").sum())


def test_classify_creators_reactivated_flag(raw: RawData):
    start, end = resolve_date_range("Last 30 days")
    summary = build_creator_summary(raw, start, end)
    events = build_activity_events(raw.posts, raw.links)
    classified = classify_creators(summary, events, active_days=30, went_dark_days=60, range_start=start, range_end=end)
    rae = classified.set_index("creator_id").loc["c5"]

    # c5 posted 150 days ago, then again 3 days ago -> a big gap, then active again.
    assert rae["activation_state"] == "Active"
    assert rae["is_reactivated"]
    assert not rae["is_consistently_active"]


def test_classify_creators_newly_activated_flag():
    """A creator whose one-and-only post happened inside the selected range
    should be flagged newly activated, not reactivated or consistently active.
    """
    creators = pd.DataFrame({"creator_id": ["c1"], "name": ["New Creator"], "joined_date": [days_ago(20)]})
    posts = pd.DataFrame({"post_id": ["p1"], "creator_id": ["c1"], "posted_at": [days_ago(2)]})
    links = pd.DataFrame(columns=["link_id", "creator_id", "created_at"])
    email_events = pd.DataFrame(columns=["event_id", "creator_id", "sent_at", "opened_at", "clicked_at"])
    raw = RawData(creators=creators, posts=posts, links=links, email_events=email_events)

    start, end = resolve_date_range("Last 30 days")
    summary = build_creator_summary(raw, start, end)
    events = build_activity_events(posts, links)
    classified = classify_creators(summary, events, active_days=30, went_dark_days=60, range_start=start, range_end=end)
    row = classified.iloc[0]

    assert row["is_newly_activated"]
    assert not row["is_reactivated"]
    assert not row["is_consistently_active"]


def test_compute_kpis(raw: RawData):
    start, end = resolve_date_range("Last 30 days")
    summary = build_creator_summary(raw, start, end)
    events = build_activity_events(raw.posts, raw.links)
    classified = classify_creators(summary, events, active_days=30, went_dark_days=60, range_start=start, range_end=end)
    kpis = compute_kpis(classified, posts_in_range_total=10, links_in_range_total=4)

    assert kpis["total_creators"] == 5
    assert kpis["never_activated_creators"] == 1
    assert kpis["went_dark_creators"] == 1
    assert kpis["total_posts_in_range"] == 10
    assert kpis["total_links_in_range"] == 4


def test_compute_new_activations(raw: RawData):
    start, end = resolve_date_range("Last 30 days")
    summary = build_creator_summary(raw, start, end)
    result = compute_new_activations(summary, start, end)

    # c1 posted within the range (first post 10 days ago) -> first-time poster.
    assert "c1" in set(result["first_time_posters"]["creator_id"])
    # c4 only ever created a link, never posted.
    assert "c4" in set(result["linked_no_post"]["creator_id"])


def test_compute_went_dark_recommends_action(raw: RawData):
    start, end = resolve_date_range("Last 30 days")
    summary = build_creator_summary(raw, start, end)
    events = build_activity_events(raw.posts, raw.links)
    classified = classify_creators(summary, events, active_days=30, went_dark_days=60, range_start=start, range_end=end)
    went_dark = compute_went_dark(classified)

    assert len(went_dark) == 1
    assert went_dark.iloc[0]["creator_id"] == "c2"
    assert isinstance(went_dark.iloc[0]["recommended_action"], str)
    assert len(went_dark.iloc[0]["recommended_action"]) > 0


def test_compute_email_segments(raw: RawData):
    start, end = resolve_date_range("Last 30 days")
    summary = build_creator_summary(raw, start, end)
    segments = compute_email_segments(summary)

    # c3 was sent an email but never opened it.
    assert "c3" in set(segments["never_opened"]["creator_id"])
    # c4 created a link but never posted.
    assert "c4" in set(segments["linked_no_post"]["creator_id"])


def test_compute_momentum_flags_spike():
    now = NOW
    creator_id = "c1"
    # Baseline: ~1 post every 4 days over the last 28 days before the recent window.
    baseline_dates = [now - pd.Timedelta(days=d) for d in range(10, 35, 4)]
    # Recent week: a burst of 6 posts.
    recent_dates = [now - pd.Timedelta(days=d) for d in range(0, 6)]
    posts = pd.DataFrame(
        {
            "post_id": [f"p{i}" for i in range(len(baseline_dates) + len(recent_dates))],
            "creator_id": [creator_id] * (len(baseline_dates) + len(recent_dates)),
            "posted_at": baseline_dates + recent_dates,
        }
    )
    links = pd.DataFrame(columns=["link_id", "creator_id", "created_at"])
    raw = RawData(
        creators=pd.DataFrame({"creator_id": [creator_id], "name": ["Spike Creator"]}),
        posts=posts,
        links=links,
        email_events=pd.DataFrame(columns=["event_id", "creator_id", "sent_at", "opened_at", "clicked_at"]),
    )

    momentum = compute_momentum(raw, recent_days=7, baseline_days=28, min_count_for_spike=2, spike_percentage_threshold=50)
    assert len(momentum) == 1
    row = momentum.iloc[0]
    assert row["creator_id"] == creator_id
    assert row["posts_this_week"] == 6
    assert row["spike_pct"] > 50


def test_build_daily_activity_and_timeline_combination():
    posts = pd.DataFrame({"posted_at": [days_ago(1), days_ago(1), days_ago(2)]})
    links = pd.DataFrame({"created_at": [days_ago(1)]})

    posts_timeline = build_daily_activity(posts, "posted_at", "Posts")
    links_timeline = build_daily_activity(links, "created_at", "Links")
    combined = combine_activity_timelines(posts_timeline, links_timeline)

    assert set(combined["activity_type"]) == {"Posts", "Links"}
    assert combined[combined["activity_type"] == "Posts"]["count"].sum() == 3


def test_detect_spikes_flags_anomalous_day():
    dates = pd.date_range(end=NOW.normalize(), periods=40, freq="D")
    counts = [1] * 39 + [50]
    timeline = pd.DataFrame({"date": dates.date, "activity_type": "Posts", "count": counts})

    result = detect_spikes(timeline, baseline_window_days=28, min_count_for_spike=3, z_score_threshold=2.0)
    last_day = result.iloc[-1]
    assert last_day["is_spike"]
    assert last_day["z_score"] > 2.0


def test_detect_spikes_respects_min_count_floor():
    dates = pd.date_range(end=NOW.normalize(), periods=40, freq="D")
    counts = [0] * 39 + [2]
    timeline = pd.DataFrame({"date": dates.date, "activity_type": "Posts", "count": counts})

    result = detect_spikes(timeline, baseline_window_days=28, min_count_for_spike=3, z_score_threshold=2.0)
    assert not result.iloc[-1]["is_spike"]
