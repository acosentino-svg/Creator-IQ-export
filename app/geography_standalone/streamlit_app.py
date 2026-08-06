"""Standalone Creator Geography app — US map (home page).

Deploy on Streamlit Cloud with main file: geography_app.py (repo root).
"""
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

from creatoriq_dashboard.geography import (  # noqa: E402
    aggregate_by_country,
    aggregate_by_us_state,
    enrich_creator_locations,
    location_coverage,
)
from geography_standalone.common import get_config, load_creators, render_sidebar_header  # noqa: E402

st.set_page_config(
    page_title="Creator Geography",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)

config = render_sidebar_header()
expected_min = config.settings.get("live_sync", "expected_enrolled_min", default=43000)
try:
    expected_min = int(expected_min)
except (TypeError, ValueError):
    expected_min = 43000
us_only_cfg = bool(config.settings.get("geography", "us_only_program", default=False))

st.title("🌍 Creator Geography")
st.caption("Where your enrolled creators live (CRM State / City / Country). Use **Load Data** to import from the API.")

creators, last_sync = load_creators(config.mode)
coverage = location_coverage(creators, us_only_program=us_only_cfg)
us_only = coverage.get("us_only", False)

if last_sync:
    st.sidebar.caption(f"Creators cache updated: **{last_sync}**")

if coverage["total"] == 0:
    st.info("No creator data yet. Open **Load Data** in the sidebar to upload `warehouse.db` from GitHub Actions.")
    st.stop()

if not config.is_demo and expected_min > 0 and coverage["total"] < expected_min:
    st.warning(
        f"**{coverage['total']:,}** creators in cache (expected **{expected_min:,}+**). "
        "Run the GitHub Actions sync and upload `warehouse.db` on **Load Data**."
    )

if us_only:
    st.info("**US-only program** — map defaults to states.")

if us_only:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Enrolled creators", f"{coverage['total']:,}")
    c2.metric("With state", f"{coverage['with_state_us']:,}")
    c3.metric("Missing state", f"{coverage['missing_state_us']:,}")
    c4.metric("With city", f"{coverage['with_city']:,}")
else:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Enrolled creators", f"{coverage['total']:,}")
    c2.metric("With country", f"{coverage['with_country']:,}")
    c3.metric("Missing country", f"{coverage['missing_country']:,}")
    c4.metric("US creators", f"{coverage['us_creators']:,}")
    c5.metric("US with state", f"{coverage['with_state_us']:,}")

map_options = ["US state", "Country"]
default_level = "US state" if us_only else "Country"
level = st.radio("Map level", map_options, index=0 if default_level == "US state" else 1, horizontal=True)

if level == "Country":
    counts = aggregate_by_country(creators)
    if counts.empty:
        st.info("No country data yet.")
        st.stop()
    fig = px.choropleth(
        counts,
        locations="country",
        locationmode="country names",
        color="creators",
        color_continuous_scale="Blues",
    )
    fig.update_layout(margin=dict(l=0, r=0, t=30, b=0), height=520, geo=dict(showframe=False))
    st.plotly_chart(fig, use_container_width=True)
    display = counts.rename(columns={"country": "Country", "creators": "Creators"})
    display["% of located"] = (display["Creators"] / display["Creators"].sum() * 100).round(1)
    st.dataframe(display, use_container_width=True, hide_index=True)
    st.download_button(
        "Download country counts (CSV)",
        display.to_csv(index=False),
        file_name="creator_geography_by_country.csv",
        mime="text/csv",
    )
else:
    counts = aggregate_by_us_state(creators, us_only_program=us_only_cfg)
    if counts.empty:
        st.info("No state data — check State field in CreatorIQ CRM.")
        st.stop()
    fig = px.choropleth(
        counts,
        locations="state",
        locationmode="USA-states",
        color="creators",
        scope="usa",
        color_continuous_scale="Blues",
    )
    fig.update_layout(margin=dict(l=0, r=0, t=30, b=0), height=520)
    st.plotly_chart(fig, use_container_width=True)
    display = counts.rename(columns={"state": "State", "creators": "Creators"})
    pct_base = coverage["total"] if us_only else coverage["us_creators"]
    display["% of enrolled"] = (display["Creators"] / max(pct_base, 1) * 100).round(1)
    st.dataframe(display, use_container_width=True, hide_index=True)
    st.download_button(
        "Download state counts (CSV)",
        display.to_csv(index=False),
        file_name="creator_geography_by_us_state.csv",
        mime="text/csv",
    )

with st.expander("Sample rows (first 200)"):
    sample = enrich_creator_locations(creators, us_only_program=us_only_cfg)
    cols = [c for c in ("name", "country", "state", "city") if c in sample.columns]
    st.dataframe(sample[cols].head(200), use_container_width=True, hide_index=True)
