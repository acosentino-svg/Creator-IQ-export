"""Boosting Active Creator Report (WBP / campaign 2206666).

Mirrors creator-activity-dash #active-creator-report with Activation + Retention tabs.
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

import streamlit as st  # noqa: E402

from boosting_activity.active_creator_report import render_active_creator_table  # noqa: E402
from boosting_activity.retention_tab import render_retention_tab  # noqa: E402
from boosting_activity.diagnostics_panel import render_data_diagnostics  # noqa: E402
from boosting_activity.sidebar import render_boosting_activity_sidebar  # noqa: E402
from boosting_activity.overview import render_report_overview  # noqa: E402
from common import get_bundle, get_config  # noqa: E402
from creatoriq_dashboard.boosting_activity_data import (  # noqa: E402
    get_boosting_hybrid_diagnostics,
    get_boosting_transactions_view,
)
from creatoriq_dashboard.creator_sales import load_creator_sales, merge_sales_into_summary  # noqa: E402

st.set_page_config(
    page_title="Boosting Active Creator Report",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.session_state["boosting_activity_dash_v2"] = True

render_boosting_activity_sidebar()
bundle = get_bundle()
config = get_config()

summary = merge_sales_into_summary(bundle["summary"], load_creator_sales())
classified = bundle["classified"]
controls = bundle["controls"]
raw = bundle["raw"]
diag = get_boosting_hybrid_diagnostics()
transactions = get_boosting_transactions_view()

st.title("Active Creator Report")
st.markdown(
    "For any date range, see which creators **posted content**, **generated affiliate links**, "
    "and **drove sales** — with counts and revenue rolled up per creator."
)
st.caption(
    f"Boosting program · campaign **2206666** · "
    f"Activity window **{controls['range_start'].date()} → {controls['range_end'].date()}**"
)

if summary.empty and classified.empty:
    st.warning(
        "No boosting creators loaded yet. Click **Refresh from CreatorIQ** in the sidebar (live mode). "
        "Upload backlog CSVs under **CSV uploads** for links/transactions history, or use "
        "`data/creator_sales_ranking.csv` for lifetime sales."
    )

tab_activation, tab_retention = st.tabs(["Activation", "Retention"])

with tab_activation:
    if not summary.empty or not classified.empty:
        render_report_overview(summary, raw.posts, raw.links, transactions, diag, config=config)
    st.subheader("Creator detail")
    render_active_creator_table(summary, classified)
    render_data_diagnostics()

with tab_retention:
    render_retention_tab()
