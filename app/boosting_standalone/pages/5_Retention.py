"""Retention — monthly trend + cohort table."""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_DIR.parents[1]
SRC_DIR = REPO_ROOT / "src"
for path in (str(APP_DIR), str(REPO_ROOT / "app"), str(SRC_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import pandas as pd
import plotly.express as px
import streamlit as st

from boosting_standalone.common import render_sidebar, show_flash
from creatoriq_dashboard.boosting_comparisons import compare_months
from creatoriq_dashboard.boosting_scorecard import (
    build_cohort_retention,
    build_program_monthly,
    compute_creator_movement,
    program_trend_series,
)

st.set_page_config(page_title="Retention", page_icon="🔁", layout="wide")
content = render_sidebar()
show_flash()

st.title("Retention")

if content.empty:
    st.info("Upload data to see retention.")
    st.stop()

program_long = build_program_monthly(content)
trends = program_trend_series(program_long)
months = sorted(content["month"].unique())
month = st.selectbox("Month", months, index=len(months) - 1)

comp = compare_months(program_long, "retention_rate")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Retention", f"{comp.get('current', 0) * 100:.1f}%" if comp.get("current") is not None else "—")
if comp.get("previous") is not None:
    c2.metric("Previous month", f"{comp['previous'] * 100:.1f}%")
    if comp.get("abs_change") is not None:
        c3.metric("Change", f"{comp['abs_change'] * 100:+.1f} pts")

movement = compute_creator_movement(content, month)
for col, (_, row) in zip([c4, c5], movement[movement["segment"].isin(["Retained", "Lapsed"])].iterrows()):
    col.metric(row["segment"], int(row["creators"]))

if not trends.empty and "retention_rate" in trends.columns:
    fig = px.line(trends, x="month_label", y="retention_rate", markers=True)
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Cohort retention")
cohorts = build_cohort_retention(content)
if cohorts.empty:
    st.info("Need more history for cohorts.")
else:
    display = cohorts.copy()
    for col in [c for c in display.columns if c.startswith("month_")]:
        display[col] = display[col].map(lambda v: f"{v * 100:.0f}%" if v is not None and pd.notna(v) else "")
    st.dataframe(display, use_container_width=True, hide_index=True)
