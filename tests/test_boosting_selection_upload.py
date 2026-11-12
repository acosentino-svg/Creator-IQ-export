import pandas as pd

from creatoriq_dashboard.boosting_selection_upload import parse_selection_csv, summarize_selections


def test_multiple_rows_same_creator_month_counted():
    csv = b"""Publisher ID,Month,Selected
1,2026-10,yes
1,2026-10,yes
2,2026-10,yes
"""
    parsed = parse_selection_csv(csv)
    stats = summarize_selections(parsed)
    assert stats["total_picks"] == 3
    assert stats["creators_with_picks"] == 2
    assert stats["creators_picked_more_than_once"] == 1


def test_selection_count_column():
    csv = b"""Publisher ID,Month,Selected,Times Selected
1,2026-10,yes,3
2,2026-10,yes,1
"""
    parsed = parse_selection_csv(csv)
    stats = summarize_selections(parsed)
    assert stats["total_picks"] == 4
    assert stats["creators_picked_more_than_once"] == 1
