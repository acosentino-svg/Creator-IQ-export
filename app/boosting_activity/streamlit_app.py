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

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from boosting_activity.active_creator_report import render_active_creator_table  # noqa: E402
from boosting_activity.retention_tab import render_retention_tab  # noqa: E402
from boosting_activity.sidebar import render_boosting_activity_sidebar  # noqa: E402
from common import get_bundle, get_config  # noqa: E402
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
ek = bundle["extended_kpis"]
controls = bundle["controls"]

st.title("🚀 Boosting Active Creator Report")
st.caption(
    "Program: **WBP** tag or CreatorIQ campaign **2206666** · "
    f"Activity window **{controls['range_start'].date()} → {controls['range_end'].date()}**"
)

if summary.empty and classified.empty:
    st.warning(
        "No boosting creators loaded yet. Live mode needs a **boosting-only** sync (campaign **2206666** roster + "
        "activity via API — not the whole-program refresh). Click **Refresh from CreatorIQ** in the sidebar. "
        "Transactions come from `data/creator_sales_ranking.csv`; link dates from **Active Members** CSV on "
        "**Data & Settings** (optional)."
    )
else:
    dq = bundle.get("data_quality", {})
    st.caption(
        f"Loaded **{len(summary):,}** creators · **{int(bundle['raw'].posts.shape[0]):,}** boosting posts · "
        f"**{int(dq.get('active_member_link_rows', 0)):,}** link-date rows · sales file **{int(summary['has_transactions'].sum()) if 'has_transactions' in summary.columns else 0:,}** with transactions"
    )

tab_activation, tab_retention = st.tabs(["Activation", "Retention"])

with tab_activation:
    st.subheader("Active creator report")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("In scope", f"{ek.get('total_creators', 0):,}")
    m2.metric("Active", f"{ek.get('active_creators', 0):,}")
    m3.metric("Ever activated", f"{ek.get('ever_activated_rate', 0)}%")
    m4.metric("Went dark", f"{ek.get('went_dark_creators', 0):,}")
    txn_count = int(summary["has_transactions"].sum()) if "has_transactions" in summary.columns else 0
    m5.metric("With transactions", f"{txn_count:,}")
    render_active_creator_table(summary, classified)

with tab_retention:
    render_retention_tab()
