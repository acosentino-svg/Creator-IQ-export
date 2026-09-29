"""Selection impact — posting lift and falloff for selected vs not selected."""
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
from creatoriq_dashboard.boosting_selection_impact import (
    build_creator_posting_velocity,
    build_monthly_selection_retention,
    summarize_selection_impact,
)

st.set_page_config(page_title="Selection Impact", page_icon="🎯", layout="wide")
content = render_sidebar()
show_flash()

st.title("Selection impact")
st.caption(
    "Uses eligible boosting posts from CreatorIQ (or your upload) with the **Selected** flag. "
    "Merge your boosting selection spreadsheet on **Data Source** if API rows are missing selections."
)

if content.empty:
    st.info("Upload or sync data to see selection impact.")
    st.stop()

summary = summarize_selection_impact(content)
month_label = summary.get("latest_month") or "—"

c1, c2, c3, c4 = st.columns(4)
pct_sel = summary.get("pct_active_creators_selected")
c1.metric(
    f"% active creators selected ({month_label})",
    f"{pct_sel * 100:.1f}%" if pct_sel is not None else "—",
    help="Active creators with ≥1 selected eligible piece this month ÷ all active creators this month.",
)
ret_sel = summary.get("retention_rate_had_selection_prior_month")
c2.metric(
    "Retention if selected last month",
    f"{ret_sel * 100:.1f}%" if ret_sel is not None else "—",
    help="Share of creators who had a selection last month and posted again this month.",
)
falloff = summary.get("falloff_rate_no_selection_prior_month")
c3.metric(
    "Falloff if not selected last month",
    f"{falloff * 100:.1f}%" if falloff is not None else "—",
    help="Share of creators active last month with zero selections who did not post this month.",
)
lift = summary.get("avg_eligible_pieces_lift_after_selection")
c4.metric(
    "Avg eligible pieces / month lift after 1st selection",
    f"{lift:+.2f}" if lift is not None else "—",
    help="Among creators with activity before and after their first selection month, "
    "average change in eligible pieces per active month.",
)

st.subheader("Do selections increase posting?")
st.write(
    "Compare **before vs after each creator's first selection month** (only creators with activity in both windows). "
    f"**{summary.get('creators_with_pre_and_post_selection', 0):,}** creators qualify."
)
bullets = []
share_more = summary.get("share_of_selected_creators_posting_more_after")
if share_more is not None:
    bullets.append(
        f"- **{share_more * 100:.0f}%** of paired creators post more eligible pieces/month after first selection."
    )
never_avg = summary.get("avg_eligible_pieces_never_selected")
if never_avg is not None:
    bullets.append(f"- Never-selected creators average **{never_avg:.2f}** eligible pieces/active month.")
post_avg = summary.get("avg_eligible_pieces_after_first_selection")
if post_avg is not None:
    bullets.append(
        f"- After first selection, creators average **{post_avg:.2f}** eligible pieces/active month (post window)."
    )
if bullets:
    st.markdown("\n".join(bullets))

velocity = build_creator_posting_velocity(content)
paired = velocity[velocity["post_minus_pre"].notna()].copy()
if not paired.empty:
    fig = px.histogram(paired, x="post_minus_pre", nbins=20, title="Change in eligible pieces/month (after − before first selection)")
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Retention: selected vs not selected (prior month)")
retention = build_monthly_selection_retention(content)
if retention.empty:
    st.info("Need at least two months of data for month-over-month retention.")
else:
    plot_df = retention.copy()
    plot_df["retention_pct"] = plot_df["retention_rate"] * 100
    plot_df["falloff_pct"] = plot_df["falloff_rate"] * 100
    fig = px.line(
        plot_df,
        x="month",
        y="retention_pct",
        color="segment",
        markers=True,
        title="Retention into next month by prior-month selection status",
    )
    st.plotly_chart(fig, use_container_width=True)

    display = retention.copy()
    for col in ("retention_rate", "falloff_rate"):
        display[col] = display[col].map(lambda v: f"{v * 100:.1f}%" if pd.notna(v) else "—")
    st.dataframe(
        display.rename(
            columns={
                "month": "Month",
                "segment": "Prior month segment",
                "prior_month_creators": "Creators",
                "retained": "Retained",
                "lapsed": "Lapsed",
                "retention_rate": "Retention",
                "falloff_rate": "Falloff",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

st.subheader("Creator-level detail")
st.dataframe(
    velocity.rename(
        columns={
            "creator_id": "Publisher ID",
            "creator_name": "Creator",
            "first_selection_month": "First selection month",
            "pre_active_months": "Months before 1st selection",
            "post_active_months": "Months after 1st selection",
            "pre_avg_eligible_pieces": "Avg eligible/mo before",
            "post_avg_eligible_pieces": "Avg eligible/mo after",
            "post_minus_pre": "After − before",
            "ever_selected": "Ever selected",
        }
    ),
    use_container_width=True,
    hide_index=True,
)
st.download_button(
    "Download posting velocity (CSV)",
    velocity.to_csv(index=False).encode("utf-8"),
    file_name="selection_posting_velocity.csv",
    mime="text/csv",
)
