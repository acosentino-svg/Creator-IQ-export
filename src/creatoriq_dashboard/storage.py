"""Lightweight SQLite-backed warehouse for normalized CreatorIQ data.

Streamlit pages read from this local cache instead of hitting the CreatorIQ
API on every page load / filter change. `scripts/refresh_data.py` (run via
cron, GitHub Actions, etc.) is what keeps it up to date.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

TABLES = ("creators", "campaigns", "posts", "links", "email_events")


def get_engine(db_path: Path) -> Engine:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{db_path}", future=True)


def write_table(engine: Engine, table_name: str, df: pd.DataFrame, if_exists: str = "replace") -> None:
    df.to_sql(table_name, engine, if_exists=if_exists, index=False)


def read_table(engine: Engine, table_name: str) -> pd.DataFrame:
    try:
        return pd.read_sql_table(table_name, engine)
    except (ValueError, Exception):  # noqa: BLE001 - table may not exist yet
        return pd.DataFrame()


def upsert_rows(engine: Engine, table_name: str, df: pd.DataFrame, key_col: str) -> None:
    """Append new/changed rows, replacing any existing rows with the same key."""
    if df.empty:
        return
    existing = read_table(engine, table_name)
    if existing.empty:
        combined = df
    else:
        combined = pd.concat([existing, df], ignore_index=True)
        combined = combined.drop_duplicates(subset=[key_col], keep="last")
    write_table(engine, table_name, combined, if_exists="replace")


def record_sync(engine: Engine, resource_name: str, synced_at: datetime | None = None) -> None:
    synced_at = synced_at or datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS sync_state ("
                "resource_name TEXT PRIMARY KEY, last_synced_at TEXT)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO sync_state (resource_name, last_synced_at) VALUES (:r, :t) "
                "ON CONFLICT(resource_name) DO UPDATE SET last_synced_at=:t"
            ),
            {"r": resource_name, "t": synced_at.isoformat()},
        )


def get_last_synced_at(engine: Engine, resource_name: str) -> str | None:
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text("SELECT last_synced_at FROM sync_state WHERE resource_name=:r"),
                {"r": resource_name},
            ).fetchone()
        return row[0] if row else None
    except Exception:  # noqa: BLE001 - table doesn't exist on first run
        return None
