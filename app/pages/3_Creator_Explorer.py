"""Creator Explorer: searchable/filterable roster with drill-down into a
single creator's full activity timeline."""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from common import get_bundle, render_mode_badge  # noqa: E402

st.set_page_config(page_title="Creator Explorer", page_icon="🔍", layout="wide")
render_mode_badge()

st.title("🔍 Creator Explorer")

bundle = get_bundle()
scored = bundle["scored"]
email_engagement = bundle["email_engagement"]
inputs = bundle["inputs"]

merged = scored.merge(
    email_engagement[["creator_id", "open_rate", "days_since_last_open", "is_cold"]],
    on="creator_id",
    how="left",
)

col1, col2, col3 = st.columns(3)
with col1:
    tiers = sorted(merged["tier"].dropna().unique())
    tier_filter = st.multiselect("Tier", tiers, default=list(tiers))
with col2:
    segments = ["Active", "Cooling Off", "At Risk", "Dormant", "Never Activated"]
    segment_filter = st.multiselect("Segment", segments, default=segments)
with col3:
    search = st.text_input("Search by name")

view = merged[merged["tier"].isin(tier_filter) & merged["activation_segment"].isin(segment_filter)]
if search:
    view = view[view["name"].str.contains(search, case=False, na=False)]

st.dataframe(
    view[
        [
            "creator_id",
            "name",
            "tier",
            "activation_segment",
            "activation_score",
            "post_count_all_time",
            "link_click_count_all_time",
            "days_since_last_active",
            "open_rate",
            "days_since_last_open",
        ]
    ].sort_values("activation_score", ascending=False),
    use_container_width=True,
    hide_index=True,
    column_config={
        "open_rate": st.column_config.ProgressColumn("email open_rate", format="%.0f%%", min_value=0, max_value=1),
        "activation_score": st.column_config.ProgressColumn("activation_score", min_value=0, max_value=100),
    },
)

st.divider()
st.subheader("Drill into one creator")
options = view["creator_id"] + " — " + view["name"].fillna("")
if options.empty:
    st.info("No creators match the current filters.")
    st.stop()

selection = st.selectbox("Creator", options)
selected_id = selection.split(" — ")[0]

creator_row = merged[merged["creator_id"] == selected_id].iloc[0]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Activation score", f"{creator_row['activation_score']:.0f}")
c2.metric("Segment", creator_row["activation_segment"])
c3.metric("Days since last active", f"{creator_row['days_since_last_active']:.0f}" if pd.notna(creator_row["days_since_last_active"]) else "—")
c4.metric("Email open rate", f"{creator_row['open_rate'] * 100:.0f}%" if pd.notna(creator_row["open_rate"]) else "—")

creator_posts = inputs.posts[inputs.posts["creator_id"] == selected_id] if not inputs.posts.empty else inputs.posts
creator_links = inputs.links[inputs.links["creator_id"] == selected_id] if not inputs.links.empty else inputs.links
creator_emails = (
    inputs.email_events[inputs.email_events["creator_id"] == selected_id]
    if not inputs.email_events.empty
    else inputs.email_events
)

events = []
if not creator_posts.empty:
    events.append(creator_posts.assign(event_type="Post", event_date=pd.to_datetime(creator_posts["posted_at"], utc=True)))
if not creator_links.empty:
    events.append(creator_links.assign(event_type="Link Click", event_date=pd.to_datetime(creator_links["clicked_at"], utc=True)))
if not creator_emails.empty:
    opened = creator_emails.dropna(subset=["opened_at"])
    if not opened.empty:
        events.append(opened.assign(event_type="Email Open", event_date=pd.to_datetime(opened["opened_at"], utc=True)))

if events:
    timeline_df = pd.concat([e[["event_date", "event_type"]] for e in events], ignore_index=True)
    timeline_df["day"] = timeline_df["event_date"].dt.date
    daily = timeline_df.groupby(["day", "event_type"]).size().reset_index(name="count")
    fig = px.bar(daily, x="day", y="count", color="event_type", barmode="stack")
    fig.update_layout(xaxis_title=None, yaxis_title="Events", legend_title=None)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("This creator has no recorded posts, link clicks, or email opens yet.")
