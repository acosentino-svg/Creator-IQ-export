"""Streamlit Cloud entry point for the standalone Boosting Program Scorecard.

Deploy as a SEPARATE app from the activation dashboard:
  Main file path: boosting_app.py
  Branch: main
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
