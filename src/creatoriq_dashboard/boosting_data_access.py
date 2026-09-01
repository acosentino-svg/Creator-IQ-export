"""Load Boosting scorecard content for demo and live modes."""
from __future__ import annotations

import pandas as pd

from .boosting_creatoriq import merge_api_with_supplements, posts_to_boosting_content, sync_boosting_from_creatoriq
from .boosting_demo_data import generate_demo_boosting_content
from .boosting_scorecard import CONTENT_RAW_COLUMNS, normalize_content_raw
from .config import AppConfig
from .data_access import load_inputs
from .storage import get_engine, get_last_synced_at, read_table, record_sync, write_table
from datetime import datetime, timezone


def load_boosting_content(config: AppConfig) -> tuple[pd.DataFrame, dict[str, str | None]]:
    """Return (content_raw_df, sync_status)."""
    if config.is_demo:
        return generate_demo_boosting_content(), {"boosting_content": "demo", "posts": "demo"}

    engine = get_engine(config.db_path)
    stored = read_table(engine, "boosting_content")
    if not stored.empty:
        stored = normalize_content_raw(stored)

    inputs, sync_status = load_inputs(config)
    posts_status = sync_status.get("posts")
    boosting_status = get_last_synced_at(engine, "boosting_content") or sync_status.get("boosting_content")

    if stored.empty and not inputs.posts.empty:
        built = posts_to_boosting_content(inputs.posts, config, creators=inputs.creators)
        if not built.empty:
            stored = built
            write_table(engine, "boosting_content", stored)
            record_sync(engine, "boosting_content", datetime.now(timezone.utc))
            boosting_status = datetime.now(timezone.utc).isoformat()

    return stored, {"boosting_content": boosting_status, "posts": posts_status}


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
    inputs, _ = load_inputs(config)
    existing = normalize_content_raw(read_table(engine, "boosting_content"))
    merged = sync_boosting_from_creatoriq(
        config,
        existing_content=existing,
        extra_posts=inputs.posts,
        creators=inputs.creators,
    )
    write_table(engine, "boosting_content", merged)
    record_sync(engine, "boosting_content", datetime.now(timezone.utc))
    return merged


def save_boosting_content(config: AppConfig, content: pd.DataFrame) -> None:
    engine = get_engine(config.db_path)
    write_table(engine, "boosting_content", normalize_content_raw(content))
    record_sync(engine, "boosting_content", datetime.now(timezone.utc))
