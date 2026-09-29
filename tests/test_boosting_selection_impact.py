"""Tests for selection impact analytics."""
from __future__ import annotations

import pandas as pd

from creatoriq_dashboard.boosting_selection_impact import (
    build_creator_posting_velocity,
    build_creator_selection_timeline,
    build_monthly_selection_retention,
    summarize_selection_impact,
    summarize_timeline_segments,
)
from creatoriq_dashboard.boosting_scorecard import normalize_content_raw


def _sample_content() -> pd.DataFrame:
    return normalize_content_raw(
        pd.DataFrame(
            {
                "creator_id": ["A", "A", "A", "B", "B", "C", "C"],
                "month": ["2026-06", "2026-07", "2026-08", "2026-07", "2026-08", "2026-07", "2026-08"],
                "content_url": ["u1", "u2", "u3", "u4", "u5", "u6", "u7"],
                "platform": ["TikTok"] * 7,
                "post_date": pd.to_datetime(
                    [
                        "2026-06-10",
                        "2026-07-10",
                        "2026-08-10",
                        "2026-07-12",
                        "2026-08-12",
                        "2026-07-15",
                        "2026-08-15",
                    ],
                    utc=True,
                ),
                "eligible": [True] * 7,
                "selected": [False, True, True, False, False, True, False],
                "selection_date": pd.NaT,
                "boosted": [False] * 7,
                "gift_card_cost": [0] * 7,
                "paid_spend": [0] * 7,
                "boosted_revenue": [0] * 7,
                "impressions": [0] * 7,
                "engagements": [0] * 7,
                "clicks": [0] * 7,
                "featured_category": [""] * 7,
                "campaign": ["Wayfair Creators Boosting Partnership"] * 7,
            }
        )
    )


def test_retention_split_selected_vs_not():
    content = _sample_content()
    split = build_monthly_selection_retention(content)
    aug = split[split["month"] == "2026-08"]
    no_sel = aug[aug["segment"] == "No selection last month"].iloc[0]
    # July: B posted but was not selected; B also posts in August.
    assert int(no_sel["prior_month_creators"]) == 1
    assert int(no_sel["retained"]) == 1
    assert no_sel["falloff_rate"] == 0.0

    with_sel = aug[aug["segment"] == "Had selection last month"].iloc[0]
    assert int(with_sel["prior_month_creators"]) == 2  # A and C
    assert int(with_sel["retained"]) == 2
    assert with_sel["retention_rate"] == 1.0


def test_posting_velocity_before_after_first_selection():
    content = _sample_content()
    velocity = build_creator_posting_velocity(content)
    a = velocity[velocity["creator_id"] == "A"].iloc[0]
    assert a["first_selection_month"] == "2026-07"
    assert a["pre_active_months"] == 1
    assert a["post_active_months"] == 1
    assert a["pre_avg_eligible_pieces"] == 1.0
    assert a["post_avg_eligible_pieces"] == 1.0
    assert a["post_minus_pre"] == 0.0

    b = velocity[velocity["creator_id"] == "B"].iloc[0]
    assert not b["ever_selected"]


def test_timeline_past_selector_went_dark():
    content = normalize_content_raw(
        pd.DataFrame(
            {
                "creator_id": ["D", "D"],
                "month": ["2026-01", "2026-06"],
                "content_url": ["u1", "u2"],
                "platform": ["TikTok"] * 2,
                "post_date": pd.to_datetime(["2026-01-15", "2026-06-10"], utc=True),
                "eligible": [True, True],
                "selected": [True, False],
                "selection_date": pd.to_datetime(["2026-01-20"], utc=True).tolist() + [pd.NaT],
                "boosted": [False] * 2,
                "gift_card_cost": [0] * 2,
                "paid_spend": [0] * 2,
                "boosted_revenue": [0] * 2,
                "impressions": [0] * 2,
                "engagements": [0] * 2,
                "clicks": [0] * 2,
                "featured_category": [""] * 2,
                "campaign": ["Wayfair Creators Boosting Partnership"] * 2,
            }
        )
    )
    as_of = pd.Timestamp("2026-09-15", tz="UTC")
    timeline = build_creator_selection_timeline(
        content, as_of=as_of, drought_days=90, active_days=30
    )
    row = timeline.iloc[0]
    assert row["segment"] == "Past selector — went dark"
    summary = summarize_timeline_segments(timeline)
    assert int(summary.iloc[0]["creators"]) == 1
    assert int(summary.iloc[0]["still_posting"]) == 0


def test_summarize_selection_impact_keys():
    content = _sample_content()
    summary = summarize_selection_impact(content)
    assert summary["latest_month"] == "2026-08"
    assert summary["pct_active_creators_selected"] is not None
    assert summary["falloff_rate_no_selection_prior_month"] == 0.0
