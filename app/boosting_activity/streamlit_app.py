"""Boosting program Command Center — same activation dashboard UI, WBP scope.

Run: streamlit run app/boosting_activity/streamlit_app.py
Deploy: creator_boosting_activity_dash.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import boosting_activity._bootstrap  # noqa: F401

APP_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = APP_DIR.parent / "src"
for path in (str(APP_DIR), str(SRC_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import plotly.express as px  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from common import get_bundle, get_config  # noqa: E402

st.set_page_config(page_title="Boosting Command Center", page_icon="🚀", layout="wide")

st.title("🚀 Boosting Command Center")
st.caption(
    "Same layout as the **Activation Command Center**, scoped to **WBP** creators and "
    "**Wayfair Creators Boosting Partnership** post activity. Use the sidebar for date range and thresholds."
)

bundle = get_bundle()
ek = bundle["extended_kpis"]
funnel = bundle["funnel"]
struggle = bundle["struggle_segments"]
controls = bundle["controls"]
data_quality = bundle["data_quality"]
config = get_config()

if bundle["raw"].creators.empty and bundle["raw"].posts.empty:
    st.warning(
        "No boosting cohort in the cache yet. In **live** mode, run a sync from **Data & Settings** "
        "(or ask your team to refresh the shared warehouse). In **demo** mode, sample data includes WBP creators."
    )

if not config.is_demo and data_quality.get("link_creations_unavailable"):
    st.warning(
        "**Link-creation data is not available yet from CreatorIQ.** "
        "Boosting outreach segments that depend on links may show **0** until link creation events are connected."
    )
elif not config.is_demo and data_quality.get("posts_likely_incomplete"):
    st.info(
        f"Post rows are limited to the boosting campaign/WBP scope. "
        f"**{data_quality.get('creators_with_posts', 0):,}** boosting creators have matched post data."
    )

st.subheader("Boosting cohort at a glance")
r1 = st.columns(6)
r1[0].metric(
    "In scope",
    f"{ek.get('total_creators', 0):,}",
    help="WBP-tagged and/or creators with boosting campaign posts",
)
r1[1].metric("Ever activated", f"{ek.get('ever_activated_rate', 0)}%")
r1[2].metric("Fully activated", f"{ek.get('fully_activated_rate', 0)}%")
r1[3].metric("14-day activation", f"{ek.get('activated_within_14d_rate', 0)}%")
r1[4].metric("Ghosts", f"{ek.get('ghost_count', 0):,}")
r1[5].metric(
    "Went dark",
    f"{ek.get('went_dark_creators', 0):,}",
    help=f"No post/link in {controls['went_dark_days']}+ days (boosting-scoped posts in metrics)",
)

r2 = st.columns(4)
r2[0].metric("Linked only (no post)", f"{ek.get('linked_only_count', 0):,}")
r2[1].metric("Posted only (no link)", f"{ek.get('posted_only_count', 0):,}")
r2[2].metric("Median days → first activity", ek.get("median_days_to_first_activity") or "—")
r2[3].metric(
    "Currently active",
    f"{ek.get('active_creators', 0):,}",
    help=f"Posted or linked in the last {controls['active_days']} days",
)

st.divider()

left, right = st.columns([3, 2])

with left:
    st.subheader("Activation funnel")
    if funnel.empty:
        st.info("No creator data yet.")
    else:
        fig = go.Figure(
            go.Funnel(
                y=funnel["step_label"],
                x=funnel["count"],
                textinfo="value+percent initial",
            )
        )
        fig.update_layout(margin=dict(l=20, r=20, t=20, b=20), height=420)
        st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("Where creators are stuck")
    outreach_segments = struggle[struggle["segment_id"] != "healthy"].copy()
    if outreach_segments.empty:
        st.info("No segment data.")
    else:
        fig2 = px.bar(
            outreach_segments,
            x="creator_count",
            y="segment_label",
            orientation="h",
            color="priority",
            color_continuous_scale="Reds_r",
            text="creator_count",
        )
        fig2.update_layout(
            yaxis={"categoryorder": "total ascending"},
            xaxis_title="Creators",
            showlegend=False,
            height=420,
        )
        st.plotly_chart(fig2, use_container_width=True)

st.caption(
    f"Date range: **{controls['range_start'].date()} → {controls['range_end'].date()}** · "
    "For boosting ROAS and content funnel, deploy the separate **Boosting scorecard** (`boosting_app.py`)."
)
