"""Standalone geography app — ranked states and cities."""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = REPO_ROOT / "src"
for path in (str(APP_DIR), str(REPO_ROOT / "app"), str(SRC_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from creatoriq_dashboard.bootstrap import ensure_plotly  # noqa: E402

ensure_plotly()

import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from creatoriq_dashboard.geography import aggregate_by_city, aggregate_by_us_state, location_coverage  # noqa: E402
from geography_standalone.common import get_config, load_creators, render_sidebar_header  # noqa: E402

render_sidebar_header()
config = get_config()
us_only_cfg = bool(config.settings.get("geography", "us_only_program", default=False))

st.title("📍 Top States & Cities")
st.caption("Ranked creator counts by home state and city.")

creators, _ = load_creators(config.mode)
coverage = location_coverage(creators, us_only_program=us_only_cfg)

if coverage["total"] == 0:
    st.info("No data yet — use **Load Data** in the sidebar.")
    st.stop()

top_n = st.slider("Show top N", min_value=10, max_value=100, value=25, step=5)
state_counts = aggregate_by_us_state(creators, us_only_program=us_only_cfg)
city_counts = aggregate_by_city(creators, us_only_program=us_only_cfg)
state_top = state_counts.head(top_n)
city_top = city_counts.head(top_n)

left, right = st.columns(2)

with left:
    st.subheader("Top states")
    if state_top.empty:
        st.info("No state data.")
    else:
        fig = px.bar(
            state_top.sort_values("creators"),
            x="creators",
            y="state",
            orientation="h",
            text="creators",
            color="creators",
            color_continuous_scale="Blues",
        )
        fig.update_layout(yaxis={"categoryorder": "total ascending"}, showlegend=False, height=max(400, top_n * 18))
        st.plotly_chart(fig, use_container_width=True)
        tbl = state_top.rename(columns={"state": "State", "creators": "Creators"})
        pct_base = coverage["total"] if coverage.get("us_only") else coverage["us_creators"]
        tbl["% of enrolled"] = (tbl["Creators"] / max(pct_base, 1) * 100).round(1)
        st.dataframe(tbl, use_container_width=True, hide_index=True)
        st.download_button(
            "Download all states (CSV)",
            state_counts.rename(columns={"state": "State", "creators": "Creators"}).to_csv(index=False),
            file_name="creator_top_states.csv",
            mime="text/csv",
        )

with right:
    st.subheader("Top cities")
    if city_top.empty:
        st.info("No city data.")
    else:
        fig = px.bar(
            city_top.sort_values("creators"),
            x="creators",
            y="location_label",
            orientation="h",
            text="creators",
            color="creators",
            color_continuous_scale="Teal",
        )
        fig.update_layout(yaxis={"categoryorder": "total ascending"}, showlegend=False, height=max(400, top_n * 18))
        st.plotly_chart(fig, use_container_width=True)
        tbl = city_top.rename(columns={"location_label": "City", "state": "State", "creators": "Creators"})
        tbl["% of enrolled"] = (tbl["Creators"] / max(coverage["total"], 1) * 100).round(1)
        st.dataframe(tbl[["City", "State", "Creators", "% of enrolled"]], use_container_width=True, hide_index=True)
        st.download_button(
            "Download all cities (CSV)",
            city_counts.rename(columns={"location_label": "City", "state": "State", "creators": "Creators"})[
                ["City", "State", "Creators"]
            ].to_csv(index=False),
            file_name="creator_top_cities.csv",
            mime="text/csv",
        )
