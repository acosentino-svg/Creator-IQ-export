"""Boosting Program Scorecard — also available as standalone app via boosting_app.py."""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = APP_DIR.parent / "src"
for path in (str(APP_DIR), str(SRC_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import streamlit as st  # noqa: E402

from boosting_standalone.scorecard_ui import render_boosting_scorecard  # noqa: E402
from common import get_config  # noqa: E402

st.set_page_config(page_title="Boosting Scorecard", page_icon="🚀", layout="wide")

st.sidebar.info(
    "This page is inside the **activation dashboard**. For a Boosting-only app, "
    "deploy `boosting_app.py` on Streamlit Cloud (see docs/DEPLOY_BOOSTING_APP.md)."
)

render_boosting_scorecard(get_config())
