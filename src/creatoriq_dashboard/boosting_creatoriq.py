"""Build Boosting scorecard content from CreatorIQ campaign activity (posts)."""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from .api_client import CreatorIQClient
from .config import AppConfig
from .boosting_scorecard import CONTENT_RAW_COLUMNS, merge_content_raw, normalize_content_raw
from .normalize import clean_id_columns, normalize_records

logger = logging.getLogger(__name__)


def _boosting_settings(config: AppConfig) -> dict[str, Any]:
    return config.settings.get("boosting", default={}) or {}


def is_boosting_campaign(campaign_name: str, campaign_id: str, config: AppConfig) -> bool:
    """True when a campaign belongs to the Boosting program (config-driven)."""
    cfg = _boosting_settings(config)
    campaign_ids = cfg.get("campaign_ids") or []
    if campaign_ids:
        return str(campaign_id) in {str(x) for x in campaign_ids}

    terms = cfg.get("campaign_name_contains")
    if terms is None:
        terms = ["boost", "Boosting"]
    if not terms:
        return bool(cfg.get("include_all_campaigns", False))

    text = str(campaign_name).lower()
    return any(str(term).lower() in text for term in terms)


def filter_boosting_posts(posts: pd.DataFrame, config: AppConfig) -> pd.DataFrame:
    if posts.empty:
        return posts.copy()
    if "campaign_name" not in posts.columns and "campaign_id" not in posts.columns:
        return posts.iloc[0:0].copy()

    mask = posts.apply(
        lambda row: is_boosting_campaign(
            row.get("campaign_name", ""),
            row.get("campaign_id", ""),
            config,
        ),
        axis=1,
    )
    return posts[mask].copy()


def _coerce_bool(value, default: bool = False) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "yes", "y", "1", "selected", "eligible", "boosted"}:
        return True
    if text in {"false", "no", "n", "0", ""}:
        return False
    return default


def _num(value, default: float = 0.0) -> float:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return default
    return float(parsed)


