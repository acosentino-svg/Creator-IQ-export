"""Sidebar: API refresh window, activity dates, sync — boosting activity dash."""
from __future__ import annotations

import os
from datetime import date, timedelta
import pandas as pd
import streamlit as st

from common import get_config, render_mode_badge
from creatoriq_dashboard.boosting_cache import clear_boosting_warehouse
from creatoriq_dashboard.boosting_data_access import sync_and_store_boosting_content
from creatoriq_dashboard.boosting_selection_upload import (
    load_boosting_selections,
    parse_selection_csv,
    persist_selection_upload,
    summarize_selections,
)

from boosting_activity.backlog_upload import save_backlog_upload


def _clear_streamlit_caches() -> None:
    st.cache_data.clear()
    try:
        get_config.clear()
    except Exception:  # noqa: BLE001
        pass


def render_sidebar_filters() -> dict:
    st.sidebar.divider()
    st.sidebar.subheader("Report filters")
    must_posts = st.sidebar.checkbox("Must have posts", key="report_must_have_posts")
    must_links = st.sidebar.checkbox("Must have links", key="report_must_have_links")
    must_txn = st.sidebar.checkbox("Must have transactions", key="report_must_have_transactions")
    search = st.sidebar.text_input(
        "Search creator",
        key="report_search_creator",
        placeholder="Name, handle, email, ID",
    )
    return {
        "must_have_posts": must_posts,
        "must_have_links": must_links,
        "must_have_transactions": must_txn,
        "search": search.strip().lower(),
    }


def render_boosting_activity_sidebar() -> dict:
    render_mode_badge()
    config = get_config()

    st.sidebar.divider()
    st.sidebar.subheader("Live API refresh")
    if "boosting_api_refresh_days" not in st.session_state:
        st.session_state["boosting_api_refresh_days"] = int(
            config.settings.get("boosting", "api_refresh_lookback_days", default=30)
        )
    api_days = st.sidebar.number_input(
        "Refresh window (days)",
        min_value=1,
        max_value=365,
        step=1,
        key="boosting_api_refresh_days",
        help="Reserved for incremental API refresh (like the main dash’s ~7-day pulls). "
        "History in the table is driven by **Activity window** and cached campaign activity after **Refresh**.",
    )
    os.environ["BOOSTING_API_REFRESH_DAYS"] = str(int(api_days))

    if st.sidebar.button("Refresh from CreatorIQ", type="primary", use_container_width=True, disabled=config.is_demo):
        try:
            with st.spinner("Syncing campaign roster + posts, then link dates (CRM)…"):
                sync_and_store_boosting_content(config)
            st.session_state["boosting_sync_flash"] = ("success", "CreatorIQ sync completed.")
        except Exception as exc:  # noqa: BLE001
            st.session_state["boosting_sync_flash"] = ("error", str(exc))
        _clear_streamlit_caches()
        st.rerun()

    flash = st.session_state.pop("boosting_sync_flash", None)
    if flash:
        kind, text = flash
        if kind == "success":
            st.sidebar.success(text)
        else:
            st.sidebar.error(text)

    st.sidebar.divider()
    st.sidebar.subheader("Activity window")
    today = date.today()
    if "boosting_activity_start" not in st.session_state:
        st.session_state["boosting_activity_start"] = today - timedelta(days=30)
    if "boosting_activity_end" not in st.session_state:
        st.session_state["boosting_activity_end"] = today

    c1, c2 = st.sidebar.columns(2)
    activity_start = c1.date_input("From", key="boosting_activity_start")
    activity_end = c2.date_input("To", key="boosting_activity_end")
    if activity_end < activity_start:
        st.sidebar.warning("End date adjusted to match start.")
        activity_end = activity_start

    st.session_state["date_range_preset"] = "Custom"
    st.session_state["custom_range_start"] = activity_start
    st.session_state["custom_range_end"] = activity_end
    os.environ["BOOSTING_ACTIVITY_START"] = pd.Timestamp(activity_start, tz="UTC").isoformat()
    os.environ["BOOSTING_ACTIVITY_END"] = (
        pd.Timestamp(activity_end, tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    ).isoformat()

    render_sidebar_filters()

    st.sidebar.divider()
    st.sidebar.subheader("Dashboard data")
    if st.sidebar.button("Load dashboard data", use_container_width=True, help="Re-read cache and recompute metrics (no API call)"):
        _clear_streamlit_caches()
        st.session_state["boosting_sync_flash"] = ("success", "Dashboard data reloaded from cache.")
        st.rerun()
    if st.sidebar.button(
        "Clear cached data",
        use_container_width=True,
        disabled=config.is_demo,
        help="Clears boosting tables in SQLite and Streamlit cache. Run Refresh after.",
    ):
        clear_boosting_warehouse(config)
        _clear_streamlit_caches()
        st.session_state["boosting_sync_flash"] = ("success", "Cleared boosting warehouse cache.")
        st.rerun()

    st.sidebar.divider()
    st.sidebar.subheader("CSV uploads")
    with st.sidebar.expander("Backlog (links / posts / transactions)"):
        kind = st.selectbox("File type", ["links", "posts", "transactions", "publisher_names"], key="backlog_upload_kind")
        backlog_file = st.file_uploader("CSV file", type=["csv"], key="backlog_csv_upload")
        if backlog_file and st.button("Save backlog CSV", key="save_backlog"):
            try:
                path = save_backlog_upload(config, kind, backlog_file.getvalue())
                _clear_streamlit_caches()
                st.success(f"Saved to {path.name}")
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))

    with st.sidebar.expander("Monthly selections (prior month picks)"):
        sel_file = st.file_uploader("Selection roster CSV", type=["csv"], key="selection_csv_upload")
        if sel_file and st.button("Import selections", key="import_selections"):
            try:
                parsed = parse_selection_csv(sel_file.getvalue())
                n = persist_selection_upload(config, parsed)
                _clear_streamlit_caches()
                st.success(f"Stored {n:,} selection rows.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    selections = load_boosting_selections(config)
    if not selections.empty:
        stats = summarize_selections(selections)
        st.sidebar.caption(
            f"Selections: **{stats['total_picks']:,}** picks · "
            f"{stats['creators_with_picks']:,} creators · "
            f"{stats['creators_picked_more_than_once']:,} with 2+ picks/month"
        )

    return {
        "api_refresh_days": int(api_days),
        "activity_start": pd.Timestamp(activity_start, tz="UTC"),
        "activity_end": pd.Timestamp(activity_end, tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(seconds=1),
    }
