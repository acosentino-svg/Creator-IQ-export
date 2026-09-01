from __future__ import annotations

import pandas as pd
import pytest

from creatoriq_dashboard.boosting_creatoriq import (
    merge_api_with_supplements,
    posts_to_boosting_content,
)
from creatoriq_dashboard.boosting_rules import is_boosting_campaign
from creatoriq_dashboard.boosting_demo_data import generate_demo_boosting_content
from creatoriq_dashboard.boosting_scorecard import (
    build_creator_monthly,
    build_program_monthly,
    compute_creator_movement,
    merge_content_raw,
    normalize_content_raw,
    parse_content_raw_csv,
)
from creatoriq_dashboard.config import AppConfig, Settings


def make_config(**boosting_overrides) -> AppConfig:
    boosting = {
        "creator_tags": ["WBP"],
        "campaign_names": ["Wayfair Boosting Partnership"],
        "campaign_name_contains": [],
        "campaign_ids": [],
        "eligible_hashtags": ["WayfairCreator", "wayfairelevate"],
        "default_eligible_if_in_campaign": False,
        **boosting_overrides,
    }
    return AppConfig(
        mode="live",
        base_url="https://api.example.test",
        crm_base_url="https://apis.example.test",
        api_key="test-key",
        org_id="",
        db_path=pytest.importorskip("pathlib").Path("/tmp/test.db"),
        slack_webhook_url="",
        settings=Settings(raw={"boosting": boosting}),
        endpoints={"resources": {"campaign_activity": {}}},
        field_mappings={},
    )


def test_is_boosting_campaign_by_name():
    config = make_config()
    assert is_boosting_campaign("Wayfair Boosting Partnership", "1", config)
    assert not is_boosting_campaign("Affiliate Always-on", "2", config)


def test_is_boosting_campaign_by_id():
    config = make_config(campaign_ids=["99"])
    assert is_boosting_campaign("Anything", "99", config)
    assert not is_boosting_campaign("Boosting", "1", config)


def test_posts_to_boosting_content_maps_fields():
    config = make_config()
    posts = pd.DataFrame(
        {
            "post_id": ["p1"],
            "creator_id": ["pub_001"],
            "campaign_id": ["c1"],
            "campaign_name": ["Wayfair Boosting Partnership"],
            "platform": ["TikTok"],
            "posted_at": [pd.Timestamp("2026-08-15", tz="UTC")],
            "post_url": ["https://tiktok.com/@x/video/1"],
            "post_caption": ["Room refresh #WayfairCreator #wayfairelevate"],
            "views": [10000],
            "likes": [500],
            "comments": [40],
            "engagement": [0],
            "link_clicks": [120],
            "boosting_selected": [True],
            "boosting_boosted": [True],
            "boosting_gift_card_cost": [100],
            "boosting_paid_spend": [400],
            "boosting_revenue": [1200],
            "boosting_category": ["Bedding"],
        }
    )
    out = posts_to_boosting_content(posts, config)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["creator_id"] == "pub_001"
    assert row["month"] == "2026-08"
    assert row["eligible"] == True
    assert row["selected"] == True
    assert row["gift_card_cost"] == 100
    assert row["paid_spend"] == 400
    assert row["boosted_revenue"] == 1200
    assert row["impressions"] == 10000
    assert row["engagements"] == 540


def test_posts_without_both_hashtags_not_eligible():
    config = make_config()
    posts = pd.DataFrame(
        {
            "post_id": ["p1"],
            "creator_id": ["pub_001"],
            "campaign_id": ["c1"],
            "campaign_name": ["Wayfair Boosting Partnership"],
            "platform": ["TikTok"],
            "posted_at": [pd.Timestamp("2026-08-15", tz="UTC")],
            "post_url": ["https://tiktok.com/@x/video/1"],
            "post_caption": ["Only #WayfairCreator here"],
            "views": [100],
            "likes": [10],
            "comments": [1],
            "engagement": [0],
            "link_clicks": [0],
        }
    )
    out = posts_to_boosting_content(posts, config)
    assert len(out) == 1
    assert out.iloc[0]["eligible"] == False


def test_wbp_tag_includes_creator_outside_campaign():
    config = make_config()
    posts = pd.DataFrame(
        {
            "post_id": ["p1"],
            "creator_id": ["pub_wbp"],
            "campaign_id": ["c9"],
            "campaign_name": ["Affiliate Always-on"],
            "platform": ["Instagram"],
            "posted_at": [pd.Timestamp("2026-08-10", tz="UTC")],
            "post_url": ["https://instagram.com/p/1"],
            "post_caption": ["#WayfairCreator #wayfairelevate"],
            "views": [1000],
            "likes": [50],
            "comments": [5],
            "engagement": [0],
            "link_clicks": [0],
        }
    )
    creators = pd.DataFrame({"creator_id": ["pub_wbp"], "tags": ["WBP"]})
    out = posts_to_boosting_content(posts, config, creators=creators)
    assert len(out) == 1
    assert out.iloc[0]["eligible"] == True


def test_merge_api_with_supplements_keeps_csv_paid_metrics():
    api = normalize_content_raw(
        pd.DataFrame(
            {
                "creator_id": ["pub_001"],
                "month": ["2026-08"],
                "content_url": ["https://example.com/1"],
                "platform": ["TikTok"],
                "post_date": [pd.Timestamp("2026-08-01", tz="UTC")],
                "eligible": [True],
                "selected": [False],
                "selection_date": [pd.NaT],
                "boosted": [False],
                "gift_card_cost": [0],
                "paid_spend": [0],
                "boosted_revenue": [0],
                "impressions": [0],
                "engagements": [0],
                "clicks": [0],
                "featured_category": [""],
                "campaign": ["Wayfair Boosting Partnership"],
            }
        )
    )
    supplement = api.copy()
    supplement["selected"] = True
    supplement["paid_spend"] = 500
    supplement["boosted_revenue"] = 2000
    merged = merge_api_with_supplements(api, supplement)
    assert merged.iloc[0]["paid_spend"] == 500
    assert merged.iloc[0]["boosted_revenue"] == 2000
    assert merged.iloc[0]["selected"] == True


