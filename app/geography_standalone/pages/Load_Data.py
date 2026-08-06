"""Standalone geography app — import API sync (warehouse.db) or CSV."""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = REPO_ROOT / "src"
for path in (str(APP_DIR), str(REPO_ROOT / "app"), str(SRC_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import streamlit as st  # noqa: E402

from creatoriq_dashboard.creator_geography_upload import (  # noqa: E402
    merge_geography_creator_frames,
    merge_geography_into_creators,
    parse_creator_geography_csv,
)
from creatoriq_dashboard.runtime import is_streamlit_cloud  # noqa: E402
from creatoriq_dashboard.storage import get_engine, read_table, record_sync, write_table  # noqa: E402
from geography_standalone.common import get_config, load_creators, render_sidebar_header  # noqa: E402

render_sidebar_header()
config = get_config()
on_cloud = is_streamlit_cloud()
SYNC_TIMEOUT = 7200

st.title("📥 Load Data")
st.caption("Pull creator locations via the CreatorIQ API (GitHub) or upload files. No Mac Terminal required.")

st.subheader("Option A — GitHub API sync (recommended for 43k+)")
st.markdown(
    """
1. GitHub repo → **Settings** → **Secrets** → **Actions** → add `CREATORIQ_API_KEY` and `CREATORIQ_BASE_URL`
2. **Actions** → **Sync enrolled creators (API geography)** → **Run workflow**
3. When finished, download artifact **warehouse-db** → unzip → get `warehouse.db`
4. Upload below
    """
)

db_upload = st.file_uploader("Upload warehouse.db", type=["db"])
if db_upload is not None:
    size_mb = len(db_upload.getvalue()) / 1_000_000
    st.caption(f"File size: {size_mb:.1f} MB → `{config.db_path}`")
    if st.button("Import warehouse.db", type="primary"):
        config.db_path.parent.mkdir(parents=True, exist_ok=True)
        config.db_path.write_bytes(db_upload.getvalue())
        record_sync(get_engine(config.db_path), "creators", datetime.now(timezone.utc))
        load_creators.clear()
        st.success(f"Imported {size_mb:.1f} MB. Open **Creator Geography** (home) or **Top States & Cities**.")

st.divider()
st.subheader("Option B — Upload CSV (if export is available)")
st.caption("CreatorIQ caps exports at ~20k — upload multiple files to merge.")

geo_files = st.file_uploader("Creators CSV (State / City / Country)", type=["csv"], accept_multiple_files=True)
if geo_files:
    try:
        batches = [parse_creator_geography_csv(f.getvalue()) for f in geo_files]
        combined = batches[0]
        for batch in batches[1:]:
            combined = merge_geography_creator_frames(combined, batch)
        st.write(f"**{len(combined):,}** rows ready to import.")
        st.dataframe(combined.head(5), use_container_width=True, hide_index=True)
        if st.button("Import CSV location data"):
            engine = get_engine(config.db_path)
            merged = merge_geography_into_creators(read_table(engine, "creators"), combined)
            write_table(engine, "creators", merged)
            record_sync(engine, "creators", datetime.now(timezone.utc))
            load_creators.clear()
            st.success(f"**{len(merged):,}** creators in cache.")
    except ValueError as exc:
        st.error(str(exc))

st.divider()
st.subheader("Option C — Sync from this app (advanced)")
if on_cloud:
    st.warning("43k+ API sync may time out on Streamlit Cloud. Prefer GitHub Actions (Option A).")

if st.button("Run creators-only API sync here"):
    cmd = [sys.executable, str(REPO_ROOT / "scripts" / "refresh_data.py"), "--enrolled-only"]
    with st.spinner(f"Sync running (max {SYNC_TIMEOUT // 60} min)..."):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=SYNC_TIMEOUT)
        except subprocess.TimeoutExpired:
            st.error("Timed out. Use GitHub Actions instead.")
        else:
            if result.returncode == 0:
                load_creators.clear()
                st.success("Sync complete. Open the map pages.")
            else:
                st.error("Sync failed.")
            st.code((result.stdout or "") + "\n" + (result.stderr or ""))
