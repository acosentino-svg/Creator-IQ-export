"""Persist CreatorIQ campaign 2206666 roster (+ WBP scan) for boosting scope."""
from __future__ import annotations

import logging

import pandas as pd

from .config import AppConfig
from .storage import get_engine, read_table, write_table

logger = logging.getLogger(__name__)


def load_boosting_roster_creator_ids(config: AppConfig) -> set[str]:
    """Creator IDs last synced from campaign roster / WBP publisher scan."""
    if config.is_demo:
        return set()
    try:
        df = read_table(get_engine(config.db_path), "boosting_roster")
    except Exception:  # noqa: BLE001
        logger.debug("No boosting_roster table yet", exc_info=True)
        return set()
    if df.empty or "creator_id" not in df.columns:
        return set()
    return set(df["creator_id"].astype(str).str.strip()) - {"", "nan"}


def persist_boosting_roster(config: AppConfig, creators: pd.DataFrame) -> None:
    if config.is_demo or creators is None or creators.empty or "creator_id" not in creators.columns:
        return
    keep = [
        c
        for c in ("creator_id", "name", "tags", "handle", "email", "network_publisher_id")
        if c in creators.columns
    ]
    roster = creators[keep].drop_duplicates(subset=["creator_id"], keep="last")
    write_table(get_engine(config.db_path), "boosting_roster", roster)
