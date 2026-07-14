"""Pulls data from the CreatorIQ API, normalizes it, and lands it in the
local SQLite warehouse that the Streamlit app reads from.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from .api_client import CreatorIQClient
from .config import AppConfig
from .normalize import normalize_records
from .storage import get_engine, get_last_synced_at, record_sync, upsert_rows

logger = logging.getLogger(__name__)

RESOURCE_KEY_COLS = {
    "creators": "creator_id",
    "campaigns": "campaign_id",
    "posts": "post_id",
    "links": "event_id",
    "email_events": "event_id",
}

# Resources that support incremental "updated_since" pulls.
INCREMENTAL_RESOURCES = {"posts", "links", "email_events"}


def sync_resource(config: AppConfig, client: CreatorIQClient, resource_name: str) -> pd.DataFrame:
    engine = get_engine(config.db_path)
    mapping = config.field_mappings.get(resource_name, {})
    if not mapping:
        raise ValueError(f"No field mapping configured for resource '{resource_name}'")

    extra_params = {}
    if resource_name in INCREMENTAL_RESOURCES:
        since = get_last_synced_at(engine, resource_name)
        if since:
            extra_params["since"] = since

    raw_records = client.fetch_all(resource_name, extra_params=extra_params or None)
    normalized = normalize_records(raw_records, mapping)
    df = pd.DataFrame(normalized)

    key_col = RESOURCE_KEY_COLS[resource_name]
    if not df.empty:
        upsert_rows(engine, resource_name, df, key_col=key_col)
    record_sync(engine, resource_name, datetime.now(timezone.utc))
    logger.info("Synced %d %s records", len(df), resource_name)
    return df


def sync_all(config: AppConfig) -> dict[str, int]:
    client = CreatorIQClient(config)
    counts: dict[str, int] = {}
    for resource_name in RESOURCE_KEY_COLS:
        df = sync_resource(config, client, resource_name)
        counts[resource_name] = len(df)
    return counts
