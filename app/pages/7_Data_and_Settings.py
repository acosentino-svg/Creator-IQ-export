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

from common import get_config, get_settings_context  # noqa: E402
from creatoriq_dashboard.active_members import (  # noqa: E402
    merge_active_member_link_frames,
    parse_active_members_csv,
    parse_active_members_csv_preview,
)
from creatoriq_dashboard.runtime import is_streamlit_cloud  # noqa: E402
from creatoriq_dashboard.storage import get_engine, read_table, record_sync, write_table  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

SYNC_TIMEOUT_SECONDS = 900  # 15 minutes — Streamlit Cloud will kill longer runs anyway

st.set_page_config(page_title="Data & Settings", page_icon="⚙️", layout="wide")
config = get_config()
on_cloud = is_streamlit_cloud()

st.title("⚙️ Data & Settings")

if on_cloud:
    st.info(
        "**Streamlit Cloud note:** A full sync of ~43k+ creators can take **many hours** and will "
        "look like this page is stuck. Use **Quick sync** below for a **~500-creator sample** only. "
        "For the full program, run `python3 scripts/refresh_data.py` on a laptop or server. "
        "If the app has been spinning for a long time, open **Manage app → Reboot app** in the "
        "lower-right corner of Streamlit Cloud."
    )

st.subheader("Mode")
st.write(f"**Current mode:** `{config.mode}`")
if config.is_demo:
    st.write(
        "Showing mock/synthetic data so every page is fully explorable without CreatorIQ credentials. "
        "Set `CREATORIQ_DASHBOARD_MODE=live` in Streamlit secrets (or `.env` locally) once your API key is ready."
    )
else:
    st.write(f"**API base URL:** `{config.base_url}`")

st.subheader("Sync freshness")
settings_ctx = get_settings_context()
sync_status = settings_ctx["sync_status"]
st.table({"resource": list(sync_status.keys()), "last_synced_at": list(sync_status.values())})

dq = settings_ctx.get("data_quality", {})
if not config.is_demo:
    st.subheader("Data coverage (live)")
    if dq.get("enrolled", 0) == 0:
        st.warning(
            "**No creator data in the cache yet.** Click **Quick sync** below for a small sample (~500 creators), "
            "or run `python3 scripts/refresh_data.py` locally for the full ~43k+ program."
        )
    expected_min = config.settings.get("live_sync", "expected_enrolled_min", default=43000)
    try:
        expected_min = int(expected_min)
    except (TypeError, ValueError):
        expected_min = 43000
    if expected_min > 0 and dq.get("enrolled", 0) < expected_min:
        st.error(
            f"**Only {dq.get('enrolled', 0):,} enrolled creators in cache** — expected at least "
            f"**{expected_min:,}**. Quick sync is capped; run a full sync locally without `--quick`."
        )
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
    st.caption("Data is served from the local SQLite cache on this server.")
    col_quick, col_full = st.columns(2)
    with col_quick:
        run_quick = st.button(
            "Quick sync (~500 creators)",
            type="primary",
            help="5 publisher pages (~500 enrolled creators) — safe on Streamlit Cloud",
        )
    with col_full:
        run_full = st.button(
            "Full sync (43k+ — hours, local only)",
            help="All Active publishers until API ends. Not recommended in the browser on Streamlit Cloud.",
        )

    if run_quick or run_full:
        cmd = [sys.executable, str(REPO_ROOT / "scripts" / "refresh_data.py")]
        if run_quick:
            cmd.append("--quick")
        elif on_cloud:
            st.warning("Full sync on Streamlit Cloud will likely time out. Run locally: python3 scripts/refresh_data.py")
        label = "Quick sync" if "--quick" in cmd else "Full sync"
        with st.spinner(f"{label} in progress (max {SYNC_TIMEOUT_SECONDS // 60} minutes)..."):
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=str(REPO_ROOT),
                    timeout=SYNC_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired:
                st.error(
                    f"{label} timed out after {SYNC_TIMEOUT_SECONDS // 60} minutes. "
                    "Use Quick sync, or run `python scripts/refresh_data.py` on a machine that can stay on for hours."
                )
            else:
                if result.returncode == 0:
                    st.success(f"{label} complete. Reload the page to see updated data.")
                    st.cache_data.clear()
                else:
                    st.error(f"{label} failed — see logs below.")
                st.code((result.stdout or "") + "\n" + (result.stderr or ""))

st.divider()
st.subheader("Active Members report (link dates)")
st.markdown(
    """
    If your **Active Members** export includes **when each creator last created a link**, upload it here.
    The dashboard will use that for **Last Link Date**, **Posted only (no link)**, and **Went dark**.

    **Can't export all ~43k at once?** Upload partial CSVs (we merge them), **or** click
    **Pull from CreatorIQ API** below — uses the CRM Reports API (same family as Daily Campaign Posts).

    We auto-detect columns like `Publisher Id` and `Last Link Created`.
    """
)

if not config.is_demo:
    if st.button("Pull Active Members link dates from CreatorIQ API"):
        with st.spinner("Requesting Active Members report from CRM API (up to ~2 minutes)..."):
            try:
                from creatoriq_dashboard.crm_reports import sync_active_member_links_from_crm  # noqa: WPS433

                count = sync_active_member_links_from_crm(config)
                st.cache_data.clear()
                st.success(f"Pulled link dates for **{count:,}** creators. Reload the page.")
            except Exception as exc:  # noqa: BLE001
                st.error(f"CRM pull failed: {exc}")
                st.caption(
                    "The exact report name varies by account. Ask CreatorIQ for the "
                    "`view=` path for Active Members, then add it to "
                    "`config/settings.yaml` → `live_sync.active_members_report.view_candidates`."
                )

active_member_link_rows = int(settings_ctx.get("active_member_link_rows", dq.get("active_member_link_rows", 0)))
if active_member_link_rows > 0:
    st.info(f"You already have link dates for **{active_member_link_rows:,}** creators on file. New uploads **add to** this.")

uploaded = st.file_uploader("Active Members CSV (full or partial)", type=["csv"])
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
            merged = merge_active_member_link_frames(read_table(engine, "active_member_links"), parsed)
            write_table(engine, "active_member_links", merged)
            record_sync(engine, "active_member_links", datetime.now(timezone.utc))
            st.cache_data.clear()
            st.success(
                f"Added **{len(parsed):,}** rows from this file. "
                f"**{len(merged):,}** creators total with link dates. Reload to refresh metrics."
            )
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
with st.expander("Raw settings.yaml (advanced)"):
    st.json(config.settings.raw)
