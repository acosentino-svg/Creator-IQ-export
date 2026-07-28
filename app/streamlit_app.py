"""Creator Activation Dashboard — Command Center (overview).

Run with: streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
SRC_DIR = APP_DIR.parent / "src"
for path in (str(APP_DIR), str(SRC_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import plotly.express as px  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from common import get_bundle, get_config  # noqa: E402

st.set_page_config(page_title="Activation Command Center", page_icon="📊", layout="wide")

st.title("📊 Activation Command Center")
st.caption(
    "Deep activation intelligence for your creator program — funnel, cohorts, struggle segments, "
    "and an AI chat assistant. Use the sidebar to adjust date range and thresholds."
)

bundle = get_bundle()
ek = bundle["extended_kpis"]
funnel = bundle["funnel"]
struggle = bundle["struggle_segments"]
controls = bundle["controls"]
data_quality = bundle["data_quality"]
config = get_config()

if not config.is_demo and data_quality.get("link_creations_unavailable"):
    st.warning(
        "**Link-creation data is not available yet from CreatorIQ.** "
        "Metrics like *Posted only (no link)* and *Linked only (no post)* need trackable link "
        "creation events (from the Link Generator), which are separate from post activity and "
        "link click counts. Until that API is connected, those counts may show **0** even when "
        "you know creators exist in that segment. See **Data & Settings** for coverage details."
    )
elif not config.is_demo and data_quality.get("posts_likely_incomplete"):
    st.info(
        f"Post activity is synced from a **limited set of campaigns** (currently capped in config). "
        f"Only **{data_quality.get('creators_with_posts', 0):,}** of "
        f"**{data_quality.get('enrolled', 0):,}** enrolled creators have matched post data — "
        "activation segments may undercount until more campaigns are synced."
    )

# --- Hero KPIs ---
st.subheader("Activation at a glance")
r1 = st.columns(6)
r1[0].metric(
    "Enrolled (Active)",
    f"{ek.get('total_creators', 0):,}",
    help="Creators with Status=Active in CreatorIQ — your enrolled program population",
)
r1[1].metric(
    "Ever activated",
    f"{ek.get('ever_activated_rate', 0)}%",
    help="Created a link or posted at least once, ever",
)
r1[2].metric(
    "Fully activated",
    f"{ek.get('fully_activated_rate', 0)}%",
    help="Both created a link AND published a post",
)
r1[3].metric(
    "14-day activation",
    f"{ek.get('activated_within_14d_rate', 0)}%",
    help="% of creators (joined 14+ days ago) who activated within 14 days of joining",
)
r1[4].metric("Ghosts", f"{ek.get('ghost_count', 0):,}", help="Joined 14+ days ago, zero activity")
r1[5].metric("Went dark", f"{ek.get('went_dark_creators', 0):,}")

r2 = st.columns(4)
r2[0].metric("Linked only (no post)", f"{ek.get('linked_only_count', 0):,}")
r2[1].metric("Posted only (no link)", f"{ek.get('posted_only_count', 0):,}")
r2[2].metric(
    "Median days → first activity",
    ek.get("median_days_to_first_activity") or "—",
)
r2[3].metric("Currently active", f"{ek.get('active_creators', 0):,}")

st.divider()

# --- Funnel + Struggle segments ---
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

        st.dataframe(
            funnel[["step_label", "count", "pct_of_enrolled", "pct_of_previous"]].rename(
                columns={
                    "step_label": "Step",
                    "count": "Creators",
                    "pct_of_enrolled": "% of enrolled",
                    "pct_of_previous": "% from prev step",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

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

st.divider()

# --- Trends + Cohorts ---
trend_col, cohort_col = st.columns(2)

with trend_col:
    st.subheader("Weekly activation trend")
    trends = bundle["activation_trends"]
    if trends.empty:
        st.info("Not enough history for trends yet.")
    else:
        fig3 = px.bar(trends, x="week", y=["new_enrollments", "first_activations"], barmode="group")
        fig3.update_layout(xaxis_title=None, yaxis_title="Count", legend_title=None)
        st.plotly_chart(fig3, use_container_width=True)

with cohort_col:
    st.subheader("Cohort activation (by join month)")
    cohorts = bundle["cohorts"]
    if cohorts.empty:
        st.info("No cohort data yet.")
    else:
        recent = cohorts.tail(8).copy()
        plot_cols = [
            c
            for c in ("ever_activated_pct", "activated_14d_pct", "activated_30d_pct")
            if c in recent.columns and recent[c].notna().any()
        ]
        if not plot_cols:
            st.info("Not enough cohort history to chart yet.")
        else:
            fig4 = px.line(recent, x="cohort_month", y=plot_cols, markers=True)
            fig4.update_layout(xaxis_title="Join month", yaxis_title="% activated", legend_title=None)
            st.plotly_chart(fig4, use_container_width=True)

st.divider()

st.subheader("💬 Ask the data")
st.markdown(
    "Go to **Chat Assistant** in the sidebar and try: "
    '*Give me 10 creators that activated for the first time this week* or '
    '*How many creators posted but never linked?*'
)

st.caption(
    f"Date range: **{controls['range_start'].date()} → {controls['range_end'].date()}** · "
    "See **Activation Analytics** for full funnel/cohort detail and **Outreach Queue** for prioritized lists."
)
