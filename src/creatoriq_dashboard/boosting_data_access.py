"""Load Boosting scorecard content for demo and live modes."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pandas as pd

from .boosting_creatoriq import merge_api_with_supplements, posts_to_boosting_content, sync_boosting_from_creatoriq
from .boosting_demo_data import generate_demo_boosting_content
from .boosting_scorecard import CONTENT_RAW_COLUMNS, normalize_content_raw
from .config import AppConfig
from .data_access import load_inputs
from .storage import get_engine, get_last_synced_at, read_table, record_sync, write_table

logger = logging.getLogger(__name__)


def _parse_sync_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (TypeError, ValueError):
        return None


def should_auto_sync_boosting(
    config: AppConfig,
    content: pd.DataFrame,
    last_synced_at: str | None,
) -> bool:
    """True when live mode should pull from CreatorIQ without a manual sync click."""
    if config.is_demo:
        return False
    cfg = config.settings.get("boosting", default={}) or {}
    if not cfg.get("auto_sync_on_load", True):
        return False
    if content.empty:
        return True
    stale_hours = cfg.get("sync_stale_hours", 24)
    try:
        stale_hours = float(stale_hours)
    except (TypeError, ValueError):
        stale_hours = 24.0
    if stale_hours <= 0:
        return False
    synced = _parse_sync_time(last_synced_at)
    if synced is None:
        return True
    return datetime.now(timezone.utc) - synced > timedelta(hours=stale_hours)


def load_boosting_content(config: AppConfig) -> tuple[pd.DataFrame, dict[str, str | None]]:
    """Return (content_raw_df, sync_status). Auto-syncs from CreatorIQ API when configured."""
    if config.is_demo:
        return generate_demo_boosting_content(), {"boosting_content": "demo", "posts": "demo"}

    engine = get_engine(config.db_path)
    stored = read_table(engine, "boosting_content")
    if not stored.empty:
        stored = normalize_content_raw(stored)

    boosting_status = get_last_synced_at(engine, "boosting_content")
    sync_status: dict[str, str | None] = {"boosting_content": boosting_status, "posts": None}

    if should_auto_sync_boosting(config, stored, boosting_status):
        try:
            logger.info("Auto-syncing boosting scorecard from CreatorIQ API...")
            stored = sync_boosting_from_creatoriq(config, existing_content=stored)
            write_table(engine, "boosting_content", stored)
            now = datetime.now(timezone.utc)
            record_sync(engine, "boosting_content", now)
            boosting_status = now.isoformat()
            sync_status["boosting_content"] = boosting_status
        except Exception:  # noqa: BLE001
            logger.exception("Boosting auto-sync failed")

    if stored.empty:
        inputs, input_status = load_inputs(config)
        sync_status["posts"] = input_status.get("posts")
        if not inputs.posts.empty:
            built = posts_to_boosting_content(inputs.posts, config, creators=inputs.creators)
            if not built.empty:
                stored = built
                write_table(engine, "boosting_content", stored)
                now = datetime.now(timezone.utc)
                record_sync(engine, "boosting_content", now)
                sync_status["boosting_content"] = now.isoformat()

    return stored, sync_status


def rebuild_boosting_from_cached_posts(config: AppConfig) -> pd.DataFrame:
    """Rebuild boosting_content from the posts already in warehouse.db."""
    engine = get_engine(config.db_path)
    existing = normalize_content_raw(read_table(engine, "boosting_content"))
    inputs, _ = load_inputs(config)
    api_content = posts_to_boosting_content(inputs.posts, config, creators=inputs.creators)
    merged = merge_api_with_supplements(api_content, existing)
    write_table(engine, "boosting_content", merged)
    record_sync(engine, "boosting_content", datetime.now(timezone.utc))
    return merged


def sync_and_store_boosting_content(config: AppConfig) -> pd.DataFrame:
    """Pull boosting campaigns from CreatorIQ API and persist content raw."""
    engine = get_engine(config.db_path)
    existing = normalize_content_raw(read_table(engine, "boosting_content"))
    merged = sync_boosting_from_creatoriq(config, existing_content=existing)
    write_table(engine, "boosting_content", merged)
    record_sync(engine, "boosting_content", datetime.now(timezone.utc))
    return merged


def save_boosting_content(config: AppConfig, content: pd.DataFrame) -> None:
    engine = get_engine(config.db_path)
    write_table(engine, "boosting_content", normalize_content_raw(content))
    record_sync(engine, "boosting_content", datetime.now(timezone.utc))
