"""Build Boosting scorecard content from CreatorIQ campaign activity (posts)."""
from __future__ import annotations

import logging

import pandas as pd

from .api_client import CreatorIQClient
from .boosting_rules import (
    creator_has_boosting_tag,
    is_boosting_campaign,
    is_boosting_creator_post,
    is_eligible_boosting_content,
    wbp_creator_ids,
)
from .boosting_scorecard import CONTENT_RAW_COLUMNS, merge_content_raw, normalize_content_raw
from .config import AppConfig
from .normalize import clean_id_columns, normalize_records
from .tiers import extract_tier_from_tags, normalize_tag_string

logger = logging.getLogger(__name__)


def filter_boosting_posts(
    posts: pd.DataFrame,
    config: AppConfig,
    *,
    creators: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Posts from WBP-tagged creators or the Wayfair Creators Boosting Partnership campaign."""
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


def _boosting_settings(config: AppConfig) -> dict:
    return config.settings.get("boosting", default={}) or {}


def _resolve_boosting_campaign_ids(config: AppConfig, boosting_campaigns: pd.DataFrame) -> list[str]:
    """Configured IDs always sync; also include any campaigns matched from /campaigns."""
    configured = [str(x) for x in (_boosting_settings(config).get("campaign_ids") or []) if str(x).strip()]
    from_api: list[str] = []
    if not boosting_campaigns.empty and "campaign_id" in boosting_campaigns.columns:
        from_api = [str(x) for x in boosting_campaigns["campaign_id"].tolist() if str(x).strip() and str(x) != "nan"]

    seen: list[str] = []
    for cid in configured + from_api:
        if cid not in seen:
            seen.append(cid)
    return seen


def _fetch_boosting_campaigns(config: AppConfig, client: CreatorIQClient) -> pd.DataFrame:
    """List campaigns, applying boosting-specific status filter (not live_sync Active-only)."""
    mapping = config.field_mappings.get("campaigns", {})
    raw = client.fetch_all("campaigns")
    df = pd.DataFrame(normalize_records(raw, mapping))
    df = clean_id_columns(df, ["campaign_id"])

    status_filter = _boosting_settings(config).get("campaign_status_filter")
    if status_filter is None:
        status_filter = []
    if status_filter and not df.empty and "status" in df.columns:
        df = df[df["status"].isin(status_filter)]

    if df.empty:
        return df

    mask = df.apply(
        lambda row: is_boosting_campaign(row.get("campaign_name", ""), row.get("campaign_id", ""), config),
        axis=1,
    )
    return df[mask].reset_index(drop=True)


def _fetch_campaign_roster(
    config: AppConfig,
    client: CreatorIQClient,
    campaign_ids: list,
) -> pd.DataFrame:
    """Roster rows for the configured boosting campaign(s)."""
    if not campaign_ids:
        return pd.DataFrame()

    creator_mapping = config.field_mappings.get("creators", {})
    roster_rows: list[dict] = []
    for campaign_id in campaign_ids:
        try:
            raw_roster = client.fetch_unpaginated_list("campaign_publishers", path_params={"campaign_id": campaign_id})
            roster_rows.extend(normalize_records(raw_roster, creator_mapping))
        except Exception:  # noqa: BLE001
            logger.exception("Failed to fetch roster for boosting campaign %s", campaign_id)

    roster_df = clean_id_columns(pd.DataFrame(roster_rows), ["creator_id"])
    if roster_df.empty:
        return roster_df

    if "joined_date" in roster_df.columns:
        roster_df = roster_df.sort_values("joined_date")
    return roster_df.drop_duplicates(subset=["creator_id"], keep="last").reset_index(drop=True)


def _fetch_wbp_tagged_publishers(config: AppConfig, client: CreatorIQClient) -> pd.DataFrame:
    """Scan /publishers for CRM tag WBP (bounded by boosting.max_publisher_pages)."""
    cfg = _boosting_settings(config)
    required_tags = cfg.get("creator_tags") or ["WBP"]
    max_pages = cfg.get("max_publisher_pages")
    mapping = config.field_mappings.get("publishers", {})

    rows: list[dict] = []
    for record in client.iter_resource("publishers", max_pages=max_pages):
        pub = record.get("Publisher", record) if isinstance(record, dict) else record
        if not isinstance(pub, dict):
            continue
        tags = normalize_tag_string(pub.get("Tags") or pub.get("TagNames"))
        if not creator_has_boosting_tag(tags, required_tags):
            continue
        row = normalize_records([pub], mapping)[0]
        row["tags"] = tags
        row["tier"] = extract_tier_from_tags(tags)
        rows.append(row)

    df = clean_id_columns(pd.DataFrame(rows), ["creator_id", "network_publisher_id"])
    if df.empty:
        return df
    return df.drop_duplicates(subset=["creator_id"], keep="last").reset_index(drop=True)


def _combine_creators(*frames: pd.DataFrame) -> pd.DataFrame:
    parts = [df for df in frames if df is not None and not df.empty]
    if not parts:
        return pd.DataFrame()
    combined = pd.concat(parts, ignore_index=True)
    if "creator_id" not in combined.columns:
        return combined.drop_duplicates(keep="last")
    sort_col = "joined_date" if "joined_date" in combined.columns else None
    if sort_col:
        combined = combined.sort_values(sort_col)
    return combined.drop_duplicates(subset=["creator_id"], keep="last").reset_index(drop=True)


def _fetch_boosting_creators(
    config: AppConfig,
    client: CreatorIQClient,
    campaign_ids: list,
) -> pd.DataFrame:
    """WBP-tagged publishers plus roster from the boosting campaign(s)."""
    roster = _fetch_campaign_roster(config, client, campaign_ids)
    wbp_publishers = _fetch_wbp_tagged_publishers(config, client)
    return _combine_creators(roster, wbp_publishers)


def _enrich_content_with_creators(content: pd.DataFrame, creators: pd.DataFrame) -> pd.DataFrame:
    if content.empty or creators.empty or "creator_id" not in creators.columns:
        return content

    name_map: dict[str, str] = {}
    handle_map: dict[str, str] = {}
    for _, row in creators.iterrows():
        cid = str(row.get("creator_id", "")).strip()
        if not cid or cid == "nan":
            continue
        for src, dest in (("name", name_map), ("creator_name", name_map)):
            val = row.get(src)
            if val is not None and str(val).strip() not in {"", "nan"}:
                dest[cid] = str(val).strip()
        for src in ("handle", "creator_handle", "username"):
            val = row.get(src)
            if val is not None and str(val).strip() not in {"", "nan"}:
                handle_map[cid] = str(val).strip()

    out = content.copy()
    if "creator_name" not in out.columns:
        out["creator_name"] = ""
    if "creator_handle" not in out.columns:
        out["creator_handle"] = ""

    for idx, row in out.iterrows():
        cid = str(row.get("creator_id", "")).strip()
        if not cid:
            continue
        if not str(row.get("creator_name", "")).strip() or str(row.get("creator_name")) == "nan":
            out.at[idx, "creator_name"] = name_map.get(cid, "")
        if not str(row.get("creator_handle", "")).strip() or str(row.get("creator_handle")) == "nan":
            out.at[idx, "creator_handle"] = handle_map.get(cid, "")
    return out


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

    content = normalize_content_raw(pd.DataFrame(rows, columns=CONTENT_RAW_COLUMNS))
    return _enrich_content_with_creators(content, creators) if creators is not None else content


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
    client = client or CreatorIQClient(config)
    post_mapping = config.field_mappings.get("posts", {})

    boosting_campaigns = _fetch_boosting_campaigns(config, client)
    campaign_ids = _resolve_boosting_campaign_ids(config, boosting_campaigns)

    if creators is None or creators.empty:
        creators = _fetch_boosting_creators(config, client, campaign_ids)

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
        names = _boosting_settings(config).get("campaign_names") or ["Wayfair Creators Boosting Partnership"]
        ids = _boosting_settings(config).get("campaign_ids") or []
        logger.warning(
            "No boosting campaigns to sync. Check boosting.campaign_ids (%s) and campaign_names (%s) in settings.yaml.",
            ", ".join(str(i) for i in ids) or "none",
            ", ".join(str(n) for n in names),
        )

    posts_df = _combine_posts(posts_df, extra_posts)
    api_content = posts_to_boosting_content(posts_df, config, creators=creators)
    if existing_content is not None and not existing_content.empty:
        return merge_api_with_supplements(api_content, existing_content)
    return api_content
