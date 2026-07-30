from __future__ import annotations

import pandas as pd
import pytest

from creatoriq_dashboard.activation_analytics import (
    compute_activation_funnel,
    compute_extended_kpis,
    enrich_activation_fields,
    filter_first_activations,
)
from creatoriq_dashboard.chat_engine import chat_turn, parse_user_message
from creatoriq_dashboard.metrics import (
    RawData,
    build_activity_events,
    build_creator_summary,
    classify_creators,
    resolve_date_range,
)

NOW = pd.Timestamp.now(tz="UTC")


def days_ago(n: float) -> pd.Timestamp:
    return NOW - pd.Timedelta(days=n)


@pytest.fixture
def sample_raw() -> RawData:
    creators = pd.DataFrame(
        {
            "creator_id": ["c1", "c2", "c3", "c4"],
            "name": ["Amy", "Bob", "Cara", "Dan"],
            "handle": ["@amy", "@bob", "@cara", "@dan"],
            "email": ["a@x.com", "b@x.com", "c@x.com", "d@x.com"],
            "tier": ["VIP", "Core", "New", "Core"],
            "joined_date": [days_ago(100), days_ago(20), days_ago(200), days_ago(5)],
        }
    )
    posts = pd.DataFrame(
        {
            "post_id": ["p1", "p2"],
            "creator_id": ["c1", "c1"],
            "posted_at": [days_ago(3), days_ago(2)],
        }
    )
    links = pd.DataFrame(
        {
            "link_id": ["l1", "l2"],
            "creator_id": ["c1", "c4"],
            "created_at": [days_ago(1), days_ago(2)],
        }
    )
    return RawData(
        creators=creators,
        posts=posts,
        links=links,
        email_events=pd.DataFrame(columns=["event_id", "creator_id", "sent_at", "opened_at", "clicked_at"]),
    )


def test_enrich_activation_fields(sample_raw: RawData):
    start, end = resolve_date_range("Last 30 days")
    summary = build_creator_summary(sample_raw, start, end)
    enriched = enrich_activation_fields(summary)
    assert enriched.loc[enriched["creator_id"] == "c1", "has_ever_activated"].iloc[0]
    assert not enriched.loc[enriched["creator_id"] == "c3", "has_ever_activated"].iloc[0]


def test_activation_funnel_counts(sample_raw: RawData):
    start, end = resolve_date_range("Last 30 days")
    summary = build_creator_summary(sample_raw, start, end)
    enriched = enrich_activation_fields(summary)
    funnel = compute_activation_funnel(enriched)
    assert funnel.iloc[0]["count"] == 4
    assert funnel[funnel["step_id"] == "ever_activated"]["count"].iloc[0] >= 2


def test_filter_first_activations_this_week(sample_raw: RawData):
    start, end = resolve_date_range("Last 7 days")
    summary = build_creator_summary(sample_raw, start, end)
    enriched = enrich_activation_fields(summary)
    first = filter_first_activations(enriched, start, end)
    assert "c4" in set(first["creator_id"])


def test_chat_first_activation_query(sample_raw: RawData):
    start, end = resolve_date_range("Last 30 days")
    summary = build_creator_summary(sample_raw, start, end)
    events = build_activity_events(sample_raw.posts, sample_raw.links)
    classified = classify_creators(summary, events, 30, 60, start, end)
    from creatoriq_dashboard.activation_analytics import ActivationContext

    ctx = ActivationContext(summary=summary, classified=classified)
    spec = parse_user_message("give me 10 creators that activated for the first time this week")
    assert spec.intent == "first_activations"
    assert spec.limit == 10

    response = chat_turn("give me 10 creators that activated for the first time this week", ctx)
    assert "first-ever activation" in response.message.lower() or "first" in response.message.lower()


def test_chat_count_ghosts(sample_raw: RawData):
    start, end = resolve_date_range("Last 30 days")
    summary = build_creator_summary(sample_raw, start, end)
    events = build_activity_events(sample_raw.posts, sample_raw.links)
    classified = classify_creators(summary, events, 30, 60, start, end)
    from creatoriq_dashboard.activation_analytics import ActivationContext

    ctx = ActivationContext(summary=summary, classified=classified)
    response = chat_turn("how many creators are ghosts?", ctx)
    assert response.message  # non-empty
    assert "ghost" in response.message.lower() or "creators" in response.message.lower()


def test_chat_posted_no_link(sample_raw: RawData):
    creators = pd.DataFrame(
        {
            "creator_id": ["x1"],
            "name": ["Poster"],
            "joined_date": [days_ago(50)],
            "tier": ["Core"],
        }
    )
    posts = pd.DataFrame({"post_id": ["p1"], "creator_id": ["x1"], "posted_at": [days_ago(5)]})
    links = pd.DataFrame(columns=["link_id", "creator_id", "created_at"])
    raw = RawData(creators=creators, posts=posts, links=links, email_events=pd.DataFrame())
    start, end = resolve_date_range("Last 30 days")
    summary = build_creator_summary(raw, start, end)
    classified = classify_creators(summary, build_activity_events(posts, links), 30, 60, start, end)
    from creatoriq_dashboard.activation_analytics import ActivationContext

    ctx = ActivationContext(summary=summary, classified=classified)
    response = chat_turn("show creators who posted but never linked", ctx)
    assert response.table is not None
    assert len(response.table) == 1
