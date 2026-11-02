"""Tests for October brief theme tagging from captions."""
from __future__ import annotations

import pandas as pd

from creatoriq_dashboard.boosting_brief_themes import (
    add_brief_theme_columns,
    summarize_brief_themes_by_month,
    text_matches_brief_theme,
)


def test_halloween_and_fall_case_insensitive():
    assert text_matches_brief_theme("Spooky #HALLOWEEN decor", "halloween")
    assert text_matches_brief_theme("Cozy fall refresh", "fall_styling")


def test_wayfair_verified_variants():
    assert text_matches_brief_theme("Sofa is Wayfair Verified ✔️", "wayfair_verified")


def test_summarize_by_month():
    df = pd.DataFrame(
        {
            "month": ["2026-10", "2026-10", "2026-09"],
            "post_caption": [
                "Cozy fall room #WayfairCreator #WayfairElevate",
                "Halloween porch #WayfairCreator #WayfairElevate",
                "Summer patio #WayfairCreator #WayfairElevate",
            ],
            "eligible": [True, True, True],
            "selected": [True, False, False],
        }
    )
    summary = summarize_brief_themes_by_month(df)
    oct_row = summary[summary["month"] == "2026-10"].iloc[0]
    assert oct_row["eligible_posts"] == 2
    assert oct_row["halloween_posts"] == 1
    assert oct_row["fall_styling_posts"] == 1
    assert oct_row["any_brief_theme_posts"] == 2


def test_add_brief_columns():
    tagged = add_brief_theme_columns(
        pd.DataFrame({"post_caption": ["Pet bed for my puppy from Wayfair"]})
    )
    assert bool(tagged.iloc[0]["brief_pet"])
