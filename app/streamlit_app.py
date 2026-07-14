"""Creator Activation Dashboard — Overview page.

Run with: streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from common import get_bundle, get_config, render_mode_badge  # noqa: E402

st.set_page_config(page_title="Activation Dashboard — Overview", page_icon="📊", layout="wide")

config = get_config()
render_mode_badge()

st.title("📊 Creator Activation Dashboard")
st.caption("Powered by CreatorIQ data · Activity, spikes, and email engagement in one place")

bundle = get_bundle()
scored = bundle["scored"]
email_engagement = bundle["email_engagement"]
needs_attention = bundle["needs_attention"]

total_creators = len(scored)
segment_counts = scored["activation_segment"].value_counts()
active_count = int(segment_counts.get("Active", 0))
active_rate = (active_count / total_creators * 100) if total_creators else 0.0
cold_email_count = int(email_engagement["is_cold"].sum()) if not email_engagement.empty else 0
avg_score = scored["activation_score"].mean() if not scored.empty else 0.0

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Creators", f"{total_creators:,}")
col2.metric("Active (last window)", f"{active_count:,}", f"{active_rate:.1f}% of program")
col3.metric("Avg. Activation Score", f"{avg_score:.0f} / 100")
col4.metric("Needs Attention", f"{len(needs_attention):,}")
col5.metric("Email-Cold Creators", f"{cold_email_count:,}")

st.divider()

left, right = st.columns([3, 2])

with left:
    st.subheader("Activation Segments")
    seg_order = ["Active", "Cooling Off", "At Risk", "Dormant", "Never Activated"]
    seg_df = segment_counts.reindex(seg_order).fillna(0).reset_index()
    seg_df.columns = ["segment", "count"]
    color_map = {
        "Active": "#2ecc71",
        "Cooling Off": "#f1c40f",
        "At Risk": "#e67e22",
        "Dormant": "#e74c3c",
        "Never Activated": "#95a5a6",
    }
    fig = px.bar(
        seg_df,
        x="segment",
        y="count",
        color="segment",
        color_discrete_map=color_map,
        text="count",
    )
    fig.update_layout(showlegend=False, xaxis_title=None, yaxis_title="Creators")
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("Score Distribution")
    fig2 = px.histogram(scored, x="activation_score", nbins=20, color_discrete_sequence=["#3498db"])
    fig2.update_layout(xaxis_title="Activation score (0-100)", yaxis_title="Creators")
    st.plotly_chart(fig2, use_container_width=True)

st.divider()

st.subheader("Recent Activity Timeline (Posts vs. Link Clicks)")
timeline = bundle["timeline"]
if timeline.empty:
    st.info("No activity data yet.")
else:
    fig3 = px.line(
        timeline,
        x="date",
        y="count",
        color="activity_type",
        markers=False,
    )
    fig3.update_layout(xaxis_title=None, yaxis_title="Daily count", legend_title=None)
    st.plotly_chart(fig3, use_container_width=True)

spikes = bundle["spikes"]
recent_spikes = spikes[spikes["is_spike"]].sort_values("date", ascending=False).head(8) if not spikes.empty else spikes
if not recent_spikes.empty:
    st.warning(
        f"⚡ {len(spikes[spikes['is_spike']])} spike day(s) detected historically — "
        "see the **Activity & Spikes** page for the full breakdown."
    )
    st.dataframe(
        recent_spikes[["date", "activity_type", "count", "z_score"]].rename(
            columns={"count": "actual", "z_score": "z-score"}
        ),
        use_container_width=True,
        hide_index=True,
    )

st.divider()
st.caption(
    "Use the pages in the sidebar to dig into spikes by channel, email engagement, "
    "individual creators, and the exportable outreach list."
)
