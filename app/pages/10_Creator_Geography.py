"""Creator Geography: where enrolled creators are located (CRM location, not audience)."""
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
    aggregate_by_country,
    aggregate_by_us_state,
    enrich_creator_locations,
    location_coverage,
)
from common import get_bundle  # noqa: E402

st.set_page_config(page_title="Creator Geography", page_icon="🌍", layout="wide")

st.title("🌍 Creator Geography")
st.caption(
    "Where enrolled creators are located based on CreatorIQ CRM fields (Country / State / City). "
    "This is creator home location, not audience geography."
)

bundle = get_bundle()
creators = bundle["raw"].creators
coverage = location_coverage(creators)

if coverage["total"] == 0:
    st.info("No enrolled creators in the cache yet. Run a data refresh in live mode or use demo mode.")
    st.stop()

if coverage["with_country"] == 0:
    st.warning(
        "No creator location fields found in the cache. After confirming Country/State/City in CreatorIQ, "
        "run **Data refresh** on the Data & Settings page (or `python scripts/refresh_data.py`) so "
        "the sync picks up the new field mappings."
    )

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Enrolled creators", f"{coverage['total']:,}")
c2.metric("With country", f"{coverage['with_country']:,}")
c3.metric("Missing country", f"{coverage['missing_country']:,}")
c4.metric("US creators", f"{coverage['us_creators']:,}")
c5.metric("US with state", f"{coverage['with_state_us']:,}")

level = st.radio(
    "Map level",
    options=["Country", "US state"],
    horizontal=True,
    help="US state view only includes creators whose CRM country is United States.",
)

if level == "Country":
    counts = aggregate_by_country(creators)
    if counts.empty:
        st.info("No country data to chart yet.")
        st.stop()

    fig = px.choropleth(
        counts,
        locations="country",
        locationmode="country names",
        color="creators",
        color_continuous_scale="Blues",
        labels={"creators": "Creators"},
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=30, b=0),
        height=520,
        geo=dict(showframe=False, projection_type="natural earth"),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Creators by country")
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
    counts = aggregate_by_us_state(creators)
    if counts.empty:
        st.info("No US state data to chart yet. Check that State is filled for US creators in CreatorIQ.")
        st.stop()

    fig = px.choropleth(
        counts,
        locations="state",
        locationmode="USA-states",
        color="creators",
        scope="usa",
        color_continuous_scale="Blues",
        labels={"creators": "Creators"},
    )
    fig.update_layout(margin=dict(l=0, r=0, t=30, b=0), height=520)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("US creators by state")
    display = counts.rename(columns={"state": "State", "creators": "Creators"})
    display["% of US located"] = (display["Creators"] / display["Creators"].sum() * 100).round(1)
    st.dataframe(display, use_container_width=True, hide_index=True)
    st.download_button(
        "Download state counts (CSV)",
        display.to_csv(index=False),
        file_name="creator_geography_by_us_state.csv",
        mime="text/csv",
    )

with st.expander("Creator location sample (first 200 rows)"):
    sample = enrich_creator_locations(creators)
    cols = [c for c in ("name", "country", "state", "city", "country_normalized", "state_normalized") if c in sample.columns]
    st.dataframe(sample[cols].head(200), use_container_width=True, hide_index=True)
