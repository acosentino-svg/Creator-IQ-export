"""Detect where the dashboard is running (local vs Streamlit Cloud)."""
from __future__ import annotations

import os
from pathlib import Path


def is_streamlit_cloud() -> bool:
    """True when running on Streamlit Community Cloud (/mount/src workspace)."""
    if os.environ.get("STREAMLIT_RUNTIME_ENVIRONMENT", "").lower() == "cloud":
        return True
    return Path("/mount/src").exists()
