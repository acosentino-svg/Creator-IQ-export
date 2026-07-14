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
    creators = read_table(engine, "creators")
    posts = read_table(engine, "posts")
    links = read_table(engine, "links")
    email_events = read_table(engine, "email_events")

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
