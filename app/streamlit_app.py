"""Creator Activation Dashboard — Dashboard Overview page.

Run with: streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from common import get_bundle  # noqa: E402

st.set_page_config(page_title="Dashboard Overview", page_icon="📊", layout="wide")

st.title("📊 Creator Activation Dashboard")
st.caption(
    "Understand creator engagement, spot who needs outreach, and track activation over time. "
    "Adjust the date range and activation thresholds in the sidebar — every page updates live."
)

bundle = get_bundle()
kpis = bundle["kpis"]
controls = bundle["controls"]
classified = bundle["classified"]

st.subheader("Program Overview")
row1 = st.columns(5)
row1[0].metric("Total Creators", f"{kpis['total_creators']:,}")
row1[1].metric("Active", f"{kpis['active_creators']:,}")
row1[2].metric("Inactive", f"{kpis['inactive_creators']:,}")
row1[3].metric("Never Activated", f"{kpis['never_activated_creators']:,}")
row1[4].metric("Went Dark", f"{kpis['went_dark_creators']:,}")

row2 = st.columns(5)
row2[0].metric("Newly Activated", f"{kpis['newly_activated_creators']:,}")
row2[1].metric("Reactivated", f"{kpis['reactivated_creators']:,}")
row2[2].metric("Consistently Active", f"{kpis['consistently_active_creators']:,}")
row2[3].metric(f"Posts ({controls['preset']})", f"{kpis['total_posts_in_range']:,}")
row2[4].metric(f"Links Created ({controls['preset']})", f"{kpis['total_links_in_range']:,}")

st.caption(
    f"Date range: **{controls['range_start'].date()} → {controls['range_end'].date()}** · "
    f"Active window: **{controls['active_days']} days** · Went Dark after: **{controls['went_dark_days']} days**"
)

st.divider()

left, right = st.columns([3, 2])

with left:
    st.subheader("Activation State Breakdown")
    state_order = ["Active", "Inactive", "Went Dark", "Never Activated"]
    state_counts = classified["activation_state"].value_counts().reindex(state_order).fillna(0).reset_index()
    state_counts.columns = ["state", "count"]
    color_map = {
        "Active": "#2ecc71",
        "Inactive": "#f1c40f",
        "Went Dark": "#e74c3c",
        "Never Activated": "#95a5a6",
    }
    fig = px.bar(state_counts, x="state", y="count", color="state", color_discrete_map=color_map, text="count")
    fig.update_layout(showlegend=False, xaxis_title=None, yaxis_title="Creators")
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("Active Sub-Segments")
    sub_df = pd.DataFrame(
        {
            "segment": ["Newly Activated", "Reactivated", "Consistently Active"],
            "count": [
                kpis["newly_activated_creators"],
                kpis["reactivated_creators"],
                kpis["consistently_active_creators"],
            ],
        }
    )
    fig2 = px.bar(sub_df, x="segment", y="count", color="segment", text="count")
    fig2.update_layout(showlegend=False, xaxis_title=None, yaxis_title="Creators")
    st.plotly_chart(fig2, use_container_width=True)

st.divider()

st.subheader("Activity Timeline (Posts vs. Links Created)")
timeline = bundle["timeline"]
if timeline.empty:
    st.info("No activity data in this range.")
else:
    fig3 = px.line(timeline, x="date", y="count", color="activity_type", markers=False)
    fig3.update_layout(xaxis_title=None, yaxis_title="Daily count", legend_title=None)
    st.plotly_chart(fig3, use_container_width=True)

spikes = bundle["spikes"]
recent_spikes = spikes[spikes["is_spike"]] if not spikes.empty else spikes
if not recent_spikes.empty:
    st.warning(
        f"⚡ {len(recent_spikes)} spike day(s) detected — see the **Momentum** page for which creators are driving them."
    )

st.divider()
st.caption(
    "Use the sidebar to jump to **Creator Activity** (full roster + CSV export), **New Activations**, "
    "**Momentum** (spikes this week), **Went Dark** (who needs outreach), and **Email Engagement**."
)
