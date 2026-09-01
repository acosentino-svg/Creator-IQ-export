"""Month-over-month comparison helpers for Boosting KPIs."""
from __future__ import annotations

import pandas as pd


RATE_METRICS = {
    "selection_rate",
    "retention_rate",
    "activation_rate",
    "pct_active_creators_selected",
}

HIGHER_IS_BETTER = {
    "active_boosting_creators",
    "eligible_content_pieces",
    "selected_content_pieces",
    "selection_rate",
    "retention_rate",
    "boosted_revenue",
    "roas",
    "pct_active_creators_selected",
}

LOWER_IS_BETTER = {"cost_per_selected_asset"}


def compare_months(program_long: pd.DataFrame, metric: str) -> dict:
    if program_long.empty:
        return {}
    months = sorted(program_long["month"].unique())
    if not months:
        return {}
    curr_month = months[-1]
    prev_month = months[-2] if len(months) > 1 else None

    curr_row = program_long[(program_long["month"] == curr_month) & (program_long["metric"] == metric)]
    if curr_row.empty:
        return {}
    current = curr_row.iloc[0]["value"]
    if pd.isna(current):
        current = None

    previous = None
    if prev_month:
        prev_row = program_long[(program_long["month"] == prev_month) & (program_long["metric"] == metric)]
        if not prev_row.empty and pd.notna(prev_row.iloc[0]["value"]):
            previous = float(prev_row.iloc[0]["value"])

    abs_change = None
    pct_change = None
    if current is not None and previous is not None:
        abs_change = float(current) - previous
        if metric in RATE_METRICS:
            pct_change = abs_change  # percentage points for rates
        elif previous != 0:
            pct_change = abs_change / previous

    direction = None
    if abs_change is not None:
        if metric in LOWER_IS_BETTER:
            direction = "positive" if abs_change < 0 else "negative" if abs_change > 0 else "neutral"
        elif metric in HIGHER_IS_BETTER:
            direction = "positive" if abs_change > 0 else "negative" if abs_change < 0 else "neutral"

    return {
        "current": current,
        "previous": previous,
        "abs_change": abs_change,
        "pct_change": pct_change,
        "direction": direction,
        "current_month": curr_month,
        "previous_month": prev_month,
    }
