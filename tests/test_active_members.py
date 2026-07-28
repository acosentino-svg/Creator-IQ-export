from __future__ import annotations

import io

import pandas as pd

from creatoriq_dashboard.active_members import merge_active_member_link_frames, parse_active_members_csv
from creatoriq_dashboard.metrics import RawData, build_creator_summary, resolve_date_range


def test_parse_active_members_csv_detects_columns():
    csv = """Publisher Id,Publisher Name,Last Link Created
12345,Jane Doe,2025-06-01
67890,John Smith,2024-12-15
"""
    df = parse_active_members_csv(io.StringIO(csv))
    assert len(df) == 2
    assert set(df["creator_id"]) == {"12345", "67890"}
    assert df["last_link"].notna().all()


def test_active_members_merges_into_creator_summary():
    creators = pd.DataFrame({"creator_id": ["12345", "99999"], "name": ["Jane", "Ghost"]})
    posts = pd.DataFrame(columns=["post_id", "creator_id", "posted_at"])
    links = pd.DataFrame(columns=["link_id", "creator_id", "created_at"])
    active = pd.DataFrame(
        {
            "creator_id": ["12345"],
            "last_link": [pd.Timestamp("2025-06-01", tz="UTC")],
            "first_link": [pd.Timestamp("2025-01-01", tz="UTC")],
        }
    )
    raw = RawData(
        creators=creators,
        posts=posts,
        links=links,
        email_events=pd.DataFrame(),
        active_member_links=active,
    )
    start, end = resolve_date_range("Last 30 days")
    summary = build_creator_summary(raw, start, end)
    jane = summary.set_index("creator_id").loc["12345"]
    assert pd.notna(jane["last_link"])
    assert jane["last_link"].date().isoformat() == "2025-06-01"


def test_merge_active_member_link_frames_combines_batches():
    first = pd.DataFrame(
        {
            "creator_id": ["1", "2"],
            "last_link": [pd.Timestamp("2025-01-01", tz="UTC"), pd.Timestamp("2025-02-01", tz="UTC")],
            "first_link": [pd.Timestamp("2025-01-01", tz="UTC"), pd.Timestamp("2025-02-01", tz="UTC")],
        }
    )
    second = pd.DataFrame(
        {
            "creator_id": ["2", "3"],
            "last_link": [pd.Timestamp("2025-06-01", tz="UTC"), pd.Timestamp("2025-03-01", tz="UTC")],
            "first_link": [pd.Timestamp("2025-02-01", tz="UTC"), pd.Timestamp("2025-03-01", tz="UTC")],
        }
    )
    merged = merge_active_member_link_frames(first, second)
    assert len(merged) == 3
    assert merged.set_index("creator_id").loc["2", "last_link"].date().isoformat() == "2025-06-01"
