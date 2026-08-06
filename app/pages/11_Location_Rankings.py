"""Top states and cities — ranked creator counts from CRM location fields."""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = APP_DIR.parent / "src"
for path in (str(APP_DIR), str(SRC_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from creatoriq_dashboard.geography import (  # noqa: E402
    aggregate_by_city,
    aggregate_by_us_state,
    location_coverage,
)
from common import get_bundle, get_config  # noqa: E402

st.set_page_config(page_title="Location Rankings", page_icon="📍", layout="wide")

config = get_config()
us_only_cfg = bool(config.settings.get("geography", "us_only_program", default=False))

st.title("📍 Top States & Cities")
st.caption(
    "Most popular creator home locations from CreatorIQ CRM (State / City). "
    "See **Creator Geography** for the US map. Data comes from the API sync — not CSV exports."
)

bundle = get_bundle()
creators = bundle["raw"].creators
coverage = location_coverage(creators, us_only_program=us_only_cfg)

if coverage["total"] == 0:
    st.info("No enrolled creators in the cache yet. Run a creators-only API sync (Data & Settings).")
    st.stop()

top_n = st.slider("Show top N", min_value=10, max_value=100, value=25, step=5)

state_counts = aggregate_by_us_state(creators, us_only_program=us_only_cfg)
city_counts = aggregate_by_city(creators, us_only_program=us_only_cfg)

state_top = state_counts.head(top_n).copy()
city_top = city_counts.head(top_n).copy()

left, right = st.columns(2)

with left:
    st.subheader("Top states")
    if state_top.empty:
        st.info("No state data yet.")
    else:
        fig_states = px.bar(
            state_top.sort_values("creators"),
            x="creators",
            y="state",
            orientation="h",
            text="creators",
            color="creators",
            color_continuous_scale="Blues",
        )
        fig_states.update_layout(
            yaxis={"categoryorder": "total ascending"},
            xaxis_title="Creators",
            showlegend=False,
            height=max(400, top_n * 18),
        )
        st.plotly_chart(fig_states, use_container_width=True)

        state_display = state_top.rename(columns={"state": "State", "creators": "Creators"}).copy()
        pct_base = coverage["total"] if coverage.get("us_only") else coverage["us_creators"]
        state_display["% of enrolled"] = (state_display["Creators"] / max(pct_base, 1) * 100).round(1)
        st.dataframe(state_display, use_container_width=True, hide_index=True)
        st.download_button(
            "Download all state counts (CSV)",
            state_counts.rename(columns={"state": "State", "creators": "Creators"}).to_csv(index=False),
            file_name="creator_top_states.csv",
            mime="text/csv",
        )

with right:
    st.subheader("Top cities")
    if city_top.empty:
        st.info("No city data yet — check that City is filled in CreatorIQ CRM.")
    else:
        fig_cities = px.bar(
            city_top.sort_values("creators"),
            x="creators",
            y="location_label",
            orientation="h",
            text="creators",
            color="creators",
            color_continuous_scale="Teal",
        )
        fig_cities.update_layout(
            yaxis={"categoryorder": "total ascending"},
            xaxis_title="Creators",
            showlegend=False,
            height=max(400, top_n * 18),
        )
        st.plotly_chart(fig_cities, use_container_width=True)

        city_display = city_top.rename(
            columns={"location_label": "City", "state": "State", "creators": "Creators"}
        )[["City", "State", "Creators"]]
        city_display["% of enrolled"] = (city_display["Creators"] / max(coverage["total"], 1) * 100).round(1)
        st.dataframe(city_display, use_container_width=True, hide_index=True)
        st.download_button(
            "Download all city counts (CSV)",
            city_counts.rename(
                columns={"location_label": "City", "state": "State", "creators": "Creators"}
            )[["City", "State", "Creators"]].to_csv(index=False),
            file_name="creator_top_cities.csv",
            mime="text/csv",
        )

st.caption(
    f"Based on **{coverage['total']:,}** enrolled creators in cache · "
    f"**{coverage['with_state_us']:,}** with state · **{coverage['with_city']:,}** with city."
)
