from __future__ import annotations

from pathlib import Path

import pandas as pd

from creatoriq_dashboard.boosting_rules import (
    creator_has_boosting_tag,
    is_boosting_campaign,
    is_eligible_boosting_content,
    post_has_required_hashtags,
    wbp_creator_ids,
)
from creatoriq_dashboard.config import AppConfig, Settings


def make_config() -> AppConfig:
    return AppConfig(
        mode="live",
        base_url="https://api.example.test",
        crm_base_url="https://apis.example.test",
        api_key="test",
        org_id="",
        db_path=Path("/tmp/test.db"),
        slack_webhook_url="",
        settings=Settings(
            raw={
                "boosting": {
                    "creator_tags": ["WBP"],
                    "campaign_names": ["Wayfair Boosting Partnership"],
                    "campaign_name_contains": [],
                    "eligible_hashtags": ["WayfairCreator", "wayfairelevate"],
                }
            }
        ),
        endpoints={},
        field_mappings={},
    )


def test_wbp_tag_detection():
    assert creator_has_boosting_tag("Curator, WBP, Home", ["WBP"])
    assert not creator_has_boosting_tag("Curator", ["WBP"])


def test_campaign_name_exact_match():
    config = make_config()
    assert is_boosting_campaign("Wayfair Boosting Partnership", "1", config)
    assert not is_boosting_campaign("Affiliate Always-on", "2", config)


def test_hashtag_eligibility_requires_both():
    assert post_has_required_hashtags(
        "Loving this sofa #WayfairCreator #wayfairelevate",
        ["WayfairCreator", "wayfairelevate"],
    )
    assert not post_has_required_hashtags(
        "Only #WayfairCreator here",
        ["WayfairCreator", "wayfairelevate"],
    )


def test_hashtag_case_insensitive_variants():
    caption = "Check this out #WAYFAIRCREATOR and #WayfairElevate for the room"
    assert post_has_required_hashtags(caption, ["WayfairCreator", "wayfairelevate"])
    assert post_has_required_hashtags(caption, ["wayfaircreator", "WAYFAIRELEVATE"])


def test_is_eligible_from_caption_series():
    config = make_config()
    post = pd.Series({"post_caption": "New room tour #wayfairelevate and #WayfairCreator"})
    assert is_eligible_boosting_content(post, config=config)


def test_wbp_creator_ids_from_creators_table():
    config = make_config()
    creators = pd.DataFrame({"creator_id": ["1", "2"], "tags": ["WBP, Curator", "Designer"]})
    assert wbp_creator_ids(creators, config) == {"1"}
