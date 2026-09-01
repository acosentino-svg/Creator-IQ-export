"""Data quality — validation warnings and duplicate review."""
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

from boosting_standalone.common import get_content, render_sidebar, show_flash
from creatoriq_dashboard.boosting_data_quality import validate_content_raw

st.set_page_config(page_title="Data Quality", page_icon="✅", layout="wide")
render_sidebar()
show_flash()

st.title("Data Quality")
content = get_content()
report = validate_content_raw(content)

st.metric("Rows", f"{report['row_count']:,}")
st.metric("Eligible rows", f"{report['eligible_count']:,}")

for warning in report["warnings"]:
    st.warning(warning)

if not report["duplicate_urls"].empty:
    st.subheader("Duplicate content URLs (same month)")
    st.dataframe(report["duplicate_urls"], use_container_width=True, hide_index=True)

if not report["duplicate_keys"].empty:
    st.subheader("Possible duplicates (Publisher ID + Post Date + Platform)")
    st.dataframe(report["duplicate_keys"], use_container_width=True, hide_index=True)
