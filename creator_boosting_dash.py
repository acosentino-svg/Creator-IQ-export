"""Streamlit Cloud entry point — Boosting Program dashboard only.

Deploy as its own app (like creator-activity-dash.streamlit.app for activation):

  Main file path: creator_boosting_dash.py  (or boosting_app.py — same app)
  Python: 3.12

See docs/DEPLOY_BOOSTING_APP.md
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for path in (str(ROOT / "app"), str(ROOT / "src")):
    if path not in sys.path:
        sys.path.insert(0, path)

runpy.run_path(str(ROOT / "app" / "boosting_standalone" / "streamlit_app.py"), run_name="__main__")