def test_retention_movement_counts():
    content = pd.DataFrame(
        {
            "creator_id": ["A", "A", "B", "C", "C"],
            "month": ["2026-07", "2026-08", "2026-07", "2026-08", "2026-08"],
            "content_url": ["u1", "u2", "u3", "u4", "u5"],
            "platform": ["TikTok"] * 5,
            "post_date": pd.to_datetime(
                ["2026-07-10", "2026-08-10", "2026-07-12", "2026-08-05", "2026-08-20"],
                utc=True,
            ),
            "eligible": [True] * 5,
            "selected": [True, False, True, True, False],
            "selection_date": pd.NaT,
            "boosted": [False] * 5,
            "gift_card_cost": [0] * 5,
            "paid_spend": [0] * 5,
            "boosted_revenue": [0] * 5,
            "impressions": [0] * 5,
            "engagements": [0] * 5,
            "clicks": [0] * 5,
            "featured_category": [""] * 5,
            "campaign": ["Wayfair Boosting Partnership"] * 5,
        }
    )
    content = normalize_content_raw(content)
    movement = compute_creator_movement(content, "2026-08")
    segments = dict(zip(movement["segment"], movement["creators"]))
    assert segments["Retained"] == 1  # A
    assert segments["New"] == 1  # C (first active Aug)
    assert segments["Lapsed"] == 1  # B
    assert segments["Total Active"] == 2  # A + C


def test_creator_monthly_active_not_same_as_selected():
    content = normalize_content_raw(
        pd.DataFrame(
            {
                "creator_id": ["B"],
                "month": ["2026-08"],
                "content_url": ["u1"],
                "platform": ["IG"],
                "post_date": [pd.Timestamp("2026-08-01", tz="UTC")],
                "eligible": [True],
                "selected": [False],
                "selection_date": [pd.NaT],
                "boosted": [False],
                "gift_card_cost": [0],
                "paid_spend": [0],
                "boosted_revenue": [0],
                "impressions": [0],
                "engagements": [0],
                "clicks": [0],
                "featured_category": [""],
                "campaign": ["Wayfair Boosting Partnership"],
            }
        )
    )
    monthly = build_creator_monthly(content)
    assert len(monthly) == 1
    assert monthly.iloc[0]["eligible_pieces"] == 1
    assert monthly.iloc[0]["selected_pieces"] == 0


def test_program_monthly_roas_excludes_gift_cards():
    content = normalize_content_raw(
        pd.DataFrame(
            {
                "creator_id": ["A"],
                "month": ["2026-08"],
                "content_url": ["u1"],
                "platform": ["TikTok"],
                "post_date": [pd.Timestamp("2026-08-01", tz="UTC")],
                "eligible": [True],
                "selected": [True],
                "selection_date": [pd.NaT],
                "boosted": [True],
                "gift_card_cost": [100],
                "paid_spend": [500],
                "boosted_revenue": [1500],
                "impressions": [0],
                "engagements": [0],
                "clicks": [0],
                "featured_category": [""],
                "campaign": ["Wayfair Boosting Partnership"],
            }
        )
    )
    program = build_program_monthly(content)
    roas = program.loc[program["metric"] == "roas", "value"].iloc[0]
    assert roas == pytest.approx(3.0)


def test_demo_data_generates_multiple_months():
    content = generate_demo_boosting_content(months=("2026-06", "2026-07", "2026-08"))
    assert content["month"].nunique() == 3
    assert not build_program_monthly(content).empty


def test_parse_content_raw_csv_aliases():
    raw = pd.DataFrame(
        {
            "Publisher ID": ["pub_1"],
            "Month": ["Aug 2026"],
            "Content URL": ["https://x.com/1"],
            "Platform": ["TikTok"],
            "Post Date": ["2026-08-01"],
            "Eligible?": ["Yes"],
            "Selected?": ["No"],
            "Gift Card Cost": ["$0"],
            "Paid Spend": ["$0"],
            "Boosted Revenue": ["$0"],
        }
    )
    parsed = parse_content_raw_csv(raw)
    assert parsed.iloc[0]["creator_id"] == "pub_1"
    assert parsed.iloc[0]["month"] == "2026-08"
    assert parsed.iloc[0]["eligible"] == True


def test_merge_content_raw_by_url_month():
    a = normalize_content_raw(
        pd.DataFrame(
            {
                "creator_id": ["pub_1"],
                "month": ["2026-08"],
                "content_url": ["https://example.com/1"],
                "platform": ["TikTok"],
                "post_date": [pd.Timestamp("2026-08-01", tz="UTC")],
                "eligible": [True],
                "selected": [False],
                "selection_date": [pd.NaT],
                "boosted": [False],
                "gift_card_cost": [0],
                "paid_spend": [100],
                "boosted_revenue": [0],
                "impressions": [0],
                "engagements": [0],
                "clicks": [0],
                "featured_category": [""],
                "campaign": ["Wayfair Boosting Partnership"],
            }
        )
    )
    b = a.copy()
    b["paid_spend"] = 999
    merged = merge_content_raw(a, b)
    assert merged.iloc[0]["paid_spend"] == 999
