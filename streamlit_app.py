"""Streamlit Cloud entry point (repo root).

Deploy with main file path: streamlit_app.py
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for path in (str(ROOT / "app"), str(ROOT / "src")):
    if path not in sys.path:
        sys.path.insert(0, path)

runpy.run_path(str(ROOT / "app" / "streamlit_app.py"), run_name="__main__")
