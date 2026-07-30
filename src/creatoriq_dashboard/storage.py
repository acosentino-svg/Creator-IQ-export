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

TABLES = ("creators", "campaigns", "posts", "links", "link_clicks", "email_events", "active_member_links")
LINK_SNAPSHOT_TABLE = "link_click_snapshots"


def get_engine(db_path: Path) -> Engine:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{db_path}", future=True)


def write_table(engine: Engine, table_name: str, df: pd.DataFrame, if_exists: str = "replace") -> None:
    if df.empty and len(df.columns) == 0:
        # A DataFrame with zero rows AND zero columns (e.g. pd.DataFrame([]))
        # can't be turned into a CREATE TABLE statement -- and there's
        # nothing useful to persist anyway. read_table() already returns an
        # empty frame for a missing table, so just skip the write.
        return
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


def append_link_click_snapshot(engine: Engine, posts_df: pd.DataFrame, snapshot_at: datetime) -> None:
    """CreatorIQ exposes link clicks as a cumulative-to-date counter per
    post, not discrete click events. Append the current counter values as a
    dated snapshot; `derive_link_click_deltas` below turns consecutive
    snapshots into day-over-day deltas the rest of the app can treat as
    "link click activity" the same way it treats discrete post events.
    """
    if posts_df.empty or "link_clicks" not in posts_df.columns:
        return
    snapshot = posts_df[["post_id", "creator_id", "campaign_id", "link_clicks"]].copy()
    snapshot["link_clicks"] = pd.to_numeric(snapshot["link_clicks"], errors="coerce").fillna(0)
    snapshot["snapshot_at"] = snapshot_at.isoformat()
    with engine.begin() as conn:
        conn.execute(
            text(
                f"CREATE TABLE IF NOT EXISTS {LINK_SNAPSHOT_TABLE} ("
                "post_id TEXT, creator_id TEXT, campaign_id TEXT, link_clicks REAL, snapshot_at TEXT)"
            )
        )
    snapshot.to_sql(LINK_SNAPSHOT_TABLE, engine, if_exists="append", index=False)


def derive_link_click_deltas(engine: Engine) -> pd.DataFrame:
    """Turn accumulated link_click_snapshots into link *click* event rows:
    one row per (post, snapshot) where the cumulative click counter increased,
    with `clicks` holding the size of that increase.

    These are NOT link-creation events — do not use them for "posted but never
    linked" or other activation metrics. Persist to the `link_clicks` table.
    """
    snapshots = read_table(engine, LINK_SNAPSHOT_TABLE)
    if snapshots.empty:
        return pd.DataFrame(columns=["event_id", "creator_id", "campaign_id", "link_id", "clicked_at", "clicks"])

    snapshots["snapshot_at"] = pd.to_datetime(snapshots["snapshot_at"], utc=True, errors="coerce")
    snapshots = snapshots.sort_values(["post_id", "snapshot_at"])
    snapshots["previous_clicks"] = snapshots.groupby("post_id")["link_clicks"].shift(1)
    snapshots["delta"] = snapshots["link_clicks"] - snapshots["previous_clicks"]

    increased = snapshots[snapshots["delta"] > 0].copy()
    if increased.empty:
        return pd.DataFrame(columns=["event_id", "creator_id", "campaign_id", "link_id", "clicked_at", "clicks"])

    increased["event_id"] = (
        increased["post_id"].astype(str) + "_" + increased["snapshot_at"].astype(str)
    ).map(lambda s: f"linkdelta_{s}")
    increased = increased.rename(columns={"post_id": "link_id", "snapshot_at": "clicked_at", "delta": "clicks"})
    return increased[["event_id", "creator_id", "campaign_id", "link_id", "clicked_at", "clicks"]].reset_index(drop=True)


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


SYNC_RESOURCES = (
    "creators",
    "campaigns",
    "posts",
    "links",
    "link_clicks",
    "email_events",
    "active_member_links",
)


def get_sync_status_map(engine: Engine) -> dict[str, str | None]:
    """Read last-sync timestamps without loading any data tables."""
    return {name: get_last_synced_at(engine, name) for name in SYNC_RESOURCES}


def count_table_rows(engine: Engine, table_name: str) -> int:
    if table_name not in TABLES:
        return 0
    try:
        with engine.begin() as conn:
            row = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).fetchone()
        return int(row[0]) if row else 0
    except Exception:  # noqa: BLE001 - table may not exist yet
        return 0


def count_distinct_column(engine: Engine, table_name: str, column: str) -> int:
    if table_name not in TABLES:
        return 0
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text(f"SELECT COUNT(DISTINCT {column}) FROM {table_name} WHERE {column} IS NOT NULL")
            ).fetchone()
        return int(row[0]) if row else 0
    except Exception:  # noqa: BLE001
        return 0


def count_enrolled_creators_with_posts(engine: Engine) -> int:
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text(
                    "SELECT COUNT(DISTINCT c.creator_id) FROM creators c "
                    "INNER JOIN posts p ON c.creator_id = p.creator_id"
                )
            ).fetchone()
        return int(row[0]) if row else 0
    except Exception:  # noqa: BLE001
        return 0


def count_posted_without_link_creation(engine: Engine) -> int:
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text(
                    "SELECT COUNT(DISTINCT c.creator_id) FROM creators c "
                    "INNER JOIN posts p ON c.creator_id = p.creator_id "
                    "WHERE NOT EXISTS ("
                    "  SELECT 1 FROM links l "
                    "  WHERE l.creator_id = c.creator_id AND l.created_at IS NOT NULL"
                    ") AND NOT EXISTS ("
                    "  SELECT 1 FROM active_member_links aml "
                    "  WHERE aml.creator_id = c.creator_id AND aml.last_link IS NOT NULL"
                    ")"
                )
            ).fetchone()
        return int(row[0]) if row else 0
    except Exception:  # noqa: BLE001
        return 0
