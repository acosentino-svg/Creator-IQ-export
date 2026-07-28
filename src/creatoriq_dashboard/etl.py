"""Pulls data from the CreatorIQ API, normalizes it, and lands it in the
local SQLite warehouse that the Streamlit app reads from.

CreatorIQ's real data model (verified against a live account, 2026-07) is
campaign-centric: there's no single "give me all my creators" or "give me
all posts" endpoint. Instead:

  1. /campaigns lists campaigns.
  2. /campaign/{id}/publishers gives the roster (+ per-creator campaign
     status) for one campaign.
  3. /campaign/{id}/activity gives the social posts + metrics for one
     campaign.
  4. /publisher/{network_id}/messages and /publisher/{network_id}/summary
     give per-creator email/message history and contact info, but need a
     "NetworkPublisherId" that's different from the internal "PublisherId"
     used everywhere else -- resolved from a post if the creator has one,
     otherwise via an extra /publishers?filter= lookup.

So a full sync fans out over every (configured, status-filtered) campaign,
accumulates rosters/posts, dedupes creators, then does a bounded number of
per-creator lookups for email data. See `config/settings.yaml`'s
`live_sync` section for the safety limits on that fan-out.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from .api_client import CreatorIQClient
from .config import AppConfig
from .normalize import clean_id_columns, normalize_records
from .tiers import extract_tier_from_tags, normalize_tag_string
from .storage import (
    append_link_click_snapshot,
    derive_link_click_deltas,
    get_engine,
    record_sync,
    write_table,
)

logger = logging.getLogger(__name__)


def _fetch_campaigns(config: AppConfig, client: CreatorIQClient) -> pd.DataFrame:
    mapping = config.field_mappings.get("campaigns", {})
    raw = client.fetch_all("campaigns")
    df = pd.DataFrame(normalize_records(raw, mapping))
    df = clean_id_columns(df, ["campaign_id"])
    status_filter = config.settings.get("live_sync", "campaign_status_filter", default=[]) or []
    if status_filter and not df.empty and "status" in df.columns:
        df = df[df["status"].isin(status_filter)]
    return df.reset_index(drop=True)


def _fetch_roster_and_posts(
    config: AppConfig, client: CreatorIQClient, campaign_ids: list
) -> tuple[pd.DataFrame, pd.DataFrame]:
    creator_mapping = config.field_mappings.get("creators", {})
    post_mapping = config.field_mappings.get("posts", {})

    roster_rows: list[dict] = []
    post_rows: list[dict] = []

    for campaign_id in campaign_ids:
        try:
            raw_roster = client.fetch_unpaginated_list("campaign_publishers", path_params={"campaign_id": campaign_id})
            roster_rows.extend(normalize_records(raw_roster, creator_mapping))
        except Exception:  # noqa: BLE001 - one bad campaign shouldn't abort the whole sync
            logger.exception("Failed to fetch roster for campaign %s", campaign_id)

        try:
            raw_posts = client.fetch_nested_all("campaign_activity", path_params={"campaign_id": campaign_id})
            post_rows.extend(normalize_records(raw_posts, post_mapping))
        except Exception:  # noqa: BLE001
            logger.exception("Failed to fetch activity for campaign %s", campaign_id)

    roster_df = clean_id_columns(pd.DataFrame(roster_rows), ["creator_id"])
    posts_df = clean_id_columns(
        pd.DataFrame(post_rows), ["post_id", "creator_id", "campaign_id", "network_publisher_id"]
    )

    if not roster_df.empty:
        # A creator can be on multiple campaigns; keep the most-recently-added row per creator.
        roster_df = roster_df.sort_values("joined_date").drop_duplicates(subset=["creator_id"], keep="last")
    if not posts_df.empty:
        posts_df = posts_df.drop_duplicates(subset=["post_id"], keep="last")

    return roster_df.reset_index(drop=True), posts_df.reset_index(drop=True)


def _resolve_network_publisher_ids(
    config: AppConfig, client: CreatorIQClient, creator_ids: pd.Series, posts_df: pd.DataFrame
) -> dict[str, str]:
    """Map internal creator_id -> NetworkPublisherId, preferring the free
    lookup from a post's own NetworkPublisherId field before falling back to
    a paid (extra API call) /publishers?filter= resolution.
    """
    known: dict[str, str] = {}
    if not posts_df.empty and "network_publisher_id" in posts_df.columns:
        pairs = posts_df.dropna(subset=["network_publisher_id"])[["creator_id", "network_publisher_id"]]
        known = dict(zip(pairs["creator_id"].astype(str), pairs["network_publisher_id"].astype(str)))

    if not config.settings.get("live_sync", "resolve_missing_network_ids", default=True):
        return known

    max_lookups = config.settings.get("live_sync", "max_email_lookups", default=None)
    missing = [cid for cid in creator_ids.astype(str).unique() if cid not in known]
    if max_lookups is not None:
        missing = missing[: max(0, int(max_lookups) - len(known))]

    for creator_id in missing:
        try:
            resolved = client.resolve_network_publisher_id(creator_id)
        except Exception:  # noqa: BLE001
            resolved = None
        if resolved:
            known[creator_id] = resolved
    return known


def _fetch_enrolled_creators(config: AppConfig, client: CreatorIQClient) -> pd.DataFrame:
    """All program enrollees: CreatorIQ publishers with Status=Active (~42k)."""
    mapping = config.field_mappings.get("publishers", {})
    status = config.settings.get("live_sync", "enrolled_status_filter", default="Active")
    max_pages = config.settings.get("live_sync", "max_publisher_pages", default=450)
    rows: list[dict] = []
    for record in client.iter_resource(
        "publishers",
        extra_params={"filter": f"Status={status}"},
        max_pages=max_pages,
    ):
        pub = record.get("Publisher", record) if isinstance(record, dict) else record
        if not isinstance(pub, dict):
            continue
        row = normalize_records([pub], mapping)[0]
        tags = normalize_tag_string(row.get("tags"))
        row["tags"] = tags
        row["tier"] = extract_tier_from_tags(tags)
        rows.append(row)
    df = clean_id_columns(pd.DataFrame(rows), ["creator_id", "network_publisher_id"])
    if not df.empty and "joined_date" in df.columns:
        df["joined_date"] = pd.to_datetime(df["joined_date"], utc=True, errors="coerce")
    return df.reset_index(drop=True)


def _fetch_publisher_metadata_index(config: AppConfig, client: CreatorIQClient) -> dict[str, dict[str, str | None]]:
    """Index CreatorIQ /publishers tags by both Id and PublisherId for roster joins."""
    max_pages = config.settings.get("live_sync", "max_publisher_pages", default=100)
    index: dict[str, dict[str, str | None]] = {}
    for record in client.iter_resource("publishers", max_pages=max_pages):
        pub = record.get("Publisher", record) if isinstance(record, dict) else record
        if not isinstance(pub, dict):
            continue
        tags = normalize_tag_string(pub.get("Tags") or pub.get("TagNames"))
        tier = extract_tier_from_tags(tags)
        meta = {
            "tags": tags,
            "tier": tier,
            "email": pub.get("Email") or pub.get("PrimaryEmail") or "",
        }
        for key in (pub.get("Id"), pub.get("PublisherId")):
            if key is not None and str(key).strip():
                index[str(key)] = meta
    return index


def _apply_publisher_metadata(roster_df: pd.DataFrame, metadata_index: dict[str, dict[str, str | None]]) -> pd.DataFrame:
    if roster_df.empty or not metadata_index:
        return roster_df
    df = roster_df.copy()
    tags_vals = []
    tier_vals = []
    email_vals = []
    for _, row in df.iterrows():
        meta = metadata_index.get(str(row["creator_id"]), {})
        tags = meta.get("tags") or row.get("tags") or ""
        tags_vals.append(tags)
        tier_vals.append(meta.get("tier") or extract_tier_from_tags(tags) or row.get("tier"))
        email_vals.append(meta.get("email") or row.get("email") or "")
    df["tags"] = tags_vals
    df["tier"] = tier_vals
    df["email"] = email_vals
    return df


def _fetch_email_events(
    config: AppConfig, client: CreatorIQClient, network_ids_by_creator: dict[str, str]
) -> pd.DataFrame:
    mapping = config.field_mappings.get("email_events", {})
    max_lookups = config.settings.get("live_sync", "max_email_lookups", default=None)
    items = list(network_ids_by_creator.items())
    if max_lookups is not None:
        items = items[: int(max_lookups)]

    rows: list[dict] = []
    for creator_id, network_id in items:
        try:
            raw_messages = client.fetch_all("publisher_messages", path_params={"network_publisher_id": network_id})
        except Exception:  # noqa: BLE001
            logger.exception("Failed to fetch messages for creator %s (%s)", creator_id, network_id)
            continue
        for record in normalize_records(raw_messages, mapping):
            record["creator_id"] = creator_id
            # See config/field_mappings.yaml's caveat: `IsRead` is an
            # in-platform Message Center flag, not verified email-open
            # tracking. Treat it as a weak/optional "opened" signal only.
            record["opened_at"] = record.get("sent_at") if record.get("is_read") else None
            rows.append(record)

    return pd.DataFrame(rows)


def sync_all(config: AppConfig) -> dict[str, int]:
    client = CreatorIQClient(config)
    engine = get_engine(config.db_path)
    now = datetime.now(timezone.utc)

    campaigns_df = _fetch_campaigns(config, client)
    write_table(engine, "campaigns", campaigns_df)
    record_sync(engine, "campaigns", now)

    logger.info("Syncing enrolled creators (Status=%s)...", config.settings.get("live_sync", "enrolled_status_filter", default="Active"))
    roster_df = _fetch_enrolled_creators(config, client)
    logger.info("Fetched %d enrolled creators", len(roster_df))

    max_campaigns = config.settings.get("live_sync", "max_campaigns", default=None)
    campaign_ids = campaigns_df["campaign_id"].tolist() if not campaigns_df.empty else []
    if max_campaigns is not None:
        campaign_ids = campaign_ids[: int(max_campaigns)]
    logger.info("Syncing posts/activity for %d campaign(s)", len(campaign_ids))

    _, posts_df = _fetch_roster_and_posts(config, client, campaign_ids)
    write_table(engine, "creators", roster_df)
    write_table(engine, "posts", posts_df)
    record_sync(engine, "creators", now)
    record_sync(engine, "posts", now)

    if not posts_df.empty:
        append_link_click_snapshot(engine, posts_df, now)
    links_df = derive_link_click_deltas(engine)
    write_table(engine, "links", links_df)
    record_sync(engine, "links", now)

    email_events_df = pd.DataFrame()
    if not roster_df.empty and "network_publisher_id" in roster_df.columns:
        network_ids = (
            roster_df.dropna(subset=["network_publisher_id"])
            .drop_duplicates(subset=["creator_id"])
            .set_index("creator_id")["network_publisher_id"]
            .astype(str)
            .to_dict()
        )
        email_events_df = _fetch_email_events(config, client, network_ids)
    write_table(engine, "email_events", email_events_df)
    record_sync(engine, "email_events", now)

    return {
        "campaigns": len(campaigns_df),
        "creators": len(roster_df),
        "posts": len(posts_df),
        "links": len(links_df),
        "email_events": len(email_events_df),
    }
