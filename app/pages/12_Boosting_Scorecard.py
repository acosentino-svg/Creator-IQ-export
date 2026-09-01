"""Boosting scorecard — use the standalone Wayfair Boosting app (boosting_app.py)."""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = APP_DIR.parent / "src"
for path in (str(APP_DIR), str(SRC_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import streamlit as st  # noqa: E402

st.set_page_config(page_title="Boosting Scorecard", page_icon="🚀", layout="wide")
st.title("🚀 Wayfair Boosting Scorecard")
st.info(
    "The full Boosting scorecard lives in the **standalone app** deployed with main file **`boosting_app.py`** "
    "(not this activation dashboard). See **Data Upload** in the sidebar there to upload monthly exports."
)
st.markdown(
    """
### Quick links in the Boosting app
- **Overview** — executive KPIs
- **Data Upload** — monthly CSV/Excel (recommended)
- **Creator Health** · **Content Funnel** · **Performance** · **Retention** · **Data Quality**

Sidebar also has **Quick upload**, **Sync CreatorIQ API**, and **filters**.
    """
)
