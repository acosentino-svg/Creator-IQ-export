from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pandas as pd
import pytest

from creatoriq_dashboard.boosting_creatoriq import (
    _fetch_boosting_campaigns,
    sync_boosting_from_creatoriq,
)
from creatoriq_dashboard.boosting_data_access import should_auto_sync_boosting
from creatoriq_dashboard.config import AppConfig, Settings


def make_config(**boosting_overrides) -> AppConfig:
    boosting = {
        "creator_tags": ["WBP"],
        "campaign_names": ["Wayfair Creators Boosting Partnership"],
        "campaign_name_contains": [],
        "campaign_ids": [],
        "eligible_hashtags": ["WayfairCreator", "wayfairelevate"],
        "default_eligible_if_in_campaign": False,
        "campaign_status_filter": [],
        "auto_sync_on_load": False,
        "sync_stale_hours": 24,
        **boosting_overrides,
    }
    return AppConfig(
        mode="live",
        base_url="https://api.example.test",
        crm_base_url="https://apis.example.test",
        api_key="test-key",
        org_id="",
        db_path=pytest.importorskip("pathlib").Path("/tmp/test_boosting_api.db"),
        slack_webhook_url="",
        settings=Settings(raw={"boosting": boosting}),
        endpoints={"resources": {"campaign_activity": {}, "campaign_publishers": {}, "publishers": {}}},
        field_mappings={
            "campaigns": {"campaign_id": "CampaignId", "campaign_name": "CampaignName", "status": "CampaignStatus"},
            "creators": {"creator_id": "PublisherId", "name": "PublisherName"},
            "publishers": {"creator_id": "Id", "name": "PublisherName", "tags": "Tags"},
            "posts": {
                "post_id": "Id",
                "creator_id": "PublisherId",
                "campaign_name": "CampaignName",
                "posted_at": "DateSubmitted",
                "post_url": "PostUrl",
                "post_caption": "Caption",
            },
        },
    )


def test_fetch_boosting_campaigns_ignores_inactive_status():
    config = make_config()
    client = MagicMock()
    client.fetch_all.return_value = [
        {"CampaignId": "1", "CampaignName": "Wayfair Creators Boosting Partnership", "CampaignStatus": "Completed"},
        {"CampaignId": "2", "CampaignName": "Affiliate", "CampaignStatus": "Active"},
    ]
    df = _fetch_boosting_campaigns(config, client)
    assert list(df["campaign_id"]) == ["1"]


def test_fetch_boosting_campaigns_respects_status_filter():
    config = make_config(campaign_status_filter=["Active"])
    client = MagicMock()
    client.fetch_all.return_value = [
        {"CampaignId": "1", "CampaignName": "Wayfair Creators Boosting Partnership", "CampaignStatus": "Completed"},
        {"CampaignId": "2", "CampaignName": "Wayfair Creators Boosting Partnership", "CampaignStatus": "Active"},
    ]
    df = _fetch_boosting_campaigns(config, client)
    assert list(df["campaign_id"]) == ["2"]


def test_sync_boosting_from_creatoriq_fetches_campaign_posts():
    config = make_config()
    client = MagicMock()
    client.fetch_all.return_value = [
        {"CampaignId": "c1", "CampaignName": "Wayfair Creators Boosting Partnership", "CampaignStatus": "Active"},
    ]
    client.fetch_unpaginated_list.return_value = [{"PublisherId": "pub_1", "PublisherName": "Creator One"}]
    client.fetch_nested_all.return_value = [
        {
            "Id": "p1",
            "PublisherId": "pub_1",
            "CampaignName": "Wayfair Creators Boosting Partnership",
            "DateSubmitted": "2026-08-15T12:00:00Z",
            "PostUrl": "https://example.com/p/1",
            "Caption": "Room #WayfairCreator #wayfairelevate",
        }
    ]
    client.iter_resource.return_value = []

    out = sync_boosting_from_creatoriq(config, client=client)
    assert len(out) == 1
    assert out.iloc[0]["creator_id"] == "pub_1"
    assert out.iloc[0]["creator_name"] == "Creator One"
    assert out.iloc[0]["eligible"] == True
    client.fetch_nested_all.assert_called_once_with("campaign_activity", path_params={"campaign_id": "c1"})


def test_sync_uses_configured_campaign_id_without_campaigns_list():
    config = make_config(campaign_ids=["2206666"])
    client = MagicMock()
    client.fetch_all.return_value = []
    client.fetch_unpaginated_list.return_value = []
    client.fetch_nested_all.return_value = [
        {
            "Id": "p1",
            "PublisherId": "pub_1",
            "CampaignName": "Wayfair Creators Boosting Partnership",
            "DateSubmitted": "2026-08-15T12:00:00Z",
            "PostUrl": "https://example.com/p/1",
            "Caption": "Room #WayfairCreator #wayfairelevate",
        }
    ]
    client.iter_resource.return_value = []

    out = sync_boosting_from_creatoriq(config, client=client)
    assert len(out) == 1
    client.fetch_nested_all.assert_called_once_with("campaign_activity", path_params={"campaign_id": "2206666"})


def test_sync_skips_campaigns_list_when_id_configured():
    config = make_config(campaign_ids=["2206666"])
    client = MagicMock()
    client.fetch_unpaginated_list.return_value = []
    client.fetch_nested_all.return_value = []
    client.iter_resource.return_value = []

    sync_boosting_from_creatoriq(config, client=client)

    client.fetch_all.assert_not_called()


def test_wbp_publisher_scan_skipped_by_default():
    config = make_config()
    client = MagicMock()
    client.iter_resource.return_value = [{"Publisher": {"Id": "1", "Tags": "WBP"}}]

    from creatoriq_dashboard.boosting_creatoriq import _fetch_wbp_tagged_publishers

    out = _fetch_wbp_tagged_publishers(config, client)
    assert out.empty
    client.iter_resource.assert_not_called()


def test_should_auto_sync_when_empty():
    config = make_config(auto_sync_on_load=True)
    assert should_auto_sync_boosting(config, pd.DataFrame(), None) is True


def test_should_not_auto_sync_when_disabled():
    config = make_config(auto_sync_on_load=False)
    assert should_auto_sync_boosting(config, pd.DataFrame(), None) is False


def test_should_auto_sync_when_stale():
    config = make_config(sync_stale_hours=1, auto_sync_on_load=True)
    content = pd.DataFrame({"creator_id": ["a"], "month": ["2026-08"], "eligible": [True]})
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    assert should_auto_sync_boosting(config, content, old) is True


def test_should_not_auto_sync_when_fresh():
    config = make_config(sync_stale_hours=24)
    content = pd.DataFrame({"creator_id": ["a"], "month": ["2026-08"], "eligible": [True]})
    recent = datetime.now(timezone.utc).isoformat()
    assert should_auto_sync_boosting(config, content, recent) is False


def test_should_not_auto_sync_in_demo():
    config = make_config()
    config = AppConfig(
        mode="demo",
        base_url=config.base_url,
        crm_base_url=config.crm_base_url,
        api_key=config.api_key,
        org_id=config.org_id,
        db_path=config.db_path,
        slack_webhook_url=config.slack_webhook_url,
        settings=config.settings,
        endpoints=config.endpoints,
        field_mappings=config.field_mappings,
    )
    assert should_auto_sync_boosting(config, pd.DataFrame(), None) is False
