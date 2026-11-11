from creatoriq_dashboard.creator_sales import load_creator_sales, merge_sales_into_summary
import pandas as pd


def test_merge_sales_flags_transactions():
    summary = pd.DataFrame({"creator_id": ["12784222", "999"], "name": ["A", "B"]})
    sales = load_creator_sales()
    out = merge_sales_into_summary(summary, sales)
    row = out[out["creator_id"] == "12784222"].iloc[0]
    assert bool(row["has_transactions"])
    assert row["order_count"] > 0
