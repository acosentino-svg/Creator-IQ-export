"""Outreach Queue — prioritized creator lists for activation campaigns."""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import streamlit as st  # noqa: E402

from common import get_bundle, go_to_creator_profile  # noqa: E402

st.set_page_config(page_title="Outreach Queue", page_icon="📣", layout="wide")

st.title("📣 Outreach Queue")
st.caption(
    "Prioritized creators who need intervention — sorted by segment urgency. "
    "Export a segment for your next email campaign."
)

bundle = get_bundle()
queue = bundle["outreach_queue"]
struggle = bundle["struggle_segments"]

seg_options = struggle[struggle["segment_id"] != "healthy"]["segment_label"].tolist()
seg_filter = st.multiselect("Filter by segment", seg_options, default=seg_options[:3])

view = queue[queue["segment_label"].isin(seg_filter)] if seg_filter else queue

tier_options = sorted(view["tier"].dropna().unique()) if "tier" in view.columns else []
tier_filter = st.multiselect("Filter by tier", tier_options, default=list(tier_options))
if tier_filter and "tier" in view.columns:
    view = view[view["tier"].isin(tier_filter)]

st.metric("Creators in queue", f"{len(view):,}")

if view.empty:
    st.success("No creators match these filters.")
    st.stop()

st.dataframe(view, use_container_width=True, hide_index=True)

st.download_button(
    "Download full queue CSV",
    view.to_csv(index=False).encode(),
    file_name="outreach_queue.csv",
    mime="text/csv",
)

st.divider()
st.subheader("Segment summary")
st.dataframe(
    struggle[struggle["segment_id"] != "healthy"][
        ["segment_label", "creator_count", "priority", "recommended_intervention", "email_template"]
    ],
    use_container_width=True,
    hide_index=True,
)
