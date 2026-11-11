"""Data for the boosting active-creator report — one campaign, not whole-program sync.

Pipeline (matches creator-activity-dash, boosting-scoped):
  1. CreatorIQ **campaign 2206666** roster + WBP publishers (API)
  2. **Campaign activity** → posts (API)
  3. **active_member_links** CSV / CRM (link dates)
  4. **creator_sales_ranking.csv** (transactions) — merged for names + txn flags
"""
from __future__ import annotations

import logging
import os

import pandas as pd

from .boosting_creatoriq import filter_boosting_posts
from .boosting_data_access import load_boosting_content, should_auto_sync_boosting, sync_and_store_boosting_content
from .boosting_rules import boosting_program_creator_ids, configured_boosting_campaign_ids
from .boosting_scorecard import normalize_content_raw
from .config import AppConfig
from .creator_sales import default_sales_path, load_creator_sales
from .data_access import normalize_creators_df, normalize_links_df
from .demo_data import generate_demo_data
from .metrics import RawData
from .boosting_roster import load_boosting_roster_creator_ids
from .storage import get_engine, get_last_synced_at, read_table

logger = logging.getLogger(__name__)

_CAMPAIGN_NAME = "Wayfair Creators Boosting Partnership"


def _api_refresh_lookback_days() -> int | None:
    raw = os.environ.get("BOOSTING_API_REFRESH_DAYS", "").strip()
    if not raw:
        return None
    try:
        return max(1, int(raw))
    except ValueError:
        return None


def boosting_content_to_posts(content: pd.DataFrame, config: AppConfig) -> pd.DataFrame:
    """Map boosting scorecard rows to activation `posts` schema."""
    if content.empty:
        return pd.DataFrame(
            columns=["post_id", "creator_id", "campaign_id", "campaign_name", "platform", "post_type", "posted_at"]
        )
    content = normalize_content_raw(content)
    campaign_ids = configured_boosting_campaign_ids(config)
    campaign_id = next(iter(campaign_ids), "2206666")
    posts = pd.DataFrame(
        {
            "post_id": content["content_url"].astype(str),
            "creator_id": content["creator_id"].astype(str),
            "campaign_id": campaign_id,
            "campaign_name": content["campaign"] if "campaign" in content.columns else _CAMPAIGN_NAME,
            "platform": content.get("platform", ""),
            "post_type": content.get("featured_category", ""),
            "posted_at": pd.to_datetime(content["post_date"], utc=True, errors="coerce"),
        }
    )
    return posts.dropna(subset=["posted_at"]).drop_duplicates(subset=["post_id"], keep="last")


def _creators_from_sales_csv() -> pd.DataFrame:
    path = default_sales_path()
    if not path.is_file():
        return pd.DataFrame(columns=["creator_id", "name"])
    raw = pd.read_csv(path)
    id_col = next((c for c in raw.columns if "publisher" in c.lower() and "id" in c.lower()), None)
    name_col = next((c for c in raw.columns if "publisher" in c.lower() and "name" in c.lower()), None)
    if not id_col:
        return pd.DataFrame(columns=["creator_id", "name"])
    out = pd.DataFrame({"creator_id": raw[id_col].astype(str).str.strip()})
    out["name"] = raw[name_col].astype(str) if name_col else ""
    return out.drop_duplicates(subset=["creator_id"])


def _union_creators(*frames: pd.DataFrame) -> pd.DataFrame:
    parts = [normalize_creators_df(f) for f in frames if f is not None and not f.empty]
    if not parts:
        return normalize_creators_df(pd.DataFrame())
    combined = pd.concat(parts, ignore_index=True)
    if "creator_id" not in combined.columns:
        return normalize_creators_df(pd.DataFrame())
    for col in ("name", "handle", "email", "tags", "status"):
        if col not in combined.columns:
            combined[col] = ""
    combined = combined.sort_values("name", na_position="last")
    return normalize_creators_df(combined.drop_duplicates(subset=["creator_id"], keep="first"))


def _enrich_creator_names(creators: pd.DataFrame, content: pd.DataFrame) -> pd.DataFrame:
    if creators.empty or content.empty:
        return creators
    out = creators.copy()
    if "creator_name" in content.columns:
        name_map = (
            content.dropna(subset=["creator_id"])
            .groupby(content["creator_id"].astype(str))["creator_name"]
            .first()
        )
        mask = out["name"].fillna("").astype(str).str.strip().eq("")
        out.loc[mask, "name"] = out.loc[mask, "creator_id"].astype(str).map(name_map).fillna("")
    if "creator_handle" in content.columns:
        handle_map = (
            content.dropna(subset=["creator_id"])
            .groupby(content["creator_id"].astype(str))["creator_handle"]
            .first()
        )
        mask = out["handle"].fillna("").astype(str).str.strip().eq("")
        out.loc[mask, "handle"] = out.loc[mask, "creator_id"].astype(str).map(handle_map).fillna("")
    return normalize_creators_df(out)


