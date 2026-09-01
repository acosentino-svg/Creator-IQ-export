"""Boosting program scorecard: content-level raw data → creator monthly → program monthly.

Designed so monthly exports can be pasted/uploaded without changing calculation logic.
Publisher ID (`creator_id`) is the stable creator key — handles can change.
"""
from __future__ import annotations

import re
from typing import BinaryIO

import numpy as np
import pandas as pd

CONTENT_RAW_COLUMNS = [
    "creator_id",
    "month",
    "content_url",
    "platform",
    "post_date",
    "eligible",
    "selected",
    "selection_date",
    "boosted",
    "gift_card_cost",
    "paid_spend",
    "boosted_revenue",
    "impressions",
    "engagements",
    "clicks",
    "featured_category",
    "campaign",
]

_CREATOR_ID_ALIASES = (
    "creator_id",
    "publisherid",
    "publisher id",
    "publisher_id",
    "creator / publisher id",
    "creator/publisher id",
)

_MONTH_ALIASES = ("month", "reporting month", "report month")

_CONTENT_URL_ALIASES = ("content_url", "content url", "url", "post url", "content link")

_PLATFORM_ALIASES = ("platform", "channel", "social platform")

_POST_DATE_ALIASES = ("post_date", "post date", "posted at", "publish date")

_ELIGIBLE_ALIASES = ("eligible", "eligible?", "is eligible", "meets boosting requirements")

_SELECTED_ALIASES = ("selected", "selected?", "is selected", "paid team selected")

_SELECTION_DATE_ALIASES = ("selection_date", "selection date", "date selected")

_BOOSTED_ALIASES = ("boosted", "boosted?", "is boosted", "launched in paid")

_GIFT_CARD_ALIASES = ("gift_card_cost", "gift card cost", "gift card", "compensation")

_PAID_SPEND_ALIASES = ("paid_spend", "paid spend", "media spend", "spend")

_BOOSTED_REVENUE_ALIASES = ("boosted_revenue", "boosted revenue", "revenue", "attributed revenue")

_IMPRESSIONS_ALIASES = ("impressions", "paid impressions")

_ENGAGEMENTS_ALIASES = ("engagements", "engagement", "likes comments")

_CLICKS_ALIASES = ("clicks", "link clicks")

_CATEGORY_ALIASES = ("featured_category", "featured category", "category", "content category")

_CAMPAIGN_ALIASES = ("campaign", "campaign / push", "campaign/push", "push", "campaign push")


def _normalize_header(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(name).strip().lower()).strip()


def _find_column(columns: list[str], aliases: tuple[str, ...]) -> str | None:
    normalized = {_normalize_header(c): c for c in columns}
    for alias in aliases:
        key = _normalize_header(alias)
        if key in normalized:
            return normalized[key]
    return None


def _parse_bool(series: pd.Series) -> pd.Series:
    truthy = {"true", "yes", "y", "1", "t", "selected", "eligible", "boosted"}
    return series.map(
        lambda v: (
            True
            if str(v).strip().lower() in truthy
            else False if str(v).strip().lower() in {"false", "no", "n", "0", "f", ""} else pd.NA
        )
    )


def _parse_money(series: pd.Series) -> pd.Series:
    cleaned = (
        series.astype(str)
        .str.replace(r"[$,\s]", "", regex=True)
        .replace({"nan": np.nan, "None": np.nan, "": np.nan, "-": np.nan})
    )
    return pd.to_numeric(cleaned, errors="coerce").fillna(0.0)


def _parse_int(series: pd.Series) -> pd.Series:
    cleaned = series.astype(str).str.replace(r"[,\s]", "", regex=True)
    return pd.to_numeric(cleaned, errors="coerce").fillna(0).astype(int)


def _parse_month(value) -> str | None:
    if pd.isna(value):
        return None
    if isinstance(value, pd.Period):
        return str(value)
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return None
    ts = pd.to_datetime(text, errors="coerce")
    if pd.notna(ts):
        return ts.strftime("%Y-%m")
    # Try "Aug 2026" style
    ts2 = pd.to_datetime(text, format="%b %Y", errors="coerce")
    if pd.notna(ts2):
        return ts2.strftime("%Y-%m")
    return text


def _month_period(month_str: str) -> pd.Period:
    return pd.Period(month_str, freq="M")


def _prior_month(month_str: str) -> str:
    return str(_month_period(month_str) - 1)


