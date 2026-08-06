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
from common import get_bundle, get_config  # noqa: E402

st.set_page_config(page_title="Creator Geography", page_icon="🌍", layout="wide")

config = get_config()
expected_min = config.settings.get("live_sync", "expected_enrolled_min", default=43000)
try:
    expected_min = int(expected_min)
except (TypeError, ValueError):
    expected_min = 43000
us_only_cfg = bool(config.settings.get("geography", "us_only_program", default=False))

st.title("🌍 Creator Geography")
st.caption(
    "Where enrolled creators are located based on CreatorIQ CRM fields (Country / State / City). "
    "This is creator home location, not audience geography."
)

bundle = get_bundle()
creators = bundle["raw"].creators
coverage = location_coverage(creators, us_only_program=us_only_cfg)
us_only = coverage.get("us_only", False)

if coverage["total"] == 0:
    st.info("No enrolled creators in the cache yet. Run a data refresh in live mode or use demo mode.")
    st.stop()

if not config.is_demo and expected_min > 0 and coverage["total"] < expected_min:
    st.error(
        f"**Only {coverage['total']:,} enrolled creators in the cache — you expect at least "
        f"**{expected_min:,}**. The geography map is incomplete.\n\n"
        "**Quick sync** pulls only ~500 creators (5 API pages). For the full program, run a "
        "**full sync** on your computer:\n\n"
        "`python3 scripts/refresh_data.py` *(no `--quick` flag)*\n\n"
        "That paginates through all Active `/publishers` until the API has no more rows (~43k+). "
        "It can take **hours** — do not use the Streamlit Cloud Quick sync button for this."
    )

if us_only:
    st.info(
        "**US-only program** — all enrolled creators are mapped by **state** (country is United States). "
        "The country view is available below if you need it."
    )

if coverage["with_country"] == 0 and not us_only:
    st.warning(
        "No creator location fields found in the cache. After confirming Country/State/City in CreatorIQ, "
        "run **Data refresh** on the Data & Settings page (or `python scripts/refresh_data.py`) so "
        "the sync picks up the new field mappings."
    )

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
if "geo_map_level" not in st.session_state:
    st.session_state["geo_map_level"] = default_level
level = st.radio(
    "Map level",
    options=map_options,
    index=map_options.index(st.session_state["geo_map_level"]) if st.session_state["geo_map_level"] in map_options else 0,
    horizontal=True,
    key="geo_map_level",
    help="US state is the primary view for a US-only program.",
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
    st.caption(
        f"Map/table totals sum to **{display['Creators'].sum():,}** creators with a known country "
        f"(of **{coverage['total']:,}** enrolled in cache). "
        f"**{coverage['missing_country']:,}** enrolled creators have no country on file."
    )
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
        st.info(
            "No state data to chart yet. Check that **State** is filled in CreatorIQ CRM for your creators."
        )
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

    st.subheader("Creators by state")
    display = counts.rename(columns={"state": "State", "creators": "Creators"})
    located_total = display["Creators"].sum()
    pct_base = coverage["total"] if us_only else coverage["us_creators"]
    display["% of enrolled"] = (display["Creators"] / max(pct_base, 1) * 100).round(1)
    st.caption(
        f"Map/table totals sum to **{located_total:,}** creators with a known state "
        f"(of **{coverage['total']:,}** enrolled in cache). "
        f"**{coverage['missing_state_us']:,}** creators have no state on file."
    )
    st.dataframe(display, use_container_width=True, hide_index=True)
    st.download_button(
        "Download state counts (CSV)",
        display.to_csv(index=False),
        file_name="creator_geography_by_us_state.csv",
        mime="text/csv",
    )

with st.expander("Creator location sample (first 200 rows)"):
    sample = enrich_creator_locations(creators, us_only_program=us_only_cfg)
    cols = [c for c in ("name", "country", "state", "city", "country_normalized", "state_normalized") if c in sample.columns]
    st.dataframe(sample[cols].head(200), use_container_width=True, hide_index=True)
