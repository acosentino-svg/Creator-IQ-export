"""Tests for boosting-program scope filter."""
from __future__ import annotations

import pandas as pd
import pytest

from creatoriq_dashboard.boosting_rules import boosting_program_creator_ids
from creatoriq_dashboard.boosting_scope import filter_raw_for_boosting_program
from creatoriq_dashboard.config import AppConfig, Settings
from creatoriq_dashboard.metrics import RawData


def make_config() -> AppConfig:
    return AppConfig(
        mode="demo",
        base_url="https://api.example.test",
        crm_base_url="https://apis.example.test",
        api_key=None,
        org_id="",
        db_path=pytest.importorskip("pathlib").Path("/tmp/scope.db"),
        slack_webhook_url="",
        settings=Settings(
            raw={
                "boosting": {
                    "creator_tags": ["WBP"],
                    "campaign_names": ["Wayfair Creators Boosting Partnership"],
                    "campaign_ids": ["2206666"],
                }
            }
        ),
        endpoints={},
        field_mappings={},
    )


def test_boosting_program_ids_wbp_or_roster_or_campaign_post():
    config = make_config()
    creators = pd.DataFrame({"creator_id": ["1", "2"], "tags": ["WBP", ""]})
    posts = pd.DataFrame(
        {
            "creator_id": ["3"],
            "campaign_id": ["2206666"],
            "campaign_name": ["Wayfair Creators Boosting Partnership"],
        }
    )
    ids = boosting_program_creator_ids(creators, posts, config, campaign_roster_ids={"4"})
    assert ids == {"1", "3", "4"}


def test_filter_keeps_wbp_and_boosting_posts():
    config = make_config()
    creators = pd.DataFrame(
        {
            "creator_id": ["1", "2", "3"],
            "tags": ["Curator, WBP", "Affiliate", "Other"],
            "name": ["A", "B", "C"],
        }
    )
    posts = pd.DataFrame(
        {
            "creator_id": ["2", "3"],
            "campaign_name": ["Wayfair Creators Boosting Partnership", "Other Campaign"],
            "campaign_id": ["2206666", "1"],
            "posted_at": ["2026-01-01", "2026-01-02"],
        }
    )
    raw = RawData(
        creators=creators,
        posts=posts,
        links=pd.DataFrame({"creator_id": ["1", "2", "3"], "created_at": ["2026-01-01"] * 3}),
        email_events=pd.DataFrame({"creator_id": ["3"], "event_type": ["sent"]}),
    )
    out = filter_raw_for_boosting_program(raw, config)
    assert set(out.creators["creator_id"]) == {"1", "2"}
    assert len(out.posts) == 1
    assert out.posts.iloc[0]["creator_id"] == "2"
    assert set(out.links["creator_id"]) == {"1", "2"}
