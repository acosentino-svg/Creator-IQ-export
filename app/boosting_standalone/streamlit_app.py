"""Wayfair Boosting Scorecard — Overview (executive KPIs)."""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parents[1]
SRC_DIR = REPO_ROOT / "src"
for path in (str(APP_DIR), str(REPO_ROOT / "app"), str(SRC_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import streamlit as st  # noqa: E402

from boosting_standalone.common import get_config, render_sidebar, show_flash  # noqa: E402
from creatoriq_dashboard.boosting_comparisons import compare_months, streamlit_metric_args  # noqa: E402
from creatoriq_dashboard.boosting_diagnostics import generate_program_insights  # noqa: E402
from creatoriq_dashboard.boosting_scorecard import (  # noqa: E402
    build_program_monthly,
    program_trend_series,
)

st.set_page_config(page_title="Wayfair Boosting Scorecard", page_icon="🚀", layout="wide")

config = get_config()
content = render_sidebar(config)
show_flash()

st.title("Overview")
st.caption(
    "Wayfair Creators Boosting Partnership · Eligible content requires **#WayfairCreator** and **#wayfairelevate** "
    "(any capitalization, e.g. #wayfaircreator, #WayfairElevate)."
)

if content.empty:
    st.info(
        "No data yet. In **live mode** the app auto-syncs from CreatorIQ on load — "
        "use **Refresh from CreatorIQ** in the sidebar if needed. "
        "In demo mode, load sample data or add API secrets."
    )
    st.stop()

program_long = build_program_monthly(content)
trends = program_trend_series(program_long)

sample_comp = compare_months(program_long, "eligible_content_pieces")
if sample_comp.get("current_month"):
    help_text = streamlit_metric_args(sample_comp, "eligible_content_pieces")[2]
    if help_text:
        st.caption(f"Headline KPIs: **{help_text}**.")

PRIORITY_KPIS = [
    ("active_boosting_creators", "Active Boosting Creators", True),
    ("eligible_content_pieces", "Eligible Content Pieces", True),
    ("selected_content_pieces", "Selected Content Pieces", True),
    ("selection_rate", "Content Selection Rate", True),
    ("retention_rate", "Creator Retention", True),
    ("boosted_revenue", "Boosted Revenue", True),
    ("roas", "ROAS", True),
    ("cost_per_selected_asset", "Gift Card Cost / Selection", False),
]

cols = st.columns(4)
for i, (metric, label, higher_better) in enumerate(PRIORITY_KPIS):
    comp = compare_months(program_long, metric)
    col = cols[i % 4]
    with col:
        value, delta, _help = streamlit_metric_args(comp, metric)
        col.metric(label, value, delta)

st.subheader("Program Health Insights")
for line in generate_program_insights(program_long):
    st.write(f"• {line}")

with st.expander("Metric definitions"):
    st.markdown(
        """
- **Active Boosting Creator** — posted ≥1 eligible piece this month (selected or not)
- **Eligible content** — includes both required hashtags (case-insensitive)
- **Selection rate** — selected eligible pieces ÷ total eligible pieces
- **Retention** — creators active last month AND this month ÷ creators active last month
- **ROAS** — boosted revenue ÷ paid media spend (gift cards excluded; unavailable if no spend data)
        """
    )

if not trends.empty:
    st.subheader("Trends")
    t1, t2 = st.columns(2)
    with t1:
        st.line_chart(trends.set_index("month_label")[["active_boosting_creators"]])
    with t2:
        if "retention_rate" in trends.columns:
            st.line_chart(trends.set_index("month_label")[["retention_rate"]])
