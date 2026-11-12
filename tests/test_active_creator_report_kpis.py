import pandas as pd

from creatoriq_dashboard.active_creator_report_kpis import compute_active_creator_overview


def test_active_in_range_excludes_txn_only():
    summary = pd.DataFrame(
        {
            "creator_id": ["1", "2", "3"],
            "name": ["A", "B", "C"],
            "posts_in_range": [1, 0, 0],
            "links_in_range": [0, 2, 0],
            "has_transactions": [True, False, True],
        }
    )
    ov = compute_active_creator_overview(summary, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), None)
    assert ov["active_creators"] == 2
    assert ov["posting_creators"] == 1
    assert ov["linking_creators"] == 1
