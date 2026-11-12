"""Sidebar: API refresh window, activity dates, sync — boosting activity dash."""
from __future__ import annotations

import os
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from common import get_config, render_mode_badge
from creatoriq_dashboard.boosting_data_access import sync_and_store_boosting_content


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

    # Drive shared activation metrics via custom range
    st.session_state["date_range_preset"] = "Custom"
    st.session_state["custom_range_start"] = activity_start
    st.session_state["custom_range_end"] = activity_end
    os.environ["BOOSTING_ACTIVITY_START"] = pd.Timestamp(activity_start, tz="UTC").isoformat()
    os.environ["BOOSTING_ACTIVITY_END"] = (
        pd.Timestamp(activity_end, tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    ).isoformat()

    return {
        "api_refresh_days": int(api_days),
        "activity_start": pd.Timestamp(activity_start, tz="UTC"),
        "activity_end": pd.Timestamp(activity_end, tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(seconds=1),
    }
