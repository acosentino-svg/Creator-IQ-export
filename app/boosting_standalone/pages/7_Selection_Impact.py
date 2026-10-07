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
    build_creator_selection_timeline,
    build_monthly_selection_retention,
    build_posting_by_days_since_last_selection,
    summarize_selection_impact,
    summarize_timeline_segments,
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

st.subheader("Long-run view (days, not months)")
st.markdown(
    """
This matches the hypothesis: **creators who stop getting selected eventually stop posting**, while
**creators who were selected recently tend to keep posting**. Use full post history (not one row per month).
    """
)
drought_days = st.slider("No selection for this many days = “selection dried up”", 30, 365, 90, 15)
active_days = st.slider("Count as “still posting” if eligible post within this many days", 7, 120, 30, 7)

timeline = build_creator_selection_timeline(
    content, drought_days=drought_days, active_days=active_days
)
segment_summary = summarize_timeline_segments(timeline)
if not segment_summary.empty:
    display_seg = segment_summary.copy()
    display_seg["pct_still_posting"] = display_seg["pct_still_posting"].map(
        lambda v: f"{v * 100:.0f}%" if pd.notna(v) else "—"
    )
    st.dataframe(
        display_seg.rename(
            columns={
                "segment": "Segment",
                "creators": "Creators",
                "still_posting": f"Posted in last {active_days}d",
                "pct_still_posting": "% still posting",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

buckets = build_posting_by_days_since_last_selection(
    content, active_days=active_days, bin_width_days=30, max_days=360
)
if not buckets.empty:
    plot_buckets = buckets.copy()
    plot_buckets["pct"] = plot_buckets["pct_still_posting"] * 100
    fig = px.bar(
        plot_buckets,
        x="days_since_last_selection_bucket",
        y="pct",
        hover_data=["creators", "still_posting"],
        title=f"% still posting (last {active_days} days) by time since last selection",
        labels={"pct": "% still posting"},
    )
    st.plotly_chart(fig, use_container_width=True)

st.download_button(
    "Download creator timeline (CSV)",
    timeline.to_csv(index=False).encode("utf-8"),
    file_name="creator_selection_timeline.csv",
    mime="text/csv",
)

with st.expander("How to pull this data from CreatorIQ + your spreadsheet"):
    st.markdown(
        """
1. **All eligible posts (time series)** — CreatorIQ *Daily Campaign Posts* (or API sync in this app) for the
   boosting campaign, with **Publisher ID**, **post/publish date**, and caption (for hashtag eligibility).
   Date range: **program start → today** so you capture people who went dark months ago.

2. **Selection history** — Your boosting selection spreadsheet (or CreatorIQ custom field *Selected* /
   *Selection date* on each post). Merge on **Data Source** so every selected row has `selected = yes` and
   ideally **selection date** (not just month).

3. **One row per post** — The scorecard computes each creator’s `last_selection_date`, `last_eligible_post_date`,
   and days since each. Filter **Past selector — went dark** to see creators who used to get picked but haven’t
   posted recently.

4. **Optional QA** — Sort by `days_since_last_selection` vs `days_since_last_post`; when selections stop first
   and posting stops weeks later, that supports your story (correlation, not proof of causation).
        """
    )

st.divider()
st.subheader("Monthly scorecard (secondary)")
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
