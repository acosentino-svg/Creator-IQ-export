"""Build Boosting scorecard content from CreatorIQ campaign activity (posts)."""
from __future__ import annotations

import logging

import pandas as pd

from .api_client import CreatorIQClient
from .boosting_rules import (
    is_boosting_campaign,
    is_boosting_creator_post,
    is_eligible_boosting_content,
    wbp_creator_ids,
)
from .boosting_scorecard import CONTENT_RAW_COLUMNS, merge_content_raw, normalize_content_raw
from .config import AppConfig
from .normalize import clean_id_columns, normalize_records

logger = logging.getLogger(__name__)


def filter_boosting_posts(
    posts: pd.DataFrame,
    config: AppConfig,
    *,
    creators: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Posts from WBP-tagged creators or the Wayfair Boosting Partnership campaign."""
    if posts.empty:
        return posts.copy()

    wbp_ids = wbp_creator_ids(creators, config)
    mask = posts.apply(
        lambda row: is_boosting_creator_post(row, config=config, wbp_ids=wbp_ids),
        axis=1,
    )
    return posts[mask].copy()


def _coerce_bool(value, default: bool = False) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "yes", "y", "1", "t", "selected", "eligible", "boosted"}:
        return True
    if text in {"false", "no", "n", "0", "f", ""}:
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
    creators: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Transform synced CreatorIQ campaign-activity posts into Content Raw rows."""
    wbp_ids = wbp_creator_ids(creators, config)
    boosting_posts = filter_boosting_posts(posts, config, creators=creators)
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

        api_eligible_raw = post.get("boosting_eligible")
        api_eligible = None
        if api_eligible_raw is not None and not (isinstance(api_eligible_raw, float) and pd.isna(api_eligible_raw)):
            api_eligible = _coerce_bool(api_eligible_raw)

        eligible = is_eligible_boosting_content(post, config=config, api_eligible=api_eligible)

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


def _combine_posts(*frames: pd.DataFrame) -> pd.DataFrame:
    parts = [df for df in frames if df is not None and not df.empty]
    if not parts:
        return pd.DataFrame()
    combined = pd.concat(parts, ignore_index=True)
    if "post_id" in combined.columns:
        return combined.drop_duplicates(subset=["post_id"], keep="last")
    return combined.drop_duplicates(keep="last")


def sync_boosting_from_creatoriq(
    config: AppConfig,
    *,
    existing_content: pd.DataFrame | None = None,
    extra_posts: pd.DataFrame | None = None,
    creators: pd.DataFrame | None = None,
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

    if not campaign_ids:
        logger.warning("No boosting campaigns matched config.boosting filters.")

    posts_df = _combine_posts(posts_df, extra_posts)
    api_content = posts_to_boosting_content(posts_df, config, creators=creators)
    if existing_content is not None and not existing_content.empty:
        return merge_api_with_supplements(api_content, existing_content)
    return api_content
