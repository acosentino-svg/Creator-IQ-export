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
from .csv_backlog import backlog_file_totals, filter_by_date_range, load_csv_backlog
from .hybrid_diagnostics import HybridDiagnostics, build_hybrid_diagnostics
from .storage import get_engine, get_last_synced_at, read_table

logger = logging.getLogger(__name__)

_CAMPAIGN_NAME = "Wayfair Creators Boosting Partnership"

_LAST_HYBRID_DIAGNOSTICS: HybridDiagnostics | None = None
_LAST_TRANSACTIONS_VIEW: pd.DataFrame | None = None


def get_boosting_hybrid_diagnostics() -> HybridDiagnostics | None:
    return _LAST_HYBRID_DIAGNOSTICS


def get_boosting_transactions_view() -> pd.DataFrame:
    if _LAST_TRANSACTIONS_VIEW is None or _LAST_TRANSACTIONS_VIEW.empty:
        return pd.DataFrame()
    return _LAST_TRANSACTIONS_VIEW


def _activity_window() -> tuple[pd.Timestamp, pd.Timestamp]:
    start_raw = os.environ.get("BOOSTING_ACTIVITY_START", "").strip()
    end_raw = os.environ.get("BOOSTING_ACTIVITY_END", "").strip()
    if start_raw and end_raw:
        start = pd.Timestamp(start_raw).tz_localize("UTC") if pd.Timestamp(start_raw).tzinfo is None else pd.Timestamp(start_raw)
        end = pd.Timestamp(end_raw).tz_localize("UTC") if pd.Timestamp(end_raw).tzinfo is None else pd.Timestamp(end_raw)
        return start, end
    end = pd.Timestamp.now(tz="UTC")
    return end - pd.Timedelta(days=30), end


def _filter_posts_to_boosting_campaign(posts: pd.DataFrame, config: AppConfig) -> pd.DataFrame:
    if posts.empty:
        return posts
    ids = configured_boosting_campaign_ids(config)
    if "campaign_id" in posts.columns:
        mask = posts["campaign_id"].astype(str).isin(ids)
        if "campaign_name" in posts.columns:
            mask = mask | posts["campaign_name"].astype(str).str.contains("Boosting", case=False, na=False)
        return posts[mask].copy()
    return posts


def _csv_posts_to_schema(df: pd.DataFrame, config: AppConfig) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["post_id", "creator_id", "campaign_id", "campaign_name", "posted_at"])
    out = df.copy()
    date_col = next((c for c in out.columns if "post" in c.lower() and "date" in c.lower()), None) or _find_any_date_col(out)
    if date_col:
        out["posted_at"] = pd.to_datetime(out[date_col], utc=True, errors="coerce")
    url_col = next((c for c in out.columns if "url" in c.lower() or "link" in c.lower()), None)
    out["post_id"] = out[url_col].astype(str) if url_col else out.index.astype(str)
    if "campaign_id" not in out.columns:
        out["campaign_id"] = "2206666"
    out["campaign_name"] = _CAMPAIGN_NAME
    out = _filter_posts_to_boosting_campaign(out, config)
    if "posted_at" in out.columns:
        out = out.dropna(subset=["posted_at"])
    return out


def _find_any_date_col(df: pd.DataFrame) -> str | None:
    for cand in df.columns:
        if "date" in str(cand).lower() or "created" in str(cand).lower():
            return cand
    return None


def _csv_links_to_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["link_id", "creator_id", "created_at", "campaign_id"])
    out = df.copy()
    date_col = _find_any_date_col(df)
    if date_col:
        out["created_at"] = pd.to_datetime(out[date_col], utc=True, errors="coerce")
    out["link_id"] = out.index.astype(str)
    out["campaign_id"] = out["campaign_id"].astype(str) if "campaign_id" in out.columns else "2206666"
    return out


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
            "platform": content["platform"] if "platform" in content.columns else "",
            "post_type": content["featured_category"] if "featured_category" in content.columns else "",
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

    # Post date range is controlled by the sidebar activity window (and API/cache merge),
    # not by the refresh-window days control (that is for future incremental sync only).

    return RawData(
        creators=creators,
        posts=posts,
        links=links,
        email_events=email_events,
        link_clicks=link_clicks if not link_clicks.empty else None,
        active_member_links=active_member_links if not active_member_links.empty else None,
    )


