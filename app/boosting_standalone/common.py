"""Shared session state, sidebar controls, and data loading for the Boosting app."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from creatoriq_dashboard.boosting_data_access import (
    load_boosting_content,
    rebuild_boosting_from_cached_posts,
    save_boosting_content,
    sync_and_store_boosting_content,
)
from creatoriq_dashboard.boosting_demo_data import generate_demo_boosting_content
from creatoriq_dashboard.boosting_scorecard import merge_content_raw, normalize_content_raw
from creatoriq_dashboard.config import AppConfig, load_config

CONTENT_KEY = "boosting_content"
MESSAGE_KEY = "boosting_flash_message"
SYNC_STATUS_KEY = "boosting_sync_status"


@st.cache_resource
def get_config() -> AppConfig:
    return load_config()


def init_content(config: AppConfig | None = None) -> pd.DataFrame:
    config = config or get_config()
    if CONTENT_KEY not in st.session_state:
        content, sync_status = load_boosting_content(config)
        st.session_state[CONTENT_KEY] = content
        st.session_state[SYNC_STATUS_KEY] = sync_status
    return st.session_state[CONTENT_KEY]


def get_content() -> pd.DataFrame:
    return init_content()


def set_content(df: pd.DataFrame, config: AppConfig | None = None) -> None:
    config = config or get_config()
    st.session_state[CONTENT_KEY] = normalize_content_raw(df)
    if not config.is_demo:
        save_boosting_content(config, st.session_state[CONTENT_KEY])


def _flash(kind: str, text: str) -> None:
    st.session_state[MESSAGE_KEY] = (kind, text)


def show_flash() -> None:
    msg = st.session_state.pop(MESSAGE_KEY, None)
    if not msg:
        return
    kind, text = msg
    if kind == "success":
        st.success(text)
    elif kind == "error":
        st.error(text)
    else:
        st.info(text)


def run_api_sync(config: AppConfig) -> None:
    try:
        with st.spinner("Syncing from CreatorIQ API…"):
            df = sync_and_store_boosting_content(config)
        set_content(df, config)
        eligible = int(df["eligible"].sum()) if not df.empty and "eligible" in df.columns else 0
        if df.empty:
            _flash(
                "error",
                "Sync finished but returned **0 rows**. Confirm the **Wayfair Boosting Partnership** "
                "campaign exists in CreatorIQ and your API key has access. "
                "Check `config/settings.yaml` → `boosting.campaign_names`.",
            )
        else:
            _flash(
                "success",
                f"Synced **{len(df):,}** content rows (**{eligible:,}** eligible) from CreatorIQ campaigns. "
                "Open **Overview** or **Content Funnel** to explore.",
            )
    except Exception as exc:  # noqa: BLE001
        _flash("error", f"API sync failed: {exc}")


def run_cache_rebuild(config: AppConfig) -> None:
    try:
        with st.spinner("Rebuilding from cached posts…"):
            df = rebuild_boosting_from_cached_posts(config)
        set_content(df, config)
        eligible = int(df["eligible"].sum()) if not df.empty else 0
        _flash("success", f"Rebuilt **{len(df):,}** rows (**{eligible:,}** eligible) from cache.")
    except Exception as exc:  # noqa: BLE001
        _flash("error", f"Rebuild failed: {exc}")


def apply_filters(content: pd.DataFrame) -> pd.DataFrame:
    df = content.copy()
    if df.empty:
        return df

    months = st.session_state.get("filter_months") or sorted(df["month"].unique())
    if months:
        df = df[df["month"].isin(months)]

    for col, key in (
        ("platform", "filter_platform"),
        ("featured_category", "filter_category"),
        ("campaign", "filter_campaign"),
        ("retention_status", "filter_status"),
    ):
        if key in st.session_state and st.session_state[key] and col in df.columns:
            df = df[df[col].isin(st.session_state[key])]

    creator = st.session_state.get("filter_creator_search", "").strip().lower()
    if creator:
        mask = df["creator_id"].astype(str).str.lower().str.contains(creator, na=False)
        if "creator_name" in df.columns:
            mask = mask | df["creator_name"].astype(str).str.lower().str.contains(creator, na=False)
        df = df[mask]

    return df


def render_sidebar(config: AppConfig | None = None) -> pd.DataFrame:
    config = config or get_config()
    content = init_content(config)
    sync_status = st.session_state.get(SYNC_STATUS_KEY, {})

    st.sidebar.title("🚀 Wayfair Boosting")
    st.sidebar.caption("Pulls from CreatorIQ campaigns · metrics update automatically")

    if config.is_demo:
        st.sidebar.warning(
            "**Demo mode** — showing sample data. Add CreatorIQ secrets to `.streamlit/secrets.toml` "
            "for live API sync."
        )
    else:
        st.sidebar.success("**Live mode** — data syncs from CreatorIQ API")
        last_sync = sync_status.get("boosting_content")
        if last_sync and last_sync != "demo":
            st.sidebar.caption(f"Last synced: {last_sync[:19].replace('T', ' ')} UTC")

    st.sidebar.divider()
    st.sidebar.subheader("Data source")

    st.sidebar.markdown(
        "The scorecard pulls posts from the **Wayfair Boosting Partnership** campaign "
        "(and WBP-tagged creators) via the CreatorIQ API. It auto-syncs on load."
    )

    if st.sidebar.button("Refresh from CreatorIQ", use_container_width=True, disabled=config.is_demo, type="primary"):
        run_api_sync(config)
        st.rerun()

    with st.sidebar.expander("Optional: upload CSV supplement"):
        st.caption("Only needed if paid-media fields are missing from the API.")
        uploaded = st.file_uploader(
            "CSV/Excel supplement",
            type=["csv", "xlsx", "xls"],
            accept_multiple_files=True,
            key="sidebar_upload",
            label_visibility="collapsed",
        )
        if uploaded and st.button("Import supplement", use_container_width=True, key="sidebar_import"):
            from creatoriq_dashboard.boosting_scorecard import parse_upload_file

            try:
                batches = [parse_upload_file(f.getvalue(), f.name) for f in uploaded]
                merged = batches[0]
                for batch in batches[1:]:
                    merged = merge_content_raw(merged, batch)
                set_content(merge_content_raw(content, merged), config)
                _flash("success", f"Merged **{len(merged):,}** supplement rows into scorecard.")
                st.rerun()
            except ValueError as exc:
                _flash("error", str(exc))

    with st.sidebar.expander("Advanced"):
        if st.button("Rebuild from warehouse cache", use_container_width=True, disabled=config.is_demo):
            run_cache_rebuild(config)
            st.rerun()
        if st.button("Load sample data", use_container_width=True):
            set_content(generate_demo_boosting_content(), config)
            _flash("info", "Loaded sample data.")
            st.rerun()

    st.sidebar.divider()
    st.sidebar.subheader("Filters")

    if not content.empty:
        month_options = sorted(content["month"].unique())
        if "filter_months" not in st.session_state:
            st.session_state["filter_months"] = month_options
        st.sidebar.multiselect("Month", month_options, key="filter_months")

        for col, label, key in (
            ("platform", "Platform", "filter_platform"),
            ("featured_category", "Category", "filter_category"),
            ("campaign", "Campaign", "filter_campaign"),
        ):
            if col in content.columns:
                opts = sorted(content[col].dropna().astype(str).unique())
                opts = [o for o in opts if o and o != "nan"]
                if opts:
                    st.sidebar.multiselect(label, opts, key=key)

        st.sidebar.text_input("Creator search", key="filter_creator_search", placeholder="Name or Publisher ID")

    if st.sidebar.button("Reset filters", use_container_width=True):
        for key in list(st.session_state.keys()):
            if key.startswith("filter_"):
                del st.session_state[key]
        st.rerun()

    st.sidebar.divider()
    if not content.empty:
        st.sidebar.metric("Content rows", f"{len(content):,}")
        st.sidebar.metric("Eligible rows", f"{int(content['eligible'].sum()):,}")

    return apply_filters(content)
