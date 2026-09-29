"""Tests for halo effect posted + selected merge."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from creatoriq_dashboard.boosting_halo_effect import (
    build_data_quality_checklist,
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


def test_data_quality_checklist_rows():
    diag = {
        "posted_rows": 7959,
        "selected_unique_assets": 1403,
        "posts_matched_to_selection": 792,
        "selection_match_rate_on_posts": 0.1,
        "selected_posts": 792,
        "eligible_posts": 7678,
        "selected_not_in_posted": 611,
    }
    table = build_data_quality_checklist(diag)
    assert list(table.columns) == ["Check", "Result"]
    assert len(table) == 5
    assert "7,959" in table.iloc[0]["Result"]


def test_export_csv_dir_writes_data_quality(tmp_path: Path):
    from creatoriq_dashboard.boosting_halo_effect import export_halo_effect_csv_dir

    posted = tmp_path / "posted.csv"
    selected = tmp_path / "selected.csv"
    posted.write_text(
        "Post Id,Creator Name,SocialHandle,Post Description,Post Link,Post Date,Publisher Id\n"
        '1,a,x,"#WayfairCreator #wayfairelevate",https://tiktok.com/@x/video/99/,2026-01-10 12:00:00,1\n',
        encoding="utf-8",
    )
    selected.write_text(
        "Creator Name,Content Used,Duration of Usage\n"
        "a,https://www.tiktok.com/@x/video/99,1/5/2026\n",
        encoding="utf-8",
    )
    out = tmp_path / "sheets"
    export_halo_effect_csv_dir(str(posted), str(selected), str(out))
    dq = pd.read_csv(out / "01_data_quality.csv")
    assert "Check" in dq.columns
    assert len(dq) == 5
