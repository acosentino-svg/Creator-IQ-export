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


def _filters_from_session() -> dict:
    return {
        "must_have_posts": st.session_state.get("report_must_have_posts", False),
        "must_have_links": st.session_state.get("report_must_have_links", False),
        "must_have_transactions": st.session_state.get("report_must_have_transactions", False),
        "search": str(st.session_state.get("report_search_creator", "")).strip().lower(),
    }


def render_active_creator_table(summary: pd.DataFrame, classified: pd.DataFrame) -> None:
    filters = _filters_from_session()
    enrich_cols = [
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
        if c in summary.columns
    ]
    base = classified.merge(summary[["creator_id", *[c for c in enrich_cols if c not in classified.columns]]], on="creator_id", how="left")
    for col in enrich_cols:
        if col in summary.columns and col not in base.columns:
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
