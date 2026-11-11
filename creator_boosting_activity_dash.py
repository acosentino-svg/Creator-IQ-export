"""Streamlit Cloud entry — Activation-style dashboard for Boosting only.

Same pages as creator-activity-dash (Creator Activity, Went Dark, etc.),
scoped to WBP + boosting campaign. Deploy as a **new** app you own; you do not
need access to the original activation Streamlit deployment.

  Main file path: creator_boosting_activity_dash.py
  Python: 3.12

See docs/DEPLOY_BOOSTING_ACTIVITY_DASH.md
"""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

os.environ["CREATORIQ_BOOSTING_PROGRAM_ONLY"] = "1"

ROOT = Path(__file__).resolve().parent
for path in (str(ROOT / "app"), str(ROOT / "src")):
    if path not in sys.path:
        sys.path.insert(0, path)

runpy.run_path(str(ROOT / "app" / "boosting_activity" / "streamlit_app.py"), run_name="__main__")
