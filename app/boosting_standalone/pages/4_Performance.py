"""Performance — spend, revenue, ROAS, rankings."""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_DIR.parents[1]
SRC_DIR = REPO_ROOT / "src"
for path in (str(APP_DIR), str(REPO_ROOT / "app"), str(SRC_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import plotly.express as px
import streamlit as st

from boosting_standalone.common import render_sidebar, show_flash
from creatoriq_dashboard.boosting_scorecard import build_creator_monthly, build_program_monthly, program_trend_series

st.set_page_config(page_title="Performance", page_icon="💰", layout="wide")
content = render_sidebar()
show_flash()

st.title("Performance")

if content.empty:
    st.info("Upload data to see performance metrics.")
    st.stop()

program_long = build_program_monthly(content)
trends = program_trend_series(program_long)
creator_monthly = build_creator_monthly(content)

months = sorted(creator_monthly["month"].unique())
month = st.selectbox("Month", months, index=len(months) - 1)
month_creators = creator_monthly[creator_monthly["month"] == month]

if not trends.empty:
    fig = px.line(
        trends,
        x="month_label",
        y=["paid_media_spend", "boosted_revenue"],
        markers=True,
        title="Spend vs revenue",
    )
    st.plotly_chart(fig, use_container_width=True)

rank_tab1, rank_tab2, rank_tab3 = st.tabs(["By revenue", "By ROAS", "By selections"])
with rank_tab1:
    top = month_creators.sort_values("boosted_revenue", ascending=False).head(25)
    st.dataframe(top[["creator_name", "creator_id", "boosted_revenue", "paid_spend", "roas_display"]], hide_index=True)
with rank_tab2:
    roas_rank = month_creators[month_creators["paid_spend"] > 0].sort_values("roas", ascending=False).head(25)
    st.dataframe(roas_rank[["creator_name", "creator_id", "roas_display", "eligible_pieces", "paid_spend"]], hide_index=True)
with rank_tab3:
    sel = month_creators.sort_values("selected_pieces", ascending=False).head(25)
    st.dataframe(sel[["creator_name", "creator_id", "selected_pieces", "eligible_pieces", "selection_rate_pct"]], hide_index=True)
