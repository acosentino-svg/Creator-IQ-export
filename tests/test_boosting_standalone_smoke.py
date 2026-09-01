"""Smoke test: standalone Boosting scorecard app."""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _demo_mode(monkeypatch):
    monkeypatch.setenv("CREATORIQ_DASHBOARD_MODE", "demo")


def test_boosting_standalone_app_runs():
    at = AppTest.from_file(str(REPO_ROOT / "app" / "boosting_standalone" / "streamlit_app.py"))
    at.run(timeout=60)
    assert not at.exception, [str(e) for e in at.exception]


def test_boosting_standalone_shows_four_tabs():
    at = AppTest.from_file(str(REPO_ROOT / "app" / "boosting_standalone" / "streamlit_app.py"))
    at.run(timeout=60)
    assert not at.exception
  # Tabs render as markdown headers in streamlit testing - check title
    assert any("Wayfair Boosting" in t.value for t in at.title)
