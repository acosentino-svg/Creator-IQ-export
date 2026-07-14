"""Activity & Spikes: posting/link-click volume over time, split by
channel, with anomaly ("spike") detection."""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from common import get_bundle, get_config, render_mode_badge  # noqa: E402

st.set_page_config(page_title="Activity & Spikes", page_icon="⚡", layout="wide")
config = get_config()
render_mode_badge()

st.title("⚡ Activity & Spikes")
st.caption("Posts and link-clicks are tracked as separate activity types so a spike in one doesn't mask a lull in the other.")

bundle = get_bundle()
timeline = bundle["spikes"]

if timeline.empty:
    st.info("No activity data available yet.")
    st.stop()

activity_types = sorted(timeline["activity_type"].unique())
selected_types = st.multiselect("Activity type", activity_types, default=activity_types)
filtered = timeline[timeline["activity_type"].isin(selected_types)]

col1, col2 = st.columns(2)
with col1:
    fig = px.line(filtered, x="date", y="count", color="activity_type", markers=False, title="Daily volume")
    for activity_type in selected_types:
        spikes_only = filtered[(filtered["activity_type"] == activity_type) & (filtered["is_spike"])]
        if not spikes_only.empty:
            fig.add_scatter(
                x=spikes_only["date"],
                y=spikes_only["count"],
                mode="markers",
                marker=dict(size=12, symbol="star", color="red"),
                name=f"{activity_type} spike",
            )
    st.plotly_chart(fig, use_container_width=True)

with col2:
    fig2 = px.line(filtered, x="date", y="z_score", color="activity_type", title="Rolling z-score vs. baseline")
    spike_cfg = config.settings.get("spike_detection", default={}) or {}
    threshold = spike_cfg.get("z_score_threshold", 2.0)
    fig2.add_hline(y=threshold, line_dash="dash", line_color="red", annotation_text="spike threshold")
    st.plotly_chart(fig2, use_container_width=True)

st.subheader("Flagged spike days")
spike_rows = filtered[filtered["is_spike"]].sort_values("date", ascending=False)
if spike_rows.empty:
    st.success("No spikes flagged in the current view/window. Adjust thresholds in `config/settings.yaml` if this seems off.")
else:
    st.dataframe(
        spike_rows[["date", "activity_type", "count", "rolling_mean", "z_score"]].round(2),
        use_container_width=True,
        hide_index=True,
    )
    st.caption(
        "A day is flagged as a spike when its count is both above the minimum floor "
        "(`spike_detection.min_count_for_spike`) and its z-score vs. the trailing "
        f"{spike_cfg.get('baseline_window_days', 28)}-day baseline exceeds {threshold}."
    )

with st.expander("How to use this page"):
    st.markdown(
        """
        - **Posts** spikes usually mean a campaign brief just went out, a trend/sound is
          driving organic content, or a paid push is live — good time to amplify top posts.
        - **Link Click** spikes without a matching post spike often mean an existing post is
          resurfacing (e.g. algorithmic pickup) or a promo/discount code is circulating — check
          which `link_label` is driving it in the raw data.
        - A **dip** right after a spike is normal; watch for volume that never returns to baseline,
          which is an early signal of program fatigue.
        """
    )
