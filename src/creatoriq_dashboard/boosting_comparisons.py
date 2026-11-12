"""Month-over-month comparison helpers for Boosting KPIs."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from .boosting_scorecard import _month_period

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


def sorted_program_months(program_long: pd.DataFrame) -> list[str]:
    if program_long.empty or "month" not in program_long.columns:
        return []
    return sorted(program_long["month"].unique(), key=lambda m: _month_period(str(m)))


def reporting_month_pair(
    months: list[str],
    *,
    timezone: str = "America/New_York",
) -> tuple[str | None, str | None]:
    """Pick (current, previous) months for KPI headline comparisons.

    When the latest data month is the in-progress calendar month (e.g. Nov 2 in
    November), headline KPIs use the last *complete* month (October) vs its prior
    (September) instead of partial November vs October.
    """
    if not months:
        return None, None
    now_month = datetime.now(ZoneInfo(timezone)).strftime("%Y-%m")
    latest = months[-1]
    if latest == now_month and len(months) >= 2:
        current = months[-2]
        previous = months[-3] if len(months) >= 3 else None
        return current, previous
    current = latest
    previous = months[-2] if len(months) >= 2 else None
    return current, previous


def month_label(month_str: str | None) -> str:
    if not month_str:
        return ""
    return _month_period(str(month_str)).strftime("%b %Y")


def compare_months(program_long: pd.DataFrame, metric: str) -> dict:
    if program_long.empty:
        return {}
    months = sorted_program_months(program_long)
    if not months:
        return {}

    curr_month, prev_month = reporting_month_pair(months)
    latest_data_month = months[-1]
    now_month = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m")
    skipped_partial = latest_data_month == now_month and len(months) >= 2 and curr_month != latest_data_month

    if not curr_month:
        return {}

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
        "latest_data_month": latest_data_month,
        "skipped_partial_month": skipped_partial,
    }


def streamlit_metric_args(comp: dict, metric: str) -> tuple[str | int | float, str | int | float | None, str | None]:
    """Build (value, delta, help) for st.metric with correct Streamlit delta % math.

    Streamlit computes MoM % as delta / (value - delta) when value and delta are numeric.
    Passing pre-formatted strings (e.g. \"824\" and \"+163\") breaks that and can show ~10%.
    """
    current = comp.get("current")
    if current is None or (isinstance(current, float) and pd.isna(current)):
        return "—", None, _comparison_help(comp)

    if metric in {
        "selection_rate",
        "retention_rate",
        "activation_rate",
        "pct_active_creators_selected",
    }:
        value = f"{float(current) * 100:.1f}%"
        delta = f"{comp['abs_change'] * 100:+.1f} pts" if comp.get("abs_change") is not None else None
        return value, delta, _comparison_help(comp)

    if metric == "roas":
        from .boosting_scorecard import format_program_value

        value = format_program_value(metric, current)
        delta = f"{comp['abs_change']:+.2f}x" if comp.get("abs_change") is not None and comp.get("previous") else None
        return value, delta, _comparison_help(comp)

    if metric in {
        "gift_card_spend",
        "cost_per_selected_asset",
        "paid_media_spend",
        "boosted_revenue",
    }:
        from .boosting_scorecard import format_program_value

        value = format_program_value(metric, current)
        delta = float(comp["abs_change"]) if comp.get("abs_change") is not None else None
        return value, delta, _comparison_help(comp)

    numeric = int(current) if float(current).is_integer() else float(current)
    delta = float(comp["abs_change"]) if comp.get("abs_change") is not None else None
    return numeric, delta, _comparison_help(comp)


def _comparison_help(comp: dict) -> str | None:
    if not comp.get("current_month"):
        return None
    cur = month_label(comp.get("current_month"))
    prev = month_label(comp.get("previous_month"))
    if prev:
        base = f"{cur} vs {prev}"
    else:
        base = cur
    if comp.get("skipped_partial_month"):
        partial = month_label(comp.get("latest_data_month"))
        return f"{base} (partial {partial} excluded from headline KPIs)"
    return base