def _safe_div(numerator: float, denominator: float) -> float | None:
    if denominator == 0 or pd.isna(denominator):
        return None
    return numerator / denominator


def _format_roas(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:.1f}x"


def normalize_content_raw(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce a content-raw table to the canonical schema and types."""
    if df is None or df.empty:
        return pd.DataFrame(columns=CONTENT_RAW_COLUMNS)

    out = df.copy()
    for col in CONTENT_RAW_COLUMNS:
        if col not in out.columns:
            out[col] = np.nan

    out["creator_id"] = out["creator_id"].astype(str).str.strip()
    out = out[out["creator_id"].ne("") & out["creator_id"].ne("nan")]

    out["month"] = out["month"].map(_parse_month)
    out = out[out["month"].notna()]

    out["content_url"] = out["content_url"].astype(str).str.strip()
    out["platform"] = out["platform"].fillna("").astype(str).str.strip()
    out["post_date"] = pd.to_datetime(out["post_date"], errors="coerce", utc=True)
    out["selection_date"] = pd.to_datetime(out["selection_date"], errors="coerce", utc=True)

    for col in ("eligible", "selected", "boosted"):
        out[col] = _parse_bool(out[col]).fillna(False).astype(bool)

    for col in ("gift_card_cost", "paid_spend", "boosted_revenue"):
        out[col] = _parse_money(out[col])

    for col in ("impressions", "engagements", "clicks"):
        out[col] = _parse_int(out[col])

    out["featured_category"] = out["featured_category"].fillna("").astype(str).str.strip()
    out["campaign"] = out["campaign"].fillna("").astype(str).str.strip()

    # Derive month from post_date when missing (after eligible filter we'll use explicit month)
    missing_month = out["month"].isna() & out["post_date"].notna()
    if missing_month.any():
        out.loc[missing_month, "month"] = out.loc[missing_month, "post_date"].dt.strftime("%Y-%m")

    return out[CONTENT_RAW_COLUMNS].reset_index(drop=True)


def parse_content_raw_csv(source: str | bytes | BinaryIO | pd.DataFrame) -> pd.DataFrame:
    """Parse a monthly CreatorIQ / content-tracker CSV export into canonical schema."""
    if isinstance(source, pd.DataFrame):
        raw = source.copy()
    elif isinstance(source, str):
        raw = pd.read_csv(source)
    else:
        raw = pd.read_csv(source)

    if raw.empty:
        return pd.DataFrame(columns=CONTENT_RAW_COLUMNS)

    columns = list(raw.columns)
    mapping: dict[str, str | None] = {
        "creator_id": _find_column(columns, _CREATOR_ID_ALIASES),
        "month": _find_column(columns, _MONTH_ALIASES),
        "content_url": _find_column(columns, _CONTENT_URL_ALIASES),
        "platform": _find_column(columns, _PLATFORM_ALIASES),
        "post_date": _find_column(columns, _POST_DATE_ALIASES),
        "eligible": _find_column(columns, _ELIGIBLE_ALIASES),
        "selected": _find_column(columns, _SELECTED_ALIASES),
        "selection_date": _find_column(columns, _SELECTION_DATE_ALIASES),
        "boosted": _find_column(columns, _BOOSTED_ALIASES),
        "gift_card_cost": _find_column(columns, _GIFT_CARD_ALIASES),
        "paid_spend": _find_column(columns, _PAID_SPEND_ALIASES),
        "boosted_revenue": _find_column(columns, _BOOSTED_REVENUE_ALIASES),
        "impressions": _find_column(columns, _IMPRESSIONS_ALIASES),
        "engagements": _find_column(columns, _ENGAGEMENTS_ALIASES),
        "clicks": _find_column(columns, _CLICKS_ALIASES),
        "featured_category": _find_column(columns, _CATEGORY_ALIASES),
        "campaign": _find_column(columns, _CAMPAIGN_ALIASES),
    }

    if not mapping["creator_id"]:
        raise ValueError("Could not find Creator / Publisher ID column in upload.")

    out = pd.DataFrame()
    for target, source_col in mapping.items():
        if source_col:
            out[target] = raw[source_col]
        else:
            out[target] = np.nan

    return normalize_content_raw(out)


def merge_content_raw(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Append/replace monthly content rows. Same content_url + month replaces prior row."""
    base = pd.DataFrame(columns=CONTENT_RAW_COLUMNS) if existing is None or existing.empty else normalize_content_raw(existing)
    incoming = pd.DataFrame(columns=CONTENT_RAW_COLUMNS) if new is None or new.empty else normalize_content_raw(new)
    if incoming.empty:
        return base.reset_index(drop=True)

    combined = pd.concat([base, incoming], ignore_index=True)
    if "content_url" in combined.columns and combined["content_url"].notna().any():
        combined = combined.drop_duplicates(subset=["content_url", "month"], keep="last")
    else:
        combined = combined.drop_duplicates(keep="last")
    return combined.sort_values(["month", "creator_id"]).reset_index(drop=True)


def _eligible_content(content: pd.DataFrame) -> pd.DataFrame:
    if content.empty:
        return content.copy()
    return content[content["eligible"]].copy()


def _active_creators_by_month(eligible: pd.DataFrame) -> dict[str, set[str]]:
    if eligible.empty:
        return {}
    grouped = eligible.groupby("month")["creator_id"].apply(lambda s: set(s.unique()))
    return grouped.to_dict()


def _creator_first_active_month(eligible: pd.DataFrame) -> dict[str, str]:
    if eligible.empty:
        return {}
    first = (
        eligible.groupby("creator_id")["month"]
        .min()
        .to_dict()
    )
    return first


def classify_creator_retention(
    creator_id: str,
    month: str,
    active_by_month: dict[str, set[str]],
    first_active: dict[str, str],
) -> str | None:
    """Return Retained | New | Reactivated for active creators; None if not active this month."""
    current = active_by_month.get(month, set())
    if creator_id not in current:
        return None

    prior = _prior_month(month)
    if creator_id in active_by_month.get(prior, set()):
        return "Retained"

    first = first_active.get(creator_id)
    if first == month:
        return "New"

    return "Reactivated"


def build_creator_monthly(
    content: pd.DataFrame,
    creator_names: dict[str, str] | None = None,
) -> pd.DataFrame:
    """One row per active boosting creator per month."""
    eligible = _eligible_content(normalize_content_raw(content))
    if eligible.empty:
        return pd.DataFrame(
            columns=[
                "month",
                "creator_id",
                "creator_name",
                "eligible_pieces",
                "selected_pieces",
                "selection_rate",
                "gift_card_cost",
                "paid_spend",
                "boosted_revenue",
                "roas",
                "active_last_month",
                "retention_status",
            ]
        )

    active_by_month = _active_creators_by_month(eligible)
    first_active = _creator_first_active_month(eligible)
    names = creator_names or {}

    rows: list[dict] = []
    for month in sorted(eligible["month"].unique()):
        month_df = eligible[eligible["month"] == month]
        prior = _prior_month(month)
        prior_active = active_by_month.get(prior, set())

        for creator_id, grp in month_df.groupby("creator_id"):
            eligible_count = len(grp)
            selected_grp = grp[grp["selected"]]
            selected_count = len(selected_grp)
            selection_rate = _safe_div(selected_count, eligible_count)

            gift_card = float(selected_grp["gift_card_cost"].sum())
            spend = float(grp["paid_spend"].sum())
            revenue = float(grp["boosted_revenue"].sum())
            roas = _safe_div(revenue, spend)

            status = classify_creator_retention(creator_id, month, active_by_month, first_active)
            rows.append(
                {
                    "month": month,
                    "creator_id": creator_id,
                    "creator_name": names.get(creator_id, ""),
                    "eligible_pieces": eligible_count,
                    "selected_pieces": selected_count,
                    "selection_rate": selection_rate,
                    "gift_card_cost": gift_card,
                    "paid_spend": spend,
                    "boosted_revenue": revenue,
                    "roas": roas,
                    "active_last_month": creator_id in prior_active,
                    "retention_status": status,
                }
            )

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    out["selection_rate_pct"] = (out["selection_rate"] * 100).round(1)
    out["roas_display"] = out["roas"].map(_format_roas)
    return out.sort_values(["month", "creator_id"]).reset_index(drop=True)


def compute_creator_movement(content: pd.DataFrame, month: str) -> pd.DataFrame:
    """August-style movement table: retained / new / reactivated / lapsed / total active."""
    eligible = _eligible_content(normalize_content_raw(content))
    active_by_month = _active_creators_by_month(eligible)
    first_active = _creator_first_active_month(eligible)

    current_active = active_by_month.get(month, set())
    prior = _prior_month(month)
    prior_active = active_by_month.get(prior, set())

    retained = current_active & prior_active
    lapsed = prior_active - current_active

    new_count = 0
    reactivated_count = 0
    for cid in current_active - prior_active:
        status = classify_creator_retention(cid, month, active_by_month, first_active)
        if status == "New":
            new_count += 1
        elif status == "Reactivated":
            reactivated_count += 1

    rows = [
        {"segment": "Retained", "creators": len(retained)},
        {"segment": "New", "creators": new_count},
        {"segment": "Reactivated", "creators": reactivated_count},
        {"segment": "Lapsed", "creators": len(lapsed)},
        {"segment": "Total Active", "creators": len(current_active)},
    ]
    return pd.DataFrame(rows)


def build_program_monthly(content: pd.DataFrame) -> pd.DataFrame:
    """One row per month with program-level KPIs (long format for easy charting)."""
    eligible = _eligible_content(normalize_content_raw(content))
    creator_monthly = build_creator_monthly(content)

    if eligible.empty:
        return pd.DataFrame(columns=["month", "metric", "value"])

    months = sorted(eligible["month"].unique())
    active_by_month = _active_creators_by_month(eligible)

    records: list[dict] = []
    for month in months:
        month_eligible = eligible[eligible["month"] == month]
        month_creators = creator_monthly[creator_monthly["month"] == month]

        eligible_pieces = len(month_eligible)
        selected_pieces = int(month_eligible["selected"].sum())
        selection_rate = _safe_div(selected_pieces, eligible_pieces)

        active_creators = len(active_by_month.get(month, set()))
        creators_selected = int((month_creators["selected_pieces"] > 0).sum()) if not month_creators.empty else 0
        pct_creators_selected = _safe_div(creators_selected, active_creators)
        avg_selections = _safe_div(selected_pieces, active_creators)

        gift_card_spend = float(month_eligible.loc[month_eligible["selected"], "gift_card_cost"].sum())
        cost_per_selected = _safe_div(gift_card_spend, selected_pieces)
        paid_spend = float(month_eligible["paid_spend"].sum())
        boosted_revenue = float(month_eligible["boosted_revenue"].sum())
        roas = _safe_div(boosted_revenue, paid_spend)
        total_investment = gift_card_spend + paid_spend
        total_program_roi = _safe_div(boosted_revenue, total_investment)

        prior = _prior_month(month)
        prior_active_count = len(active_by_month.get(prior, set()))
        movement = compute_creator_movement(content, month)
        retained = int(movement.loc[movement["segment"] == "Retained", "creators"].iloc[0])
        new_creators = int(movement.loc[movement["segment"] == "New", "creators"].iloc[0])
        reactivated = int(movement.loc[movement["segment"] == "Reactivated", "creators"].iloc[0])
        lapsed = int(movement.loc[movement["segment"] == "Lapsed", "creators"].iloc[0])
        retention_rate = _safe_div(retained, prior_active_count)

        # Eligible boosting creators = creators with any eligible content ever through this month
        eligible_through = eligible[eligible["month"] <= month]["creator_id"].nunique()
        activation_rate = _safe_div(active_creators, eligible_through) if eligible_through else None

        metric_values = {
            "eligible_boosting_creators": eligible_through,
            "active_boosting_creators": active_creators,
            "activation_rate": activation_rate,
            "eligible_content_pieces": eligible_pieces,
            "selected_content_pieces": selected_pieces,
            "selection_rate": selection_rate,
            "creators_selected": creators_selected,
            "pct_active_creators_selected": pct_creators_selected,
            "avg_selections_per_active_creator": avg_selections,
            "gift_card_spend": gift_card_spend,
            "cost_per_selected_asset": cost_per_selected,
            "paid_media_spend": paid_spend,
            "boosted_revenue": boosted_revenue,
            "roas": roas,
            "total_program_roi": total_program_roi,
            "retention_rate": retention_rate,
            "new_creators": new_creators,
            "reactivated_creators": reactivated,
            "lapsed_creators": lapsed,
            "prior_month_active_creators": prior_active_count,
        }

        for metric, value in metric_values.items():
            records.append({"month": month, "metric": metric, "value": value})

    return pd.DataFrame(records)


def program_monthly_pivot(program_long: pd.DataFrame) -> pd.DataFrame:
    """Wide scorecard: metrics as rows, months as columns."""
    if program_long.empty:
        return pd.DataFrame()

    wide = program_long.pivot(index="metric", columns="month", values="value")
    wide = wide.reindex(sorted(wide.columns, key=lambda m: _month_period(str(m))), axis=1)

    label_map = {
        "eligible_boosting_creators": "Eligible Boosting Creators",
        "active_boosting_creators": "Active Boosting Creators",
        "activation_rate": "Activation Rate",
        "eligible_content_pieces": "Eligible Content Pieces",
        "selected_content_pieces": "Selected Content Pieces",
        "selection_rate": "Selection Rate",
        "creators_selected": "Creators Selected",
        "pct_active_creators_selected": "% Active Creators Selected",
        "avg_selections_per_active_creator": "Avg Selections per Active Creator",
        "gift_card_spend": "Gift Card Spend",
        "cost_per_selected_asset": "Cost / Selected Asset",
        "paid_media_spend": "Paid Media Spend",
        "boosted_revenue": "Boosted Revenue",
        "roas": "ROAS",
        "total_program_roi": "Total Program ROI",
        "retention_rate": "Retention Rate",
        "new_creators": "New Creators",
        "reactivated_creators": "Reactivated Creators",
        "lapsed_creators": "Lapsed Creators",
        "prior_month_active_creators": "Prior Month Active Creators",
    }
    wide.index = [label_map.get(idx, idx) for idx in wide.index]
    wide.index.name = "Metric"
    return wide.reset_index()


def build_cohort_retention(content: pd.DataFrame, max_offset: int = 6) -> pd.DataFrame:
    """Cohort table: first active month × months since first activity."""
    eligible = _eligible_content(normalize_content_raw(content))
    if eligible.empty:
        return pd.DataFrame()

    first_active = _creator_first_active_month(eligible)
    active_by_month = _active_creators_by_month(eligible)

    cohorts = sorted(set(first_active.values()))
    rows: list[dict] = []
    for cohort in cohorts:
        cohort_creators = {cid for cid, m in first_active.items() if m == cohort}
        row: dict = {"first_active_month": cohort, "cohort_size": len(cohort_creators)}
        base_period = _month_period(cohort)
        for offset in range(max_offset + 1):
            target_month = str(base_period + offset)
            active_set = active_by_month.get(target_month, set())
            retained = len(cohort_creators & active_set)
            pct = _safe_div(retained, len(cohort_creators))
            row[f"month_{offset}"] = pct
        rows.append(row)

    return pd.DataFrame(rows)


def format_program_value(metric: str, value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    if metric in {"selection_rate", "activation_rate", "retention_rate", "pct_active_creators_selected"}:
        return f"{float(value) * 100:.1f}%"
    if metric in {"roas", "total_program_roi"}:
        return _format_roas(float(value))
    if metric in {"avg_selections_per_active_creator"}:
        return f"{float(value):.2f}"
    if metric in {
        "gift_card_spend",
        "cost_per_selected_asset",
        "paid_media_spend",
        "boosted_revenue",
    }:
        return f"${float(value):,.0f}"
    if isinstance(value, float) and not float(value).is_integer():
        return f"{float(value):,.1f}"
    return f"{int(value):,}"


def latest_program_kpis(program_long: pd.DataFrame) -> dict[str, float | None]:
    """Extract the 8 core KPIs for the most recent month."""
    if program_long.empty:
        return {}

    latest_month = max(program_long["month"].unique(), key=lambda m: _month_period(str(m)))
    month_data = program_long[program_long["month"] == latest_month].set_index("metric")["value"]

    keys = [
        "active_boosting_creators",
        "eligible_content_pieces",
        "selected_content_pieces",
        "selection_rate",
        "pct_active_creators_selected",
        "retention_rate",
        "cost_per_selected_asset",
        "boosted_revenue",
        "roas",
    ]
    return {k: month_data.get(k) for k in keys if k in month_data.index}


def program_trend_series(program_long: pd.DataFrame) -> pd.DataFrame:
    """Month-level series for dashboard charts."""
    if program_long.empty:
        return pd.DataFrame()

    pivot = program_long.pivot(index="month", columns="metric", values="value").reset_index()
    pivot["month_label"] = pivot["month"].map(lambda m: _month_period(str(m)).strftime("%b %Y"))
    pivot = pivot.sort_values("month")
    return pivot
