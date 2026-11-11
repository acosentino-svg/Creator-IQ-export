"""Streamlit Cloud entry point for the Boosting Program dashboard (alias).

Prefer `creator_boosting_dash.py` for new Streamlit Cloud apps (naming parity
with creator-activity-dash). This file runs the same app.

  Main file path: boosting_app.py  or  creator_boosting_dash.py
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
