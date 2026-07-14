"""Creator Activity: searchable, filterable, sortable roster with every
field a Creator/Community Manager needs, plus CSV export."""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import streamlit as st  # noqa: E402

from common import get_bundle, go_to_creator_profile  # noqa: E402

st.set_page_config(page_title="Creator Activity", page_icon="📋", layout="wide")

st.title("📋 Creator Activity")
st.caption("One row per creator. Search, filter, sort, export to CSV, or select a row to open their full profile.")

bundle = get_bundle()
classified = bundle["classified"]

DISPLAY_COLUMNS = {
    "name": "Name",
    "handle": "Handle",
    "email": "Email",
    "creator_id": "Publisher ID",
    "tags": "Tags",
    "status": "Status",
    "activation_state": "Activation State",
    "first_post": "First Post Date",
    "last_post": "Last Post Date",
    "first_link": "First Link Date",
    "last_link": "Last Link Date",
    "last_email_sent": "Last Email Sent",
    "last_email_opened": "Last Email Opened",
    "last_email_clicked": "Last Email Clicked",
    "days_since_last_post": "Days Since Last Post",
    "days_since_last_link": "Days Since Last Link",
    "days_since_last_email_open": "Days Since Last Email Open",
    "days_since_last_email_click": "Days Since Last Email Click",
    "lifetime_post_count": "Lifetime Posts",
    "lifetime_link_count": "Lifetime Links",
    "posts_in_range": "Posts (selected range)",
    "links_in_range": "Links (selected range)",
}

available_cols = [c for c in DISPLAY_COLUMNS if c in classified.columns]

# --- Filters ---
col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    search = st.text_input("🔎 Search by name, handle, or email")
with col2:
    all_statuses = sorted(classified["status"].dropna().unique()) if "status" in classified.columns else []
    status_filter = st.multiselect("Status", all_statuses, default=list(all_statuses))
with col3:
    all_states = ["Active", "Inactive", "Went Dark", "Never Activated"]
    state_filter = st.multiselect("Activation State", all_states, default=list(all_states))

all_tags: set[str] = set()
if "tags" in classified.columns:
    for tag_str in classified["tags"].dropna():
        all_tags.update(t.strip() for t in str(tag_str).split(",") if t.strip())
tag_filter = st.multiselect("Tags", sorted(all_tags))

view = classified.copy()
if status_filter and "status" in view.columns:
    view = view[view["status"].isin(status_filter)]
if state_filter:
    view = view[view["activation_state"].isin(state_filter)]
if tag_filter and "tags" in view.columns:
    view = view[view["tags"].apply(lambda t: any(tag in str(t) for tag in tag_filter))]
if search:
    needle = search.lower()
    haystacks = [view.get(c, "").astype(str).str.lower() for c in ("name", "handle", "email") if c in view.columns]
    if haystacks:
        mask = haystacks[0].str.contains(needle, na=False)
        for h in haystacks[1:]:
            mask = mask | h.str.contains(needle, na=False)
        view = view[mask]

st.caption(f"Showing **{len(view):,}** of **{len(classified):,}** creators")

display_df = view[available_cols].rename(columns=DISPLAY_COLUMNS).reset_index(drop=True)

event = st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    key="creator_activity_table",
)

st.download_button(
    "⬇️ Export filtered table to CSV",
    data=display_df.to_csv(index=False).encode("utf-8"),
    file_name="creator_activity.csv",
    mime="text/csv",
)

selection = getattr(event, "selection", None)
selected_rows = selection.get("rows") if isinstance(selection, dict) else getattr(selection, "rows", None)
if selected_rows:
    selected_creator_id = view.iloc[selected_rows[0]]["creator_id"]
    st.info(f"Selected: **{view.iloc[selected_rows[0]]['name']}**")
    if st.button("Open full profile →"):
        go_to_creator_profile(selected_creator_id)
