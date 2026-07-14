"""New Activations: creators who just posted or created a link for the
first time ever, plus onboarding-funnel timing calculations."""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from common import get_bundle  # noqa: E402

st.set_page_config(page_title="New Activations", page_icon="✨", layout="wide")

st.title("✨ New Activations")
st.caption(
    "Creators whose first-ever post or first-ever link falls inside the selected date range, "
    "plus how long it took them to get there."
)

bundle = get_bundle()
controls = bundle["controls"]
new_activations = bundle["new_activations"]

first_time_posters = new_activations["first_time_posters"]
first_time_linkers = new_activations["first_time_linkers"]
linked_no_post = new_activations["linked_no_post"]
with_day_calcs = new_activations["all_with_day_calcs"]

col1, col2, col3 = st.columns(3)
col1.metric("First-time posters", f"{len(first_time_posters):,}")
col2.metric("First-time link creators", f"{len(first_time_linkers):,}")
col3.metric("Created a link, never posted", f"{len(linked_no_post):,}")
st.caption(f"Within: {controls['range_start'].date()} → {controls['range_end'].date()}")

st.divider()

tab1, tab2, tab3 = st.tabs(["🆕 Published first-ever post", "🔗 Created first-ever link", "🔗 Linked but never posted"])

with tab1:
    if first_time_posters.empty:
        st.info("No creators published their first-ever post in this range.")
    else:
        st.dataframe(
            first_time_posters[["name", "handle", "tier", "first_post", "joined_date"]].rename(
                columns={"first_post": "First Post Date", "joined_date": "Joined Program"}
            ),
            use_container_width=True,
            hide_index=True,
        )

with tab2:
    if first_time_linkers.empty:
        st.info("No creators created their first-ever link in this range.")
    else:
        st.dataframe(
            first_time_linkers[["name", "handle", "tier", "first_link", "joined_date"]].rename(
                columns={"first_link": "First Link Date", "joined_date": "Joined Program"}
            ),
            use_container_width=True,
            hide_index=True,
        )

with tab3:
    if linked_no_post.empty:
        st.success("Everyone who's created a link has also posted. 🎉")
    else:
        st.dataframe(
            linked_no_post[["name", "handle", "tier", "first_link", "days_since_last_link"]].rename(
                columns={"first_link": "First Link Date", "days_since_last_link": "Days Since Link"}
            ),
            use_container_width=True,
            hide_index=True,
        )
        st.caption("These creators took the first step (a trackable link) but haven't published content yet — a good nudge target.")

st.divider()
st.subheader("Time-to-Activation")

funnel_df = with_day_calcs.dropna(subset=["days_join_to_first_post"])
col_a, col_b, col_c = st.columns(3)
if not funnel_df.empty:
    col_a.metric("Avg. days: join → first post", f"{funnel_df['days_join_to_first_post'].mean():.1f}")
link_funnel_df = with_day_calcs.dropna(subset=["days_join_to_first_link"])
if not link_funnel_df.empty:
    col_b.metric("Avg. days: join → first link", f"{link_funnel_df['days_join_to_first_link'].mean():.1f}")
order_df = with_day_calcs.dropna(subset=["days_first_link_to_first_post"])
if not order_df.empty:
    col_c.metric(
        "Avg. days: first link → first post",
        f"{order_df['days_first_link_to_first_post'].mean():.1f}",
        help="Positive = creators typically create a link before their first post. "
        "Negative = they typically post before ever creating a link.",
    )

if not funnel_df.empty:
    fig = px.histogram(funnel_df, x="days_join_to_first_post", nbins=20, color_discrete_sequence=["#3498db"])
    fig.update_layout(xaxis_title="Days from joining to first post", yaxis_title="Creators")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Not enough data yet to chart time-to-first-post.")

with st.expander("See full per-creator timing table"):
    st.dataframe(
        with_day_calcs[
            [
                "name",
                "handle",
                "joined_date",
                "first_link",
                "first_post",
                "days_join_to_first_link",
                "days_join_to_first_post",
                "days_first_link_to_first_post",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )
