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
from creatoriq_dashboard.active_members import parse_active_members_csv, parse_active_members_csv_preview  # noqa: E402
from creatoriq_dashboard.storage import get_engine, record_sync, write_table  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

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

dq = bundle.get("data_quality", {})
if not config.is_demo:
    st.subheader("Data coverage (live)")
    st.markdown(
        "All pages read from the **same cached dataset** — if a number looks wrong here, "
        "it will be wrong everywhere until the underlying sync improves."
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Enrolled creators", f"{dq.get('enrolled', 0):,}")
    c2.metric("Creators with posts (matched)", f"{dq.get('creators_with_posts', 0):,}")
    c3.metric("Posted, no link creation on file", f"{dq.get('posted_without_link', 0):,}")
    c4.metric("Link rows (API + Active Members)", f"{dq.get('link_creation_rows', 0) + dq.get('active_member_link_rows', 0):,}")
    if dq.get("active_member_link_rows", 0) > 0:
        st.success(
            f"Active Members report loaded for **{dq.get('active_member_link_rows', 0):,}** creators "
            "(last link created dates)."
        )
    if dq.get("link_creations_unavailable"):
        st.warning(
            "**No link-creation dates on file yet.** Export the **Active Members** report from CreatorIQ "
            "(CSV) and upload it below — look for a column like *Last Link Created*. "
            "That powers *Last Link Date*, *Posted only (no link)*, and *Went dark*."
        )
    if dq.get("posts_likely_incomplete"):
        st.info(
            "Post activity is only synced from a **subset of campaigns** (`live_sync.max_campaigns` in settings). "
            "Raise that cap (or set to `null`) to pull posts from more campaigns."
        )

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
st.subheader("Active Members report (link dates)")
st.markdown(
    """
    If your **Active Members** export includes **when each creator last created a link**, upload it here.
    The dashboard will use that for **Last Link Date**, **Posted only (no link)**, and **Went dark**.

    **In CreatorIQ:** run or export **Active Members** → save as **CSV** → upload below.

    We auto-detect columns like `Publisher Id` and `Last Link Created` (names can vary slightly).
    """
)

uploaded = st.file_uploader("Active Members CSV", type=["csv"])
if uploaded is not None:
    try:
        preview = parse_active_members_csv_preview(uploaded.getvalue())
        st.write(
            f"Found **{preview['rows']:,}** creators; "
            f"**{preview['with_last_link']:,}** with a last-link date."
        )
        st.dataframe(preview["sample"], use_container_width=True, hide_index=True)
        if st.button("Import link dates from this file"):
            parsed = parse_active_members_csv(uploaded.getvalue())
            engine = get_engine(config.db_path)
            write_table(engine, "active_member_links", parsed)
            record_sync(engine, "active_member_links", datetime.now(timezone.utc))
            st.cache_data.clear()
            st.success(f"Imported {len(parsed):,} creator link dates. Reload the page to refresh metrics.")
    except ValueError as exc:
        st.error(str(exc))
        st.caption("Send a screenshot of your CSV column headers if auto-detect fails — we'll add your column names.")

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
