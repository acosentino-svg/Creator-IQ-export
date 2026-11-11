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


def test_boosting_standalone_home_title():
    at = AppTest.from_file(str(REPO_ROOT / "app" / "boosting_standalone" / "streamlit_app.py"))
    at.run(timeout=60)
    assert not at.exception, [str(e) for e in at.exception]
    assert any("Wayfair Boosting" in t.value for t in at.title)


def test_creator_boosting_dash_entrypoint_exists():
    entry = REPO_ROOT / "creator_boosting_dash.py"
    assert entry.is_file()
