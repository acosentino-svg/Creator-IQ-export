"""Retention tab — monthly boosting creator retention."""
from __future__ import annotations

import plotly.express as px
import streamlit as st

from creatoriq_dashboard.boosting_comparisons import compare_months
from creatoriq_dashboard.boosting_data_access import load_boosting_content
from creatoriq_dashboard.boosting_scorecard import (
    build_cohort_retention,
    build_program_monthly,
    compute_creator_movement,
    program_trend_series,
)
from common import get_config


def render_retention_tab() -> None:
    config = get_config()
    content, _sync = load_boosting_content(config)
    if content.empty:
        st.info("No boosting scorecard data yet. Use **Refresh from CreatorIQ** in the sidebar.")
        return

    program_long = build_program_monthly(content)
    trends = program_trend_series(program_long)
    months = sorted(content["month"].unique())
    month = st.selectbox("Month", months, index=len(months) - 1, key="retention_month")

    comp = compare_months(program_long, "retention_rate")
    m1, m2, m3 = st.columns(3)
    m1.metric("Retention rate", f"{comp.get('current', 0) * 100:.1f}%" if comp.get("current") is not None else "—")
    movement = compute_creator_movement(content, month)
    for col, segment in zip((m2, m3), ("Retained", "Lapsed")):
        row = movement[movement["segment"] == segment]
        if not row.empty:
            col.metric(segment, f"{int(row.iloc[0]['creators']):,}")

    if not trends.empty and "retention_rate" in trends.columns:
        fig = px.line(trends, x="month_label", y="retention_rate", markers=True, title="Monthly retention")
        st.plotly_chart(fig, use_container_width=True)

    cohorts = build_cohort_retention(content)
    if not cohorts.empty:
        st.subheader("Cohort retention")
        st.dataframe(cohorts, use_container_width=True, hide_index=True)