def posts_to_boosting_content(
    posts: pd.DataFrame,
    config: AppConfig,
    *,
    creator_names: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Transform synced CreatorIQ campaign-activity posts into Content Raw rows."""
    del creator_names  # reserved for future enrichment
    cfg = _boosting_settings(config)
    default_eligible = bool(cfg.get("default_eligible_if_in_campaign", True))

    boosting_posts = filter_boosting_posts(posts, config)
    if boosting_posts.empty:
        return pd.DataFrame(columns=CONTENT_RAW_COLUMNS)

    rows: list[dict] = []
    for _, post in boosting_posts.iterrows():
        posted_at = pd.to_datetime(post.get("posted_at"), utc=True, errors="coerce")
        if pd.isna(posted_at):
            continue

        creator_id = str(post.get("creator_id", "")).strip()
        if not creator_id or creator_id == "nan":
            continue

        post_url = post.get("post_url") or post.get("content_url") or ""
        if not post_url or str(post_url).lower() in {"nan", "none"}:
            post_url = f"creatoriq://post/{post.get('post_id', '')}"

        eligible_col = post.get("boosting_eligible")
        if eligible_col is None or (isinstance(eligible_col, float) and pd.isna(eligible_col)):
            eligible = default_eligible
        else:
            eligible = _coerce_bool(eligible_col, default=default_eligible)

        selected = _coerce_bool(post.get("boosting_selected"), default=False)
        boosted = _coerce_bool(post.get("boosting_boosted"), default=False)
        if not boosted and _num(post.get("boosting_paid_spend")) > 0:
            boosted = True

        engagement = _num(post.get("engagements"))
        if engagement == 0:
            engagement = _num(post.get("likes")) + _num(post.get("comments")) + _num(post.get("shares"))

        rows.append(
            {
                "creator_id": creator_id,
                "month": posted_at.strftime("%Y-%m"),
                "content_url": str(post_url),
                "platform": str(post.get("platform") or ""),
                "post_date": posted_at,
                "eligible": eligible,
                "selected": selected,
                "selection_date": pd.to_datetime(post.get("boosting_selection_date"), utc=True, errors="coerce"),
                "boosted": boosted,
                "gift_card_cost": _num(post.get("boosting_gift_card_cost")),
                "paid_spend": _num(post.get("boosting_paid_spend")),
                "boosted_revenue": _num(post.get("boosting_revenue")),
                "impressions": int(_num(post.get("views"))),
                "engagements": int(engagement),
                "clicks": int(_num(post.get("link_clicks"))),
                "featured_category": str(post.get("boosting_category") or post.get("post_type") or ""),
                "campaign": str(post.get("campaign_name") or ""),
            }
        )

    return normalize_content_raw(pd.DataFrame(rows, columns=CONTENT_RAW_COLUMNS))


def merge_api_with_supplements(api_df: pd.DataFrame, supplement_df: pd.DataFrame) -> pd.DataFrame:
    """Keep API rows but overlay paid metrics from CSV uploads when API values are zero."""
    api = normalize_content_raw(api_df)
    supplement = normalize_content_raw(supplement_df)
    if api.empty:
        return supplement
    if supplement.empty:
        return api

    merged = merge_content_raw(api, supplement)
    if merged.empty:
        return merged

    supplement_index = supplement.set_index(["content_url", "month"], drop=False)
    overlay_cols = ["gift_card_cost", "paid_spend", "boosted_revenue", "selected", "boosted", "selection_date"]

    for idx, row in merged.iterrows():
        key = (row["content_url"], row["month"])
        if key not in supplement_index.index:
            continue
        sup = supplement_index.loc[key]
        if isinstance(sup, pd.DataFrame):
            sup = sup.iloc[-1]
        for col in overlay_cols:
            api_val = row[col]
            sup_val = sup[col]
            if col in ("gift_card_cost", "paid_spend", "boosted_revenue"):
                if (api_val is None or _num(api_val) == 0) and _num(sup_val) > 0:
                    merged.at[idx, col] = sup_val
            elif col in ("selected", "boosted"):
                if not _coerce_bool(api_val) and _coerce_bool(sup_val):
                    merged.at[idx, col] = sup_val
            elif col == "selection_date":
                if pd.isna(api_val) and pd.notna(sup_val):
                    merged.at[idx, col] = sup_val

    return normalize_content_raw(merged)


def sync_boosting_from_creatoriq(
    config: AppConfig,
    *,
    existing_content: pd.DataFrame | None = None,
    client: CreatorIQClient | None = None,
) -> pd.DataFrame:
    """Fetch boosting campaign activity from CreatorIQ and return Content Raw rows."""
    from .etl import _fetch_campaigns  # local import avoids circular dependency with etl.py

    client = client or CreatorIQClient(config)
    post_mapping = config.field_mappings.get("posts", {})
    campaigns_df = _fetch_campaigns(config, client)

    boosting_campaigns = campaigns_df[
        campaigns_df.apply(
            lambda row: is_boosting_campaign(row.get("campaign_name", ""), row.get("campaign_id", ""), config),
            axis=1,
        )
    ]
    campaign_ids = boosting_campaigns["campaign_id"].tolist() if not boosting_campaigns.empty else []

    if not campaign_ids:
        logger.warning("No boosting campaigns matched config.boosting filters.")
        return normalize_content_raw(existing_content or pd.DataFrame(columns=CONTENT_RAW_COLUMNS))

    post_rows: list[dict] = []
    for campaign_id in campaign_ids:
        try:
            raw_posts = client.fetch_nested_all("campaign_activity", path_params={"campaign_id": campaign_id})
            post_rows.extend(normalize_records(raw_posts, post_mapping))
        except Exception:  # noqa: BLE001
            logger.exception("Failed to fetch boosting activity for campaign %s", campaign_id)

    posts_df = clean_id_columns(
        pd.DataFrame(post_rows), ["post_id", "creator_id", "campaign_id", "network_publisher_id"]
    )
    if not posts_df.empty:
        posts_df = posts_df.drop_duplicates(subset=["post_id"], keep="last")

    api_content = posts_to_boosting_content(posts_df, config)
    if existing_content is not None and not existing_content.empty:
        return merge_api_with_supplements(api_content, existing_content)
    return api_content
