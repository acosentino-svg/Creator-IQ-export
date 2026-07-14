"""Single entry point the Streamlit app uses to get data, regardless of
whether we're in demo mode (synthetic data, no network/DB) or live mode
(reads the local SQLite cache populated by scripts/refresh_data.py).
"""
from __future__ import annotations

import pandas as pd

from .config import AppConfig
from .demo_data import generate_demo_data
from .metrics import ActivationInputs
from .storage import get_engine, get_last_synced_at, read_table

# Minimal column shape for each table when the live SQLite cache doesn't
# exist yet (e.g. live mode selected but `scripts/refresh_data.py` hasn't
# been run once). Without this, a table read as a bare `pd.DataFrame()`
# (zero columns) breaks every downstream merge/groupby that expects
# `creator_id` etc. to exist, even on an empty dataset.
_EMPTY_TABLE_COLUMNS: dict[str, list[str]] = {
    "creators": ["creator_id", "name", "handle", "email", "status", "tier", "tags", "joined_date"],
    "campaigns": ["campaign_id", "campaign_name", "status", "start_date", "end_date"],
    "posts": ["post_id", "creator_id", "campaign_id", "campaign_name", "platform", "post_type", "posted_at"],
    "links": ["link_id", "creator_id", "label", "destination_url", "created_at", "campaign_id"],
    "email_events": ["event_id", "creator_id", "message_id", "subject", "sent_at", "opened_at", "clicked_at"],
}


def _read_table_with_shape(engine, table_name: str) -> pd.DataFrame:
    df = read_table(engine, table_name)
    if df.empty and df.columns.empty and table_name in _EMPTY_TABLE_COLUMNS:
        return pd.DataFrame(columns=_EMPTY_TABLE_COLUMNS[table_name])
    return df


def load_inputs(config: AppConfig) -> tuple[ActivationInputs, dict[str, str | None]]:
    """Returns (ActivationInputs, sync_status). sync_status maps resource
    name -> last_synced_at ISO string (or None). In demo mode, sync_status
    values are all "demo".
    """
    if config.is_demo:
        demo = generate_demo_data()
        sync_status = {name: "demo" for name in ("creators", "campaigns", "posts", "links", "email_events")}
        return (
            ActivationInputs(
                creators=demo.creators,
                posts=demo.posts,
                links=demo.links,
                email_events=demo.email_events,
            ),
            sync_status,
        )

    engine = get_engine(config.db_path)
    creators = _read_table_with_shape(engine, "creators")
    posts = _read_table_with_shape(engine, "posts")
    links = _read_table_with_shape(engine, "links")
    email_events = _read_table_with_shape(engine, "email_events")

    for date_col, df in (("joined_date", creators),):
        if not df.empty and date_col in df.columns:
            df[date_col] = pd.to_datetime(df[date_col], utc=True, errors="coerce")

    sync_status = {
        name: get_last_synced_at(engine, name)
        for name in ("creators", "campaigns", "posts", "links", "email_events")
    }

    return (
        ActivationInputs(creators=creators, posts=posts, links=links, email_events=email_events),
        sync_status,
    )
