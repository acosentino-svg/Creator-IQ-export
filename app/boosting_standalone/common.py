"""Lightweight config for the standalone Boosting scorecard app."""
from __future__ import annotations

import streamlit as st

from creatoriq_dashboard.config import AppConfig, load_config


@st.cache_resource
def get_config() -> AppConfig:
    return load_config()


def render_sidebar_header() -> None:
    config = get_config()
    st.sidebar.title("🚀 Boosting")
    st.sidebar.caption("Boosting program scorecard only.")
    if config.is_demo:
        st.sidebar.info("**Demo mode** — sample Boosting data.")
    else:
        st.sidebar.success("**Live mode** — CreatorIQ API connected.")
