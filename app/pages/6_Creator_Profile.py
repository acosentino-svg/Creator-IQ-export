"""Creator Profile: full detail + activity timeline for one creator.
Reached by clicking a creator in Creator Activity / Went Dark, or by
searching directly on this page."""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from common import get_bundle  # noqa: E402

st.set_page_config(page_title="Creator Profile", page_icon="👤", layout="wide")

st.title("👤 Creator Profile")

bundle = get_bundle()
classified = bundle["classified"]
raw = bundle["raw"]

options = classified["creator_id"] + " — " + classified["name"].fillna("")
preselected_id = st.session_state.get("selected_creator_id")
default_index = None
if preselected_id is not None:
    matches = [i for i, cid in enumerate(classified["creator_id"]) if cid == preselected_id]
    default_index = matches[0] if matches else None

selection = st.selectbox("Search for a creator", options, index=default_index, placeholder="Type a name...")
if not selection:
    st.info("Search for a creator above, or select one from the Creator Activity / Went Dark pages.")
    st.stop()

selected_id = selection.split(" — ")[0]
row = classified[classified["creator_id"] == selected_id].iloc[0]

st.subheader(f"{row['name']}  ·  {row.get('handle', '')}")
badge_cols = st.columns(6)
badge_cols[0].metric("Activation State", row["activation_state"])
badge_cols[1].metric("Tier", row.get("tier", "—"))
badge_cols[2].metric("Status", row.get("status", "—"))
badge_cols[3].metric("Lifetime Posts", int(row.get("lifetime_post_count", 0)))
badge_cols[4].metric("Lifetime Links", int(row.get("lifetime_link_count", 0)))
badge_cols[5].metric(
    "Days Since Last Activity",
    f"{row['days_since_last_activity']:.0f}" if pd.notna(row["days_since_last_activity"]) else "—",
)

flags = []
if row.get("is_newly_activated"):
    flags.append("✨ Newly Activated")
if row.get("is_reactivated"):
    flags.append("🔁 Reactivated")
if row.get("is_consistently_active"):
    flags.append("💪 Consistently Active")
if flags:
    st.success(" · ".join(flags))

st.divider()
col1, col2 = st.columns(2)
with col1:
    st.markdown("**Contact & Identity**")
    st.write(f"Email: {row.get('email', '—')}")
    st.write(f"Publisher ID: {row['creator_id']}")
    st.write(f"Tags: {row.get('tags', '—')}")
    st.write(f"Joined: {row.get('joined_date').date() if pd.notna(row.get('joined_date')) else '—'}")

with col2:
    st.markdown("**Activity Dates**")
    st.write(f"First post: {row['first_post'].date() if pd.notna(row['first_post']) else '—'}")
    st.write(f"Last post: {row['last_post'].date() if pd.notna(row['last_post']) else '—'}")
    st.write(f"First link: {row['first_link'].date() if pd.notna(row['first_link']) else '—'}")
    st.write(f"Last link: {row['last_link'].date() if pd.notna(row['last_link']) else '—'}")

col3, col4 = st.columns(2)
with col3:
    st.markdown("**Email Engagement**")
    st.write(f"Last sent: {row['last_email_sent'].date() if pd.notna(row['last_email_sent']) else '—'}")
    st.write(f"Last opened: {row['last_email_opened'].date() if pd.notna(row['last_email_opened']) else 'Never'}")
    st.write(f"Last clicked: {row['last_email_clicked'].date() if pd.notna(row['last_email_clicked']) else 'Never'}")
with col4:
    st.markdown("**Recency**")
    st.write(f"Days since last post: {row['days_since_last_post']:.0f}" if pd.notna(row["days_since_last_post"]) else "Days since last post: —")
    st.write(f"Days since last link: {row['days_since_last_link']:.0f}" if pd.notna(row["days_since_last_link"]) else "Days since last link: —")
    st.write(
        f"Days since last email open: {row['days_since_last_email_open']:.0f}"
        if pd.notna(row["days_since_last_email_open"])
        else "Days since last email open: —"
    )

if row["activation_state"] == "Went Dark":
    went_dark = bundle["went_dark"]
    match = went_dark[went_dark["creator_id"] == selected_id]
    if not match.empty:
        st.warning(f"**Recommended follow-up:** {match.iloc[0]['recommended_action']}")

st.divider()
st.subheader("Activity Timeline")

creator_posts = raw.posts[raw.posts["creator_id"] == selected_id] if not raw.posts.empty else raw.posts
creator_links = raw.links[raw.links["creator_id"] == selected_id] if not raw.links.empty else raw.links
creator_emails = raw.email_events[raw.email_events["creator_id"] == selected_id] if not raw.email_events.empty else raw.email_events

events = []
if not creator_posts.empty:
    events.append(pd.DataFrame({"event_date": pd.to_datetime(creator_posts["posted_at"], utc=True), "event_type": "Post"}))
if not creator_links.empty:
    events.append(pd.DataFrame({"event_date": pd.to_datetime(creator_links["created_at"], utc=True), "event_type": "Link Created"}))
if not creator_emails.empty:
    opened = creator_emails.dropna(subset=["opened_at"])
    if not opened.empty:
        events.append(pd.DataFrame({"event_date": pd.to_datetime(opened["opened_at"], utc=True), "event_type": "Email Opened"}))
    clicked = creator_emails.dropna(subset=["clicked_at"])
    if not clicked.empty:
        events.append(pd.DataFrame({"event_date": pd.to_datetime(clicked["clicked_at"], utc=True), "event_type": "Email Clicked"}))

if events:
    timeline_df = pd.concat(events, ignore_index=True)
    timeline_df["day"] = timeline_df["event_date"].dt.date
    daily = timeline_df.groupby(["day", "event_type"]).size().reset_index(name="count")
    fig = px.bar(daily, x="day", y="count", color="event_type", barmode="stack")
    fig.update_layout(xaxis_title=None, yaxis_title="Events", legend_title=None)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("This creator has no recorded posts, links, or email activity yet.")
