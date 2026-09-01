"""Upload monthly CreatorIQ / content tracker exports."""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_DIR.parents[1]
SRC_DIR = REPO_ROOT / "src"
for path in (str(APP_DIR), str(REPO_ROOT / "app"), str(SRC_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import pandas as pd
import streamlit as st

from boosting_standalone.common import get_config, get_content, render_sidebar, set_content, show_flash
from creatoriq_dashboard.boosting_scorecard import merge_content_raw, parse_upload_file

st.set_page_config(page_title="Data Upload", page_icon="📤", layout="wide")
config = get_config()
render_sidebar(config)
show_flash()

st.title("📤 Data Upload")
st.markdown(
    """
**This is the main way to use the scorecard.** Each month, export your CreatorIQ / content tracker data
and upload it here. All tabs and KPIs recalculate automatically — no code changes needed.

You do **not** need API sync if your export has the right columns. API sync is optional.
    """
)

st.subheader("1. Upload file(s)")
files = st.file_uploader(
    "CSV or Excel — multiple months/files OK",
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
        st.success(f"**{len(combined):,}** rows parsed from {len(files)} file(s).")
        st.dataframe(combined.head(20), use_container_width=True, hide_index=True)

        if st.button("Import into scorecard", type="primary"):
            existing = get_content()
            set_content(merge_content_raw(existing, combined), config)
            st.success(f"Scorecard now has **{len(get_content()):,}** total rows.")
            st.balloons()

st.subheader("2. Expected columns")
st.markdown(
    """
| Field | Also accepts |
|-------|----------------|
| Publisher ID | Creator ID, PublisherId |
| Creator Name | Publisher Name, Name |
| Creator Handle | Handle, Username |
| Content URL | URL, Link |
| Eligible for Boosting | Eligible? |
| Selected for Boosting | Selected? |
| Paid Media Spend | Spend |
| Boosted Revenue | Revenue |

**Eligibility rule:** if no Eligible column is mapped, the app checks captions for
`#WayfairCreator` AND `#wayfairelevate` (any caps, e.g. `#WAYFAIRCREATOR`, `#WayfairElevate`).
    """
)

st.subheader("3. Current dataset")
current = get_content()
if current.empty:
    st.info("No data loaded yet.")
else:
    st.write(f"**{len(current):,}** rows · **{int(current['eligible'].sum()):,}** eligible")
    st.download_button(
        "Download content raw (CSV)",
        current.to_csv(index=False).encode("utf-8"),
        file_name="boosting_content_raw.csv",
        mime="text/csv",
    )
