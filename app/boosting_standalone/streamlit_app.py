"""Wayfair Boosting Program — home (executive KPIs). Separate Streamlit app from the activation dashboard."""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parents[1]
SRC_DIR = REPO_ROOT / "src"
for path in (str(APP_DIR), str(REPO_ROOT / "app"), str(SRC_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from boosting_standalone.common import get_config, render_sidebar, show_flash  # noqa: E402
from creatoriq_dashboard.boosting_comparisons import compare_months  # noqa: E402
from creatoriq_dashboard.boosting_diagnostics import generate_program_insights  # noqa: E402
from creatoriq_dashboard.boosting_scorecard import (  # noqa: E402
    build_program_monthly,
    format_program_value,
    program_trend_series,
)

st.set_page_config(page_title="Wayfair Boosting Scorecard", page_icon="🚀", layout="wide")

config = get_config()
content = render_sidebar(config)
show_flash()

st.title("🚀 Wayfair Boosting Program")
st.caption(
    "Boosting-only dashboard (separate from the whole-program **Activation Command Center**). "
    "Data: **Wayfair Creators Boosting Partnership** (campaign 2206666) and WBP-tagged creators. "
    "Eligible content requires **#WayfairCreator** and **#wayfairelevate** (case-insensitive)."
)

if content.empty:
    st.warning(
        "**No data loaded yet.** Open the sidebar and click **Refresh from CreatorIQ**. "
        "The first sync usually takes 1–2 minutes (one campaign — not a full CRM export)."
    )
    st.stop()

program_long = build_program_monthly(content)
trends = program_trend_series(program_long)

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
        current = comp.get("current")
        display = format_program_value(metric, current) if current is not None else "—"
        delta = None
        if comp.get("abs_change") is not None:
            if metric in {"selection_rate", "retention_rate", "activation_rate", "pct_active_creators_selected"}:
                delta = f"{comp['abs_change'] * 100:+.1f} pts"
            elif metric == "roas" and comp.get("previous"):
                delta = f"{(comp['abs_change']):+.2f}x"
            elif comp.get("previous"):
                delta = f"{comp['abs_change']:+,.0f}"
        col.metric(label, display, delta)

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
        fig_active = px.line(
            trends,
            x="month_label",
            y="active_boosting_creators",
            markers=True,
            title="Active Boosting Creators",
        )
        fig_active.update_layout(margin=dict(l=20, r=20, t=40, b=20), height=320, xaxis_title=None)
        st.plotly_chart(fig_active, use_container_width=True)
    with t2:
        if "retention_rate" in trends.columns:
            fig_ret = px.line(
                trends,
                x="month_label",
                y="retention_rate",
                markers=True,
                title="Creator Retention",
            )
            fig_ret.update_layout(margin=dict(l=20, r=20, t=40, b=20), height=320, xaxis_title=None)
            st.plotly_chart(fig_ret, use_container_width=True)
