"""Standalone Boosting Program Scorecard — NOT the activation dashboard.

Deploy on Streamlit Cloud with main file: boosting_app.py (repo root).
"""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parents[1]
SRC_DIR = REPO_ROOT / "src"
for path in (str(APP_DIR), str(REPO_ROOT / "app"), str(SRC_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import streamlit as st  # noqa: E402

from boosting_standalone.common import get_config, render_sidebar_header  # noqa: E402
from boosting_standalone.scorecard_ui import render_boosting_scorecard  # noqa: E402

st.set_page_config(
    page_title="Boosting Program Scorecard",
    page_icon="🚀",
    layout="wide",
)

render_sidebar_header()
render_boosting_scorecard(get_config())
