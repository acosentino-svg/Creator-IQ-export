"""Active Creator Report — matches creator-activity-dash #active-creator-report."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from boosting_activity.table_filters import apply_creator_table_filters

DISPLAY_COLUMNS = {
    "name": "Name",
    "handle": "Handle",
    "email": "Email",
    "creator_id": "Publisher ID",
    "tags": "Tags",
    "activation_state": "Activation State",
    "last_post": "Last Post",
    "last_link": "Last Link",
    "posts_in_range": "Posts (activity window)",
    "links_in_range": "Links (activity window)",
    "lifetime_post_count": "Lifetime Posts",
    "lifetime_link_count": "Lifetime Links",
    "order_count": "Orders",
    "total_sales": "Total Sales",
    "total_commission": "Commission",
}


def render_filter_bar() -> dict:
    """Primary filters shown above the table (same labels as creator-activity-dash)."""
    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
    with c1:
        must_posts = st.checkbox("Must have posts", key="report_must_have_posts")
    with c2:
        must_links = st.checkbox("Must have links", key="report_must_have_links")
    with c3:
        must_txn = st.checkbox("Must have transactions", key="report_must_have_transactions")
    with c4:
        search = st.text_input("Search creator", key="report_search_creator", placeholder="Name, handle, email, ID")
    return {
        "must_have_posts": must_posts,
        "must_have_links": must_links,
        "must_have_transactions": must_txn,
        "search": search.strip().lower(),
    }


def render_active_creator_table(summary: pd.DataFrame, classified: pd.DataFrame) -> None:
    filters = render_filter_bar()
    extra_cols = [
        c
        for c in (
            "first_post",
            "first_link",
            "last_post",
            "last_link",
            "lifetime_post_count",
            "lifetime_link_count",
            "posts_in_range",
            "links_in_range",
            "total_sales",
            "total_commission",
            "order_count",
            "has_transactions",
        )
        if c in summary.columns and c not in classified.columns
    ]
    if extra_cols:
        base = classified.merge(summary[["creator_id", *extra_cols]], on="creator_id", how="left")
    else:
        base = classified.copy()
        for col in extra_cols:
            if col in summary.columns:
                base[col] = base["creator_id"].map(summary.set_index("creator_id")[col])

    view = apply_creator_table_filters(
        base,
        must_have_posts=filters["must_have_posts"],
        must_have_links=filters["must_have_links"],
        must_have_transactions=filters["must_have_transactions"],
        search=filters["search"],
    )

    st.caption(f"Showing **{len(view):,}** of **{len(base):,}** boosting creators in scope")

    cols = [c for c in DISPLAY_COLUMNS if c in view.columns]
    display = view[cols].rename(columns=DISPLAY_COLUMNS)
    for col in ("Last Post", "Last Link"):
        if col in display.columns:
            display[col] = pd.to_datetime(display[col], errors="coerce").dt.date.astype(str).replace("NaT", "")

    st.dataframe(display, use_container_width=True, hide_index=True)
    st.download_button(
        "Export to CSV",
        data=display.to_csv(index=False).encode("utf-8"),
        file_name="boosting_active_creators.csv",
        mime="text/csv",
    )
