"""Upload posted + selected CSVs → download Google Sheets ZIP (no local Python)."""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_DIR.parents[1]
SRC_DIR = REPO_ROOT / "src"
for path in (str(APP_DIR), str(REPO_ROOT / "app"), str(SRC_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import streamlit as st

from boosting_standalone.common import get_config, render_sidebar, show_flash
from creatoriq_dashboard.boosting_halo_effect import (
    build_data_quality_checklist,
    build_halo_effect_zip_bytes,
)

st.set_page_config(page_title="Google Sheets Export", page_icon="📊", layout="wide")
config = get_config()
render_sidebar(config)
show_flash()

st.title("Google Sheets export")
st.markdown(
    """
Upload your two halo-effect CSVs here and **download a ZIP** of numbered CSVs (one tab each in Google Sheets).
No terminal or Python on your laptop required.
    """
)

posted = st.file_uploader("Posted CSV (CreatorIQ)", type=["csv"], key="gs_posted")
selected = st.file_uploader("Selected CSV (boosting tracker)", type=["csv"], key="gs_selected")

drought_days = st.slider("Selection drought (days)", 30, 365, 90, 15)
active_days = st.slider("Still posting window (days)", 7, 120, 30, 7)

if posted and selected:
    if st.button("Build export", type="primary"):
        try:
            zip_bytes, diag = build_halo_effect_zip_bytes(
                posted.getvalue(),
                selected.getvalue(),
                drought_days=drought_days,
                active_days=active_days,
                config=config,
            )
            st.session_state["halo_gs_zip"] = zip_bytes
            st.session_state["halo_gs_diag"] = diag
        except ValueError as exc:
            st.error(str(exc))

if st.session_state.get("halo_gs_zip"):
    diag = st.session_state.get("halo_gs_diag", {})
    checklist = build_data_quality_checklist(diag)
    st.subheader("Data quality (also in `01_data_quality.csv` inside the ZIP)")
    st.dataframe(checklist, use_container_width=True, hide_index=True)

    st.download_button(
        label="Download ZIP for Google Sheets",
        data=st.session_state["halo_gs_zip"],
        file_name="halo_effect_google_sheets.zip",
        mime="application/zip",
        type="primary",
    )

    st.caption(
        "In Google Sheets: File → Import → Upload → pick `01_data_quality.csv` from the ZIP "
        "(unzip first on your computer, or upload each file from the extracted folder)."
    )

st.markdown("---")
st.markdown(
    """
**Import tips**
1. Unzip the download on your computer (or use Cloud Convert if your machine blocks ZIPs).
2. [sheets.google.com](https://sheets.google.com) → new spreadsheet → **File → Import → Upload** → `01_data_quality.csv`.
3. Import `02` … `07` with **Insert new sheet(s)**.

**If download still fails in the browser:** right-click the download button → Save link as, or try another browser.
    """
)
