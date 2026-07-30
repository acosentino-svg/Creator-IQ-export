"""Went Dark: creators who previously posted but have gone quiet, with a
recommended follow-up action for each."""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import streamlit as st  # noqa: E402

from common import get_bundle, go_to_creator_profile  # noqa: E402

st.set_page_config(page_title="Went Dark", page_icon="🌙", layout="wide")

st.title("🌙 Went Dark")
st.caption(
    "Creators who **used to post AND link** but have gone quiet — ranked with a recommended follow-up. "
    "This is based on posting/linking activity, **not** email opens."
)

bundle = get_bundle()
went_dark = bundle["went_dark"]
controls = bundle["controls"]

st.metric("Went Dark creators", f"{len(went_dark):,}")
st.caption(
    f"No post or link in **{controls['went_dark_days']}+** days, after previously doing both. "
    "Adjust thresholds in the sidebar — counts update when you change them."
)

if went_dark.empty:
    st.success("Nobody has gone dark right now. 🎉")
    st.stop()

st.divider()

tier_options = sorted(went_dark["tier"].dropna().unique()) if "tier" in went_dark.columns else []
tier_filter = st.multiselect("Filter by tier", tier_options, default=list(tier_options))
view = went_dark[went_dark["tier"].isin(tier_filter)] if tier_filter else went_dark

DISPLAY_COLUMNS = {
    "name": "Name",
    "handle": "Handle",
    "tier": "Tier",
    "last_post": "Last Post Date",
    "days_since_last_post": "Days Since Last Post",
    "last_link": "Last Link Creation",
    "last_email_opened": "Last Email Opened",
    "last_email_clicked": "Last Email Clicked",
    "recommended_action": "Recommended Follow-up",
}
available_cols = [c for c in DISPLAY_COLUMNS if c in view.columns]

st.dataframe(
    view[available_cols].rename(columns=DISPLAY_COLUMNS).sort_values("Days Since Last Post", ascending=False),
    use_container_width=True,
    hide_index=True,
)

st.download_button(
    "⬇️ Export Went Dark list to CSV",
    data=view[available_cols].rename(columns=DISPLAY_COLUMNS).to_csv(index=False).encode("utf-8"),
    file_name="went_dark_creators.csv",
    mime="text/csv",
)

st.divider()
st.subheader("Look up a specific creator")
options = view["creator_id"] + " — " + view["name"].fillna("")
selection = st.selectbox("Creator", options, index=None, placeholder="Search...")
if selection:
    selected_id = selection.split(" — ")[0]
    if st.button("Open full profile →"):
        go_to_creator_profile(selected_id)

with st.expander("How recommended actions are decided"):
    st.markdown(
        """
        Recommendations are based on **how long since their last post or link**, not email engagement.

        - **Was posting and linking** → send trending products or a fresh content brief
        - **Long time since last post** → social proof + a simple one-post prompt
        - **Otherwise** → re-engagement with commission or program updates

        **Went Dark** requires a creator to have both posted and linked in the past, then gone quiet
        for the threshold in the sidebar (default 60 days).
        """
    )
