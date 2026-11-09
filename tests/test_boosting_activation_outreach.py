from __future__ import annotations

import pandas as pd

from creatoriq_dashboard.boosting_activation_outreach import (
    build_activation_outreach_lookup,
    build_sep_to_oct_halo_detail,
    parse_activation_outreach_csv,
    summarize_sep_to_oct_retention_by_factors,
)
from creatoriq_dashboard.boosting_scorecard import normalize_content_raw


def _content() -> pd.DataFrame:
    return normalize_content_raw(
        pd.DataFrame(
            {
                "creator_id": ["100", "100", "200", "300"],
                "creator_name": ["Alpha", "Alpha", "Beta", "Gamma"],
                "month": ["2026-08", "2026-09", "2026-09", "2026-10"],
                "content_url": ["u1", "u2", "u3", "u4"],
                "platform": ["TikTok"] * 4,
                "post_date": pd.to_datetime(
                    ["2026-08-10", "2026-09-10", "2026-09-12", "2026-10-05"],
                    utc=True,
                ),
                "eligible": [True] * 4,
                "selected": [True, False, False, False],
                "selection_date": pd.NaT,
                "boosted": [False] * 4,
                "gift_card_cost": [0] * 4,
                "paid_spend": [0] * 4,
                "boosted_revenue": [0] * 4,
                "impressions": [0] * 4,
                "engagements": [0] * 4,
                "clicks": [0] * 4,
                "featured_category": [""] * 4,
                "campaign": ["Wayfair Creators Boosting Partnership"] * 4,
            }
        )
    )


def test_parse_activation_outreach_publisher_id():
    raw = pd.DataFrame({"Creator": ["Jane"], "Publisher ID": ["555"], "Tags": ["Sept lapsed"]})
    parsed = parse_activation_outreach_csv(raw)
    assert parsed.iloc[0]["publisher_id"] == "555"
    assert parsed.iloc[0]["creator_name"] == "Jane"


def test_halo_detail_marks_outreach_and_jul_sep_selection():
    content = _content()
    lookup = build_activation_outreach_lookup(
        ("sept_activation_outreach", pd.DataFrame({"CreatorId": ["200"], "Creator": ["Beta"], "Tags": ["x"]}))
    )
    detail = build_sep_to_oct_halo_detail(content, outreach_lookup=lookup)
    alpha = detail[detail["creator_id"] == "100"].iloc[0]
    beta = detail[detail["creator_id"] == "200"].iloc[0]
    assert bool(alpha["ever_selected_jul_sep"])
    assert not bool(alpha["continued_sep_to_oct"])
    assert bool(beta["sept_activation_outreach"])
    assert bool(beta["fell_off_sep_to_oct"])

    factors = summarize_sep_to_oct_retention_by_factors(detail)
    outreach_yes = factors[
        (factors["factor"] == "Sept Activation Outreach") & (factors["segment"] == "Yes — on outreach list")
    ]
    assert not outreach_yes.empty
    assert int(outreach_yes.iloc[0]["sep_actives"]) == 1
