"""Scope activation-dashboard raw inputs to the Wayfair Boosting program."""
from __future__ import annotations

import pandas as pd

from .boosting_roster import load_boosting_roster_creator_ids
from .boosting_rules import boosting_program_creator_ids, is_boosting_creator_post, wbp_creator_ids
from .config import AppConfig
from .metrics import RawData


def _filter_by_creator_ids(df: pd.DataFrame | None, creator_ids: set[str], col: str = "creator_id") -> pd.DataFrame:
    if df is None:
        return pd.DataFrame()
    if df.empty or not creator_ids or col not in df.columns:
        return df.copy() if df is not None else pd.DataFrame()
    ids = df[col].astype(str)
    return df[ids.isin(creator_ids)].copy()


def filter_raw_for_boosting_program(raw: RawData, config: AppConfig) -> RawData:
    """Creators in program: WBP tag and/or campaign 2206666 roster. Posts: boosting campaign/WBP only.

    Links, emails, and optional tables are limited to those creators so went-dark and
    outreach views match the boosting cohort.
    """
    roster_ids = load_boosting_roster_creator_ids(config)
    all_posts = raw.posts.copy() if raw.posts is not None else pd.DataFrame()
    active_ids = boosting_program_creator_ids(
        raw.creators,
        all_posts,
        config,
        campaign_roster_ids=roster_ids,
    )
    wbp = wbp_creator_ids(raw.creators, config)
    posts = all_posts

    if not posts.empty:
        mask = posts.apply(lambda row: is_boosting_creator_post(row, config=config, wbp_ids=wbp), axis=1)
        posts = posts[mask]
    creators = raw.creators.copy()
    if not creators.empty and active_ids:
        creators = creators[creators["creator_id"].astype(str).isin(active_ids)]

    return RawData(
        creators=creators,
        posts=posts,
        links=_filter_by_creator_ids(raw.links, active_ids),
        email_events=_filter_by_creator_ids(raw.email_events, active_ids),
        link_clicks=_filter_by_creator_ids(raw.link_clicks, active_ids) if raw.link_clicks is not None else None,
        active_member_links=(
            _filter_by_creator_ids(raw.active_member_links, active_ids)
            if raw.active_member_links is not None
            else None
        ),
    )


def boosting_program_scope_enabled() -> bool:
    import os

    return os.environ.get("CREATORIQ_BOOSTING_PROGRAM_ONLY", "").strip().lower() in ("1", "true", "yes")
