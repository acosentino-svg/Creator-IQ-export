"""Streamlit Cloud entry point for the standalone Creator Geography app.

Deploy as a SECOND app (separate from the activation dashboard):
  Main file path: app/geography_standalone/streamlit_app.py
  Branch: main
  Python: 3.12

See docs/DEPLOY_GEOGRAPHY_APP.md
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for path in (str(ROOT / "app"), str(ROOT / "src")):
    if path not in sys.path:
        sys.path.insert(0, path)

runpy.run_path(str(ROOT / "app" / "geography_standalone" / "streamlit_app.py"), run_name="__main__")
