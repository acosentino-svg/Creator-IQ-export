"""Activation Analytics — funnel detail, cohorts, time-to-activate, segment drill-down."""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from common import get_bundle  # noqa: E402


def _conv(funnel_df, step_id: str, prev_id: str) -> str:
    if funnel_df.empty:
        return "—"
    curr = funnel_df[funnel_df["step_id"] == step_id]["count"]
    prev = funnel_df[funnel_df["step_id"] == prev_id]["count"]
    if curr.empty or prev.empty or prev.iloc[0] == 0:
        return "—"
    return f"{curr.iloc[0] / prev.iloc[0] * 100:.1f}%"


st.set_page_config(page_title="Activation Analytics", page_icon="🎯", layout="wide")

st.title("🎯 Activation Analytics")
st.caption("Funnel conversion, cohort performance, time-to-activate distributions, and struggle-segment detail.")

bundle = get_bundle()
enriched = bundle["enriched"]
funnel = bundle["funnel"]
cohorts = bundle["cohorts"]
struggle = bundle["struggle_segments"]
ek = bundle["extended_kpis"]

tab_funnel, tab_cohort, tab_timing, tab_segments = st.tabs(
    ["Funnel & conversion", "Cohorts", "Time to activate", "Struggle segments"]
)

with tab_funnel:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Enrolled → ever activated", f"{ek.get('ever_activated_rate', 0)}%")
    c2.metric("Ever activated → fully activated", _conv(funnel, "fully_activated", "ever_activated"))
    c3.metric("14-day activation (eligible)", f"{ek.get('activated_within_14d_rate', 0)}%")
    c4.metric("30-day activation (eligible)", f"{ek.get('activated_within_30d_rate', 0)}%")

    st.dataframe(
        funnel.rename(
            columns={
                "step_label": "Funnel step",
                "count": "Creators",
                "pct_of_enrolled": "% of all enrolled",
                "pct_of_previous": "Step conversion %",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Drop-off between steps")
    if len(funnel) > 1:
        drops = []
        for i in range(1, len(funnel)):
            prev_c = funnel.iloc[i - 1]["count"]
            curr_c = funnel.iloc[i]["count"]
            lost = int(prev_c - curr_c)
            drops.append(
                {
                    "from_step": funnel.iloc[i - 1]["step_label"],
                    "to_step": funnel.iloc[i]["step_label"],
                    "lost_creators": lost,
                    "drop_pct": round(lost / prev_c * 100, 1) if prev_c else 0,
                }
            )
        st.dataframe(drops, use_container_width=True, hide_index=True)

with tab_cohort:
    if cohorts.empty:
        st.info("No cohort data.")
    else:
        st.dataframe(cohorts, use_container_width=True, hide_index=True)
        heatmap_cols = [
            c
            for c in ("ever_activated_pct", "activated_14d_pct", "activated_30d_pct")
            if c in cohorts.columns and cohorts[c].notna().any()
        ]
        if heatmap_cols:
            fig = px.imshow(
                cohorts.set_index("cohort_month")[heatmap_cols].T,
                aspect="auto",
                color_continuous_scale="Greens",
                labels=dict(x="Join month", y="Metric", color="%"),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Not enough cohort history to chart yet.")

with tab_timing:
    col_a, col_b = st.columns(2)
    link_df = enriched.dropna(subset=["days_join_to_first_link"])
    post_df = enriched.dropna(subset=["days_join_to_first_post"])
    act_df = enriched.dropna(subset=["days_join_to_first_activity"])

    with col_a:
        st.subheader("Days: join → first link")
        if not link_df.empty:
            st.metric("Median", f"{link_df['days_join_to_first_link'].median():.0f} days")
            st.metric("75th percentile", f"{link_df['days_join_to_first_link'].quantile(0.75):.0f} days")
            fig = px.histogram(link_df, x="days_join_to_first_link", nbins=30, color_discrete_sequence=["#3498db"])
            st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.subheader("Days: join → first post")
        if not post_df.empty:
            st.metric("Median", f"{post_df['days_join_to_first_post'].median():.0f} days")
            st.metric("75th percentile", f"{post_df['days_join_to_first_post'].quantile(0.75):.0f} days")
            fig = px.histogram(post_df, x="days_join_to_first_post", nbins=30, color_discrete_sequence=["#e67e22"])
            st.plotly_chart(fig, use_container_width=True)

    st.subheader("Days: join → any first activity")
    if not act_df.empty:
        if "tier" in act_df.columns and act_df["tier"].notna().any():
            fig3 = px.box(act_df, y="days_join_to_first_activity", color="tier", points="outliers")
        else:
            fig3 = px.box(act_df, y="days_join_to_first_activity", points="outliers")
        st.plotly_chart(fig3, use_container_width=True)

with tab_segments:
    st.dataframe(
        struggle[
            [
                "segment_label",
                "creator_count",
                "priority",
                "recommended_intervention",
                "email_template",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )
    seg_pick = st.selectbox(
        "Drill into segment",
        struggle[struggle["segment_id"] != "healthy"]["segment_label"].tolist(),
    )
    seg_id = struggle[struggle["segment_label"] == seg_pick]["segment_id"].iloc[0]
    from creatoriq_dashboard.activation_analytics import creators_in_segment

    members = creators_in_segment(enriched, bundle["classified"], seg_id)
    st.metric("Creators in segment", f"{len(members):,}")
    show_cols = [c for c in ["name", "handle", "email", "tier", "days_since_join", "joined_date"] if c in members.columns]
    st.dataframe(members[show_cols].head(100), use_container_width=True, hide_index=True)
    st.download_button(
        "Download segment CSV",
        members.to_csv(index=False).encode(),
        file_name=f"{seg_id}.csv",
        mime="text/csv",
    )
