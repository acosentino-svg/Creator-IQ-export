"""Email Engagement: who's opening (and who's gone cold)."""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from common import get_bundle, get_config, render_mode_badge  # noqa: E402

st.set_page_config(page_title="Email Engagement", page_icon="📧", layout="wide")
config = get_config()
render_mode_badge()

st.title("📧 Email Engagement")

bundle = get_bundle()
scored = bundle["scored"][["creator_id", "name", "tier", "activation_segment", "activation_score"]]
email_engagement = bundle["email_engagement"]

if email_engagement.empty:
    st.info("No email engagement data available yet.")
    st.stop()

merged = email_engagement.merge(scored, on="creator_id", how="left")

recent_window = config.settings.get("email_engagement", "recent_open_window_days", default=30)
cold_after_days = config.settings.get("email_engagement", "cold_after_days", default=45)

opened_recently_count = int(merged["opened_recently"].sum())
cold_count = int(merged["is_cold"].sum())
avg_open_rate = merged["open_rate"].mean() * 100

col1, col2, col3 = st.columns(3)
col1.metric(f"Opened in last {recent_window}d", f"{opened_recently_count:,} / {len(merged):,}")
col2.metric("Avg. open rate (all-time)", f"{avg_open_rate:.0f}%")
col3.metric(f"Cold (no open {cold_after_days}+ days)", f"{cold_count:,}")

st.divider()
col_left, col_right = st.columns([2, 1])
with col_left:
    st.subheader("Days since last email open")
    fig = px.histogram(
        merged,
        x="days_since_last_open",
        nbins=30,
        color_discrete_sequence=["#9b59b6"],
    )
    fig.add_vline(x=cold_after_days, line_dash="dash", line_color="red", annotation_text="cold threshold")
    fig.update_layout(xaxis_title="Days since last open", yaxis_title="Creators")
    st.plotly_chart(fig, use_container_width=True)

with col_right:
    st.subheader("Open rate by tier")
    if "tier" in merged.columns and merged["tier"].notna().any():
        by_tier = merged.groupby("tier")["open_rate"].mean().reset_index()
        fig2 = px.bar(by_tier, x="tier", y="open_rate", color="tier")
        fig2.update_layout(yaxis_tickformat=".0%", showlegend=False, xaxis_title=None, yaxis_title="Avg open rate")
        st.plotly_chart(fig2, use_container_width=True)

st.divider()
st.subheader("Creators who haven't opened recently")
tier_filter = st.multiselect(
    "Filter by tier", sorted(merged["tier"].dropna().unique()), default=list(sorted(merged["tier"].dropna().unique()))
)
cold_only = st.checkbox("Show only email-cold creators", value=True)

view = merged[merged["tier"].isin(tier_filter)] if tier_filter else merged
if cold_only:
    view = view[view["is_cold"]]
view = view.sort_values("days_since_last_open", ascending=False)

st.dataframe(
    view[
        [
            "name",
            "tier",
            "activation_segment",
            "sends_total",
            "opens_total",
            "open_rate",
            "days_since_last_open",
            "consecutive_unopened_sends",
        ]
    ],
    use_container_width=True,
    hide_index=True,
    column_config={"open_rate": st.column_config.ProgressColumn("open_rate", format="%.0f%%", min_value=0, max_value=1)},
)

st.download_button(
    "⬇️ Download this list as CSV",
    data=view.to_csv(index=False).encode("utf-8"),
    file_name="creatoriq_email_cold_list.csv",
    mime="text/csv",
)

with st.expander("Why this matters"):
    st.markdown(
        """
        Email opens are a **leading indicator**: a creator who stops opening briefs/newsletters
        usually stops posting within the next cycle. Cross-reference this list against the
        **Needs Attention** page — creators who are *both* activation-cold and email-cold are
        your highest-priority re-engagement targets (try SMS, DM, or a 1:1 manager touch instead
        of another email).
        """
    )
