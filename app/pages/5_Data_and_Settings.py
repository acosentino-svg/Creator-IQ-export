"""Data & Settings: current mode, sync freshness, and the business rules
driving segmentation/spikes (read from config/settings.yaml)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_DIR.parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import streamlit as st  # noqa: E402

from common import get_bundle, get_config, render_mode_badge  # noqa: E402

st.set_page_config(page_title="Data & Settings", page_icon="⚙️", layout="wide")
config = get_config()
render_mode_badge()

st.title("⚙️ Data & Settings")

st.subheader("Mode")
st.write(f"**Current mode:** `{config.mode}`")
if config.is_demo:
    st.write(
        "Showing bundled synthetic data. To connect real CreatorIQ data:\n\n"
        "1. Copy `.env.example` to `.env` and fill in `CREATORIQ_BASE_URL`, `CREATORIQ_API_KEY`, "
        "`CREATORIQ_ORG_ID`.\n"
        "2. Confirm/adjust `config/endpoints.yaml` and `config/field_mappings.yaml` against your "
        "account's real CreatorIQ API docs (paths and JSON field names can differ per account).\n"
        "3. Set `CREATORIQ_DASHBOARD_MODE=live` in `.env`.\n"
        "4. Run `python scripts/refresh_data.py` (and put it on a schedule, e.g. cron / GitHub Actions).\n"
        "5. Restart the app."
    )
else:
    st.write(f"**API base URL:** `{config.base_url}`")

st.subheader("Sync freshness")
bundle = get_bundle()
sync_status = bundle["sync_status"]
st.table({"resource": list(sync_status.keys()), "last_synced_at": list(sync_status.values())})

if not config.is_demo:
    st.caption(
        "Data is served from the local SQLite cache. Run the refresh script below (or your "
        "cron job) to pull fresh data from CreatorIQ."
    )
    if st.button("Run refresh now (python scripts/refresh_data.py)"):
        with st.spinner("Refreshing from CreatorIQ..."):
            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "refresh_data.py")],
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
            )
        if result.returncode == 0:
            st.success("Refresh complete. Reload the page to see updated data.")
            st.cache_data.clear()
        else:
            st.error("Refresh failed — see logs below.")
        st.code(result.stdout + "\n" + result.stderr)

st.divider()
st.subheader("Business rules (config/settings.yaml)")
st.json(config.settings.raw)

st.caption(
    "Edit `config/settings.yaml` to change activation windows, score weights, email-cold "
    "thresholds, and spike-detection sensitivity — no code changes required. Restart the app "
    "(or wait for the cache TTL) to see changes take effect."
)
