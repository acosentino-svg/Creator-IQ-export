"""Creator table filters — posts, links, transactions, search."""
from __future__ import annotations

import pandas as pd


def apply_creator_table_filters(
    df: pd.DataFrame,
    *,
    must_have_posts: bool,
    must_have_links: bool,
    must_have_transactions: bool,
    search: str,
) -> pd.DataFrame:
    view = df.copy()
    if view.empty:
        return view

    if must_have_posts and "first_post" in view.columns:
        view = view[view["first_post"].notna()]
    elif must_have_posts and "lifetime_post_count" in view.columns:
        view = view[view["lifetime_post_count"].fillna(0) > 0]

    if must_have_links and "first_link" in view.columns:
        view = view[view["first_link"].notna()]
    elif must_have_links and "lifetime_link_count" in view.columns:
        view = view[view["lifetime_link_count"].fillna(0) > 0]

    if must_have_transactions and "has_transactions" in view.columns:
        view = view[view["has_transactions"] == True]  # noqa: E712

    if search:
        needle = search.lower()
        mask = pd.Series(False, index=view.index)
        for col in ("name", "handle", "email", "creator_id"):
            if col in view.columns:
                mask = mask | view[col].astype(str).str.lower().str.contains(needle, na=False)
        view = view[mask]

    return view