def prepare_demo_boosting_raw() -> RawData:
    demo = generate_demo_data()
    creators = demo.creators.copy()
    n = min(120, len(creators))
    idx = creators.index[:n] if n > 0 else pd.Index([])
    if n > 0:
        creators.loc[idx, "tags"] = creators.loc[idx, "tags"].fillna("").astype(str).apply(
            lambda t: "WBP" if not t.strip() else f"{t}, WBP"
        )
    posts = demo.posts.copy()
    if not posts.empty and n > 0:
        boost_ids = set(creators.loc[idx, "creator_id"].astype(str))
        post_idx = posts.index[: min(400, len(posts))]
        posts.loc[post_idx, "campaign_id"] = "2206666"
        posts.loc[post_idx, "campaign_name"] = _CAMPAIGN_NAME
        posts.loc[post_idx, "creator_id"] = posts.loc[post_idx, "creator_id"].where(
            posts.loc[post_idx, "creator_id"].astype(str).isin(boost_ids),
            creators.loc[idx, "creator_id"].sample(len(post_idx), replace=True).values,
        )
    return RawData(
        creators=normalize_creators_df(creators),
        posts=posts,
        links=demo.links,
        email_events=demo.email_events,
        link_clicks=pd.DataFrame(),
        active_member_links=None,
    )


def _filter_tables_to_program(
    creators: pd.DataFrame,
    posts: pd.DataFrame,
    links: pd.DataFrame,
    active_member_links: pd.DataFrame,
    email_events: pd.DataFrame,
    link_clicks: pd.DataFrame,
    config: AppConfig,
    roster_ids: set[str],
) -> RawData:
    program_ids = boosting_program_creator_ids(creators, posts, config, campaign_roster_ids=roster_ids)
    sales = load_creator_sales()
    program_ids |= set(sales["creator_id"].astype(str)) if not sales.empty else set()

    if program_ids:
        creators = creators[creators["creator_id"].astype(str).isin(program_ids)]
        if not posts.empty:
            posts = filter_boosting_posts(posts, config, creators=creators)
        if not links.empty:
            links = links[links["creator_id"].astype(str).isin(program_ids)]
        if not active_member_links.empty:
            active_member_links = active_member_links[active_member_links["creator_id"].astype(str).isin(program_ids)]
        if not email_events.empty:
            email_events = email_events[email_events["creator_id"].astype(str).isin(program_ids)]
        if not link_clicks.empty:
            link_clicks = link_clicks[link_clicks["creator_id"].astype(str).isin(program_ids)]

    lookback = _api_refresh_lookback_days()
    if lookback and not posts.empty and "posted_at" in posts.columns:
        cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=lookback)
        posts = posts[pd.to_datetime(posts["posted_at"], utc=True, errors="coerce") >= cutoff]

    return RawData(
        creators=creators,
        posts=posts,
        links=links,
        email_events=email_events,
        link_clicks=link_clicks if not link_clicks.empty else None,
        active_member_links=active_member_links if not active_member_links.empty else None,
    )


def load_boosting_activity_inputs(config: AppConfig) -> tuple[RawData, dict[str, str | None]]:
    if config.is_demo:
        return prepare_demo_boosting_raw(), {k: "demo" for k in ("creators", "posts", "links", "boosting_content")}

    engine = get_engine(config.db_path)
    content, content_sync = load_boosting_content(config)
    boosting_status = content_sync.get("boosting_content")

    if should_auto_sync_boosting(config, content, boosting_status):
        try:
            logger.info("Auto-syncing boosting campaign for active-creator report…")
            content = normalize_content_raw(sync_and_store_boosting_content(config))
            boosting_status = get_last_synced_at(engine, "boosting_content")
        except Exception:  # noqa: BLE001
            logger.exception("Boosting auto-sync failed")

    roster = read_table(engine, "boosting_roster")
    posts = boosting_content_to_posts(content, config)

    warehouse_posts = read_table(engine, "posts")
    if not warehouse_posts.empty:
        boost_from_wh = filter_boosting_posts(warehouse_posts, config, creators=roster)
        if not boost_from_wh.empty:
            posts = pd.concat([posts, boost_from_wh], ignore_index=True).drop_duplicates(subset=["post_id"], keep="last")

    sales_creators = _creators_from_sales_csv()
    creators = _union_creators(roster, sales_creators)
    creators = _enrich_creator_names(creators, content)
    if creators.empty and not content.empty:
        creators = normalize_creators_df(pd.DataFrame({"creator_id": content["creator_id"].astype(str).unique()}))
        creators = _enrich_creator_names(creators, content)

    roster_ids = (
        set(creators["creator_id"].astype(str))
        if not creators.empty
        else load_boosting_roster_creator_ids(config)
    )
    links = normalize_links_df(read_table(engine, "links"))
    active_member_links = read_table(engine, "active_member_links")
    email_events = read_table(engine, "email_events")
    link_clicks = read_table(engine, "link_clicks")

    raw = _filter_tables_to_program(
        creators,
        posts,
        links,
        active_member_links,
        email_events,
        link_clicks,
        config,
        roster_ids,
    )

    sync_status = {
        "creators": boosting_status,
        "posts": boosting_status,
        "links": get_last_synced_at(engine, "links"),
        "boosting_content": boosting_status,
        "active_member_links": get_last_synced_at(engine, "active_member_links"),
    }
    return raw, sync_status
