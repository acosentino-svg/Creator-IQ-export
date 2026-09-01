"""CreatorIQ API data source and optional CSV supplement."""
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

from boosting_standalone.common import (
    get_config,
    get_content,
    render_sidebar,
    run_api_sync,
    set_content,
    show_flash,
)
from creatoriq_dashboard.boosting_scorecard import merge_content_raw, parse_upload_file

st.set_page_config(page_title="Data Source", page_icon="🔌", layout="wide")
config = get_config()
render_sidebar(config)
show_flash()

st.title("🔌 Data Source")
st.markdown(
    """
The scorecard **pulls directly from CreatorIQ** — no monthly CSV upload required.

On each visit (live mode), the app syncs posts from the **Wayfair Boosting Partnership** campaign
and identifies WBP-tagged creators. Eligibility is computed from post captions
(`#WayfairCreator` + `#wayfairelevate`, any capitalization).

Use **Refresh from CreatorIQ** in the sidebar to pull the latest data on demand.
    """
)

st.subheader("1. CreatorIQ API sync")
if config.is_demo:
    st.warning(
        "Demo mode is active. Add these to `.streamlit/secrets.toml` (or Streamlit Cloud secrets) "
        "to enable live API sync:"
    )
    st.code(
        """CREATORIQ_API_KEY = "your-key"
CREATORIQ_BASE_URL = "https://api.creatoriq.com/api"
CREATORIQ_DASHBOARD_MODE = "live"
""",
        language="toml",
    )
else:
    st.success("Live mode — API credentials configured.")
    if st.button("Refresh from CreatorIQ now", type="primary"):
        run_api_sync(config)
        st.rerun()

st.subheader("2. Optional CSV supplement")
st.caption(
    "Only use this if paid-media spend or revenue fields are missing from the CreatorIQ API. "
    "Uploaded rows merge with API data (API wins unless a field is zero/blank)."
)
files = st.file_uploader(
    "CSV or Excel supplement",
    type=["csv", "xlsx", "xls"],
    accept_multiple_files=True,
)

if files:
    preview_batches = []
    for f in files:
        try:
            preview_batches.append(parse_upload_file(f.getvalue(), f.name))
        except ValueError as exc:
            st.error(f"{f.name}: {exc}")
    if preview_batches:
        combined = preview_batches[0]
        for batch in preview_batches[1:]:
            combined = merge_content_raw(combined, batch)
        st.success(f"**{len(combined):,}** supplement rows parsed from {len(files)} file(s).")
        st.dataframe(combined.head(20), use_container_width=True, hide_index=True)

        if st.button("Merge supplement into scorecard"):
            existing = get_content()
            set_content(merge_content_raw(existing, combined), config)
            st.success(f"Scorecard now has **{len(get_content()):,}** total rows.")

st.subheader("3. Current dataset")
current = get_content()
if current.empty:
    st.info("No data loaded yet. Refresh from CreatorIQ in the sidebar.")
else:
    st.write(f"**{len(current):,}** rows · **{int(current['eligible'].sum()):,}** eligible")
    st.download_button(
        "Download content raw (CSV)",
        current.to_csv(index=False).encode("utf-8"),
        file_name="boosting_content_raw.csv",
        mime="text/csv",
    )
