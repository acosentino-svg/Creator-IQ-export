"""Tests for halo effect posted + selected merge."""
from __future__ import annotations

import pandas as pd

from creatoriq_dashboard.boosting_halo_effect import (
    merge_halo_effect_posts_and_selections,
    parse_halo_posted_csv,
    parse_halo_selected_csv,
)


def test_url_key_matches_tiktok_and_instagram():
    sel = parse_halo_selected_csv(
        pd.DataFrame(
            {
                "Creator Name": ["a"],
                "Content Used": ["https://www.tiktok.com/@x/video/12345"],
                "Duration of Usage": ["1/5/2026"],
            }
        )
    )
    posted = parse_halo_posted_csv(
        pd.DataFrame(
            {
                "Post Id": [1],
                "Creator Name": ["a"],
                "SocialHandle": ["x"],
                "Post Description": ["#WayfairCreator #wayfairelevate"],
                "Post Link": ["https://tiktok.com/@x/video/12345/"],
                "Post Date": ["2026-01-10 12:00:00"],
                "Publisher Id": [99],
            }
        )
    )
    content, diag = merge_halo_effect_posts_and_selections(posted, sel)
    assert diag["posts_matched_to_selection"] == 1
    assert bool(content.iloc[0]["selected"])
    assert bool(content.iloc[0]["eligible"])
