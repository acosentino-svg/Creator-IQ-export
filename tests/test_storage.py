from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from creatoriq_dashboard.storage import (
    append_link_click_snapshot,
    derive_link_click_deltas,
    get_engine,
)


@pytest.fixture
def engine(tmp_path):
    return get_engine(tmp_path / "test.db")


def test_derive_link_click_deltas_empty_with_no_snapshots(engine):
    result = derive_link_click_deltas(engine)
    assert result.empty


def test_derive_link_click_deltas_needs_two_snapshots(engine):
    posts_df = pd.DataFrame(
        {
            "post_id": ["p1"],
            "creator_id": ["c1"],
            "campaign_id": ["camp1"],
            "link_clicks": [10],
        }
    )
    append_link_click_snapshot(engine, posts_df, datetime.now(timezone.utc))

    # A single snapshot has no prior point of comparison -> no deltas yet.
    result = derive_link_click_deltas(engine)
    assert result.empty


def test_derive_link_click_deltas_computes_increase(engine):
    day1 = datetime.now(timezone.utc) - timedelta(days=1)
    day2 = datetime.now(timezone.utc)

    posts_day1 = pd.DataFrame(
        {"post_id": ["p1"], "creator_id": ["c1"], "campaign_id": ["camp1"], "link_clicks": [10]}
    )
    posts_day2 = pd.DataFrame(
        {"post_id": ["p1"], "creator_id": ["c1"], "campaign_id": ["camp1"], "link_clicks": [35]}
    )
    append_link_click_snapshot(engine, posts_day1, day1)
    append_link_click_snapshot(engine, posts_day2, day2)

    result = derive_link_click_deltas(engine)
    assert len(result) == 1
    row = result.iloc[0]
    assert row["link_id"] == "p1"
    assert row["creator_id"] == "c1"
    assert row["clicks"] == 25


def test_derive_link_click_deltas_ignores_decreases_and_flat(engine):
    day1 = datetime.now(timezone.utc) - timedelta(days=2)
    day2 = datetime.now(timezone.utc) - timedelta(days=1)
    day3 = datetime.now(timezone.utc)

    for day, clicks in [(day1, 10), (day2, 10), (day3, 8)]:
        posts_df = pd.DataFrame(
            {"post_id": ["p1"], "creator_id": ["c1"], "campaign_id": ["camp1"], "link_clicks": [clicks]}
        )
        append_link_click_snapshot(engine, posts_df, day)

    result = derive_link_click_deltas(engine)
    # Flat (day1->day2, delta=0) and decreasing (day2->day3, delta=-2) don't count as click activity.
    assert result.empty


def test_derive_link_click_deltas_tracks_multiple_posts_independently(engine):
    day1 = datetime.now(timezone.utc) - timedelta(days=1)
    day2 = datetime.now(timezone.utc)

    posts_day1 = pd.DataFrame(
        {
            "post_id": ["p1", "p2"],
            "creator_id": ["c1", "c2"],
            "campaign_id": ["camp1", "camp1"],
            "link_clicks": [10, 100],
        }
    )
    posts_day2 = pd.DataFrame(
        {
            "post_id": ["p1", "p2"],
            "creator_id": ["c1", "c2"],
            "campaign_id": ["camp1", "camp1"],
            "link_clicks": [12, 150],
        }
    )
    append_link_click_snapshot(engine, posts_day1, day1)
    append_link_click_snapshot(engine, posts_day2, day2)

    result = derive_link_click_deltas(engine).set_index("link_id")
    assert result.loc["p1", "clicks"] == 2
    assert result.loc["p2", "clicks"] == 50
