"""Creator health — status, retention composition, searchable table."""
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
from creatoriq_dashboard.boosting_scorecard import build_creator_monthly, compute_creator_movement, program_trend_series, build_program_monthly

st.set_page_config(page_title="Creator Health", page_icon="👥", layout="wide")
content = render_sidebar()
show_flash()

st.title("Creator Health")

if content.empty:
    st.info("Upload data via the sidebar or **Data Upload** page.")
    st.stop()

creator_monthly = build_creator_monthly(content)
program_long = build_program_monthly(content)
trends = program_trend_series(program_long)

months = sorted(creator_monthly["month"].unique())
month = st.selectbox("Month", months, index=len(months) - 1)

movement = compute_creator_movement(content, month)
cols = st.columns(5)
for col, (_, row) in zip(cols, movement.iterrows()):
    col.metric(row["segment"], f"{int(row['creators']):,}")

if not trends.empty:
    st.subheader("Active creators by status")
    chart_df = trends[["month_label", "new_creators", "reactivated_creators"]].copy()
    chart_df["retained"] = (
        trends["active_boosting_creators"].fillna(0)
        - trends["new_creators"].fillna(0)
        - trends["reactivated_creators"].fillna(0)
    )
    fig = px.bar(chart_df, x="month_label", y=["retained", "new_creators", "reactivated_creators"], barmode="stack")
    st.plotly_chart(fig, use_container_width=True)

view = creator_monthly[creator_monthly["month"] == month].copy()
st.subheader("Creator table")
st.dataframe(
    view.rename(
        columns={
            "creator_id": "Publisher ID",
            "creator_name": "Creator",
            "creator_handle": "Handle",
            "eligible_pieces": "Eligible Pieces",
            "selected_pieces": "Selected",
            "selection_rate_pct": "Selection Rate %",
            "consecutive_active_months": "Consecutive Active Months",
            "retention_status": "Status",
            "gift_card_cost": "Gift Card",
            "paid_spend": "Spend",
            "boosted_revenue": "Revenue",
            "roas_display": "ROAS",
        }
    ),
    use_container_width=True,
    hide_index=True,
)
st.download_button("Download creator monthly (CSV)", view.to_csv(index=False), file_name="creator_monthly.csv")
