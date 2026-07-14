"""Momentum: "Spikes This Week" — creators whose posting/link-creation
activity is significantly above their own historical normal."""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from common import get_bundle  # noqa: E402

st.set_page_config(page_title="Momentum", page_icon="🚀", layout="wide")

st.title("🚀 Momentum")
st.caption("Spikes this week — creators posting or creating links well above their own normal pace.")

bundle = get_bundle()
momentum = bundle["momentum"]
spikes = bundle["spikes"]

col1, col2 = st.columns(2)
col1.metric("Creators with a spike this week", f"{len(momentum):,}")
program_spike_days = int(spikes[spikes["is_spike"]].shape[0]) if not spikes.empty else 0
col2.metric("Program-wide spike days (all time)", f"{program_spike_days:,}")

st.divider()
st.subheader("⚡ Spikes This Week")

if momentum.empty:
    st.info(
        "No creators are currently spiking above their historical average by the configured threshold. "
        "Try lowering the sensitivity in `config/settings.yaml` (`momentum.spike_percentage_threshold`) "
        "if this seems too strict."
    )
else:
    display = bundle["classified"][["creator_id", "name", "handle", "tier"]].merge(momentum, on="creator_id", how="right")
    st.dataframe(
        display[
            [
                "name",
                "handle",
                "tier",
                "posts_this_week",
                "links_this_week",
                "activity_score",
                "historical_average",
                "spike_pct",
                "most_recent_activity",
            ]
        ].rename(
            columns={
                "posts_this_week": "Posts",
                "links_this_week": "Links",
                "activity_score": "Activity Score",
                "historical_average": "Historical Avg",
                "spike_pct": "Spike %",
                "most_recent_activity": "Most Recent Activity",
            }
        ),
        use_container_width=True,
        hide_index=True,
        column_config={"Spike %": st.column_config.NumberColumn(format="%.0f%%")},
    )

    st.download_button(
        "⬇️ Export spikes to CSV",
        data=display.to_csv(index=False).encode("utf-8"),
        file_name="momentum_spikes.csv",
        mime="text/csv",
    )

st.divider()
st.subheader("Program-wide activity trend")
timeline = bundle["timeline"]
if not timeline.empty:
    fig = px.line(timeline, x="date", y="count", color="activity_type")
    spikes_only = spikes[spikes["is_spike"]] if not spikes.empty else spikes
    for activity_type in timeline["activity_type"].unique():
        subset = spikes_only[spikes_only["activity_type"] == activity_type] if not spikes_only.empty else spikes_only
        if not subset.empty:
            fig.add_scatter(
                x=subset["date"], y=subset["count"], mode="markers",
                marker=dict(size=12, symbol="star", color="red"), name=f"{activity_type} spike day",
            )
    fig.update_layout(xaxis_title=None, yaxis_title="Daily count", legend_title=None)
    st.plotly_chart(fig, use_container_width=True)

with st.expander("How momentum is calculated"):
    st.markdown(
        """
        For each creator: **activity score** = posts + links created in the last 7 days.
        **Historical average** = their own posts + links over the trailing 28 days before that,
        scaled down to a comparable 7-day rate. **Spike %** = how far above that average they
        currently are. Creators below the minimum activity floor or spike-percentage threshold
        (`config/settings.yaml` → `momentum`) aren't shown — this avoids flagging "1 post vs 0" as
        a huge spike for a creator who barely posts at all.
        """
    )