def load_boosting_activity_inputs(config: AppConfig) -> tuple[RawData, dict[str, str | None]]:
    global _LAST_HYBRID_DIAGNOSTICS, _LAST_TRANSACTIONS_VIEW  # noqa: PLW0603

    activity_start, activity_end = _activity_window()
    backlog = load_csv_backlog(config)
    backlog_totals = backlog_file_totals(backlog)

    if config.is_demo:
        raw = prepare_demo_boosting_raw()
        _LAST_TRANSACTIONS_VIEW = pd.DataFrame()
        _LAST_HYBRID_DIAGNOSTICS = build_hybrid_diagnostics(
            activity_start=activity_start,
            activity_end=activity_end,
            posts=raw.posts,
            links=raw.links,
            transactions=pd.DataFrame(),
            publisher_names=raw.creators[["creator_id", "name"]].drop_duplicates() if not raw.creators.empty else pd.DataFrame(),
            api_meta={**backlog_totals, "notes": ["Demo mode — upload CSV backlog to data/backlog/ for hybrid totals."]},
        )
        return raw, {k: "demo" for k in ("creators", "posts", "links", "boosting_content")}

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
    api_posts = boosting_content_to_posts(content, config)
    api_posts = filter_by_date_range(api_posts, activity_start, activity_end)

    warehouse_posts = read_table(engine, "posts")
    if not warehouse_posts.empty:
        boost_from_wh = filter_boosting_posts(warehouse_posts, config, creators=roster)
        if not boost_from_wh.empty:
            api_posts = pd.concat([api_posts, boost_from_wh], ignore_index=True).drop_duplicates(subset=["post_id"], keep="last")

    csv_posts_all = _filter_posts_to_boosting_campaign(_csv_posts_to_schema(backlog.get("posts", pd.DataFrame()), config), config)
    csv_posts_range = filter_by_date_range(csv_posts_all, activity_start, activity_end)
    posts = pd.concat([api_posts, csv_posts_range], ignore_index=True).drop_duplicates(subset=["post_id"], keep="last")

    csv_links_all = _csv_links_to_schema(backlog.get("links", pd.DataFrame()))
    csv_links_range = filter_by_date_range(csv_links_all, activity_start, activity_end)

    sales_creators = _creators_from_sales_csv()
    name_backlog = backlog.get("publisher_names", pd.DataFrame())
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
    api_links = normalize_links_df(read_table(engine, "links"))
    links = pd.concat([api_links, normalize_links_df(csv_links_range)], ignore_index=True)
    if not links.empty and "link_id" in links.columns:
        links = links.drop_duplicates(subset=["link_id"], keep="last")
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

    csv_txn_all = backlog.get("transactions", pd.DataFrame())
    csv_txn_range = filter_by_date_range(csv_txn_all, activity_start, activity_end)
    sales = load_creator_sales()
    transactions_view = csv_txn_range if not csv_txn_range.empty else sales.rename(columns={"creator_id": "creator_id"})

    import json

    api_meta = {
        **backlog_totals,
        "api_posts": len(api_posts),
        "api_links": len(api_links),
        "api_transactions": len(transactions_view),
        "links_fetch_pages": int((len(api_links) + 99) / 100) if len(api_links) else 0,
        "transactions_fetch_pages": int((len(transactions_view) + 99) / 100) if len(transactions_view) else 0,
        "links_fetch_rows": len(links),
        "transactions_fetch_rows": len(transactions_view),
    }
    fetch_meta = os.environ.get("BOOSTING_API_FETCH_META", "").strip()
    if fetch_meta:
        try:
            api_meta.update(json.loads(fetch_meta))
        except json.JSONDecodeError:
            pass

    publisher_names = _union_creators(creators, name_backlog.rename(columns={"name": "name"}) if "name" in name_backlog.columns else name_backlog)

    _LAST_TRANSACTIONS_VIEW = transactions_view.copy() if not transactions_view.empty else pd.DataFrame()

    _LAST_HYBRID_DIAGNOSTICS = build_hybrid_diagnostics(
        activity_start=activity_start,
        activity_end=activity_end,
        posts=raw.posts,
        links=raw.links,
        transactions=transactions_view,
        publisher_names=publisher_names[["creator_id", "name"]] if "name" in publisher_names.columns else publisher_names,
        csv_posts=csv_posts_range,
        csv_links=csv_links_range,
        csv_transactions=csv_txn_range,
        api_meta=api_meta,
        campaign_id=next(iter(configured_boosting_campaign_ids(config)), "2206666"),
    )

    sync_status = {
        "creators": boosting_status,
        "posts": boosting_status,
        "links": get_last_synced_at(engine, "links"),
        "boosting_content": boosting_status,
        "active_member_links": get_last_synced_at(engine, "active_member_links"),
    }
    return raw, sync_status
