"""Data diagnostics panel (CSV backlog + Live API)."""
from __future__ import annotations

import streamlit as st

from creatoriq_dashboard.boosting_activity_data import get_boosting_hybrid_diagnostics


def render_data_diagnostics() -> None:
    diag = get_boosting_hybrid_diagnostics()
    with st.expander("Data diagnostics", expanded=diag is not None):
        if diag is None:
            st.caption("Load data to see CSV + API hybrid diagnostics.")
            return
        st.markdown(diag.render_markdown())
        st.caption(
            "Boosting scope: campaign **2206666** only (not every campaign). "
            "Drop CSV exports in `data/backlog/` — see `data/backlog/README.md`."
        )
