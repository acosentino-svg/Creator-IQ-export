"""Boosting funnel stage counts for a given month."""
from __future__ import annotations

import pandas as pd

from .boosting_scorecard import normalize_content_raw


def build_funnel_for_month(content: pd.DataFrame, month: str) -> pd.DataFrame:
    df = normalize_content_raw(content)
    if df.empty:
        return pd.DataFrame(columns=["stage", "count", "conversion_from_previous"])

    month_df = df[df["month"] == month]
    eligible_content = month_df[month_df["eligible"]]
    selected_content = eligible_content[eligible_content["selected"]]
    boosted_content = selected_content[selected_content["boosted"]]

    active_creators = eligible_content["creator_id"].nunique()
    eligible_creators_ever = df[df["month"] <= month]["creator_id"].nunique()
    selected_creators = selected_content[selected_content["selected"]]["creator_id"].nunique()

    stages = [
        ("Eligible Boosting Creators (cumulative)", int(eligible_creators_ever)),
        ("Monthly Active Creators", int(active_creators)),
        ("Eligible Content Pieces", int(len(eligible_content))),
        ("Selected Content Pieces", int(len(selected_content))),
        ("Boosted Content Pieces", int(len(boosted_content))),
        ("Creators With ≥1 Selection", int(selected_creators)),
    ]

    rows: list[dict] = []
    prev_count = None
    for stage, count in stages:
        conv = None
        if prev_count is not None and prev_count > 0:
            conv = count / prev_count
        rows.append({"stage": stage, "count": count, "conversion_from_previous": conv})
        prev_count = count

    return pd.DataFrame(rows)
