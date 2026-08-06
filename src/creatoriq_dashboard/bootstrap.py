"""Install critical packages when Streamlit Cloud skips requirements.txt (e.g. failed -e .)."""
from __future__ import annotations

import importlib.util
import subprocess
import sys


def _missing(package: str) -> bool:
    return importlib.util.find_spec(package) is None


def ensure_plotly() -> None:
    if not _missing("plotly"):
        return
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "plotly==5.24.1"],
        timeout=300,
    )
