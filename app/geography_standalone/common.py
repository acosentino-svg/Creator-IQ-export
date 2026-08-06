"""Lightweight data loading for the standalone geography app (no activation metrics)."""
from __future__ import annotations

import streamlit as st

from creatoriq_dashboard.config import AppConfig, load_config
from creatoriq_dashboard.data_access import load_inputs


@st.cache_resource
def get_config() -> AppConfig:
    return load_config()


@st.cache_data(ttl=300, show_spinner="Loading creator locations...")
def load_creators(_config_mode: str) -> tuple:
    config = get_config()
    inputs, sync_status = load_inputs(config)
    return inputs.creators, sync_status.get("creators")


def render_sidebar_header() -> AppConfig:
    config = get_config()
    st.sidebar.caption("Creator home locations from CreatorIQ CRM — not audience geography.")
    if config.is_demo:
        st.sidebar.info("**Demo mode** — sample US creator locations.")
    else:
        st.sidebar.success("**Live mode** — reading cached creator locations.")
    return config
