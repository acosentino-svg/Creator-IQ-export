"""Data & Settings: current mode, sync freshness, and a reminder of where
the business-rule config lives (most of it is now live in the sidebar)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = APP_DIR.parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import streamlit as st  # noqa: E402

from common import get_bundle, get_config  # noqa: E402

st.set_page_config(page_title="Data & Settings", page_icon="⚙️", layout="wide")
config = get_config()

st.title("⚙️ Data & Settings")

st.subheader("Mode")
st.write(f"**Current mode:** `{config.mode}`")
if config.is_demo:
    st.write(
        "Showing mock/synthetic data so every page is fully explorable without CreatorIQ credentials. "
        "The dashboard was **structured so mock data can be swapped for the real CreatorIQ API without "
        "changing any page code**:\n\n"
        "- `src/creatoriq_dashboard/demo_data.py` generates the mock `creators` / `posts` / `links` / "
        "`email_events` tables.\n"
        "- `src/creatoriq_dashboard/data_access.load_inputs()` is the single switch point — in `live` mode "
        "it reads the exact same table shapes from a local SQLite cache instead, populated by "
        "`scripts/refresh_data.py` against the real CreatorIQ API "
        "(client + endpoint config already built in `src/creatoriq_dashboard/api_client.py` + "
        "`config/endpoints.yaml`/`config/field_mappings.yaml`).\n"
        "- Every page and every function in `metrics.py` only ever sees those four normalized tables — "
        "swapping the data source underneath doesn't require touching the pages.\n\n"
        "To switch: copy `.env.example` to `.env`, set `CREATORIQ_API_KEY` + "
        "`CREATORIQ_DASHBOARD_MODE=live`, run `python scripts/refresh_data.py`, then restart the app."
    )
else:
    st.write(f"**API base URL:** `{config.base_url}`")

st.subheader("Sync freshness")
bundle = get_bundle()
sync_status = bundle["sync_status"]
st.table({"resource": list(sync_status.keys()), "last_synced_at": list(sync_status.values())})

if not config.is_demo:
    st.caption("Data is served from the local SQLite cache. Run the refresh script below to pull fresh data.")
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
st.subheader("Where the rest of the config lives")
st.markdown(
    """
    - **Date range, "Active" days, "Went Dark" days** — adjustable live in the sidebar on every page
      (defaults come from `config/settings.yaml` → `activation`).
    - **Momentum/spike sensitivity** — `config/settings.yaml` → `momentum`.
    - **Live CreatorIQ sync limits** (once you switch to live mode) — `config/settings.yaml` → `live_sync`.
    """
)
st.json(config.settings.raw)
