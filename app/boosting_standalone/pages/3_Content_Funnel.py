"""Content funnel — eligible → selected → boosted."""
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
from creatoriq_dashboard.boosting_funnel import build_funnel_for_month
from creatoriq_dashboard.boosting_scorecard import build_program_monthly, program_trend_series

st.set_page_config(page_title="Content Funnel", page_icon="📊", layout="wide")
content = render_sidebar()
show_flash()

st.title("Content Funnel")
st.caption("Eligible creators → active creators → eligible content → selected → boosted")

if content.empty:
    st.info("Upload data to see the funnel.")
    st.stop()

months = sorted(content["month"].unique())
month = st.selectbox("Month", months, index=len(months) - 1)

funnel = build_funnel_for_month(content, month)
st.dataframe(
    funnel.assign(
        conversion_from_previous=lambda d: d["conversion_from_previous"].map(
            lambda v: f"{v * 100:.1f}%" if v is not None and pd.notna(v) else "—"
        )
    ),
    use_container_width=True,
    hide_index=True,
)

program_long = build_program_monthly(content)
trends = program_trend_series(program_long)
if not trends.empty:
    fig = px.bar(
        trends,
        x="month_label",
        y=["eligible_content_pieces", "selected_content_pieces"],
        barmode="group",
        title="Eligible vs selected content over time",
    )
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Content raw (filtered)")
display = content.rename(
    columns={
        "creator_id": "Publisher ID",
        "creator_name": "Creator",
        "eligible": "Eligible?",
        "selected": "Selected?",
        "boosted": "Boosted?",
    }
)
st.dataframe(display, use_container_width=True, hide_index=True, height=400)
