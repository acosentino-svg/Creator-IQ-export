"""Smoke tests that run every Streamlit page end-to-end in demo mode and
assert it renders without raising an exception. Catches import errors,
schema-name typos, or None-handling bugs that unit tests on pure functions
wouldn't.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"

PAGES = [
    APP_DIR / "streamlit_app.py",
    *sorted((APP_DIR / "pages").glob("*.py")),
]


@pytest.fixture(autouse=True)
def _demo_mode(monkeypatch):
    monkeypatch.setenv("CREATORIQ_DASHBOARD_MODE", "demo")


@pytest.mark.parametrize("page_path", PAGES, ids=lambda p: p.name)
def test_page_runs_without_exception(page_path: Path):
    at = AppTest.from_file(str(page_path))
    at.run(timeout=60)
    assert not at.exception, [str(e) for e in at.exception]


def test_overview_page_shows_expected_metrics():
    at = AppTest.from_file(str(APP_DIR / "streamlit_app.py"))
    at.run(timeout=60)
    assert not at.exception
    metric_labels = [m.label for m in at.metric]
    assert "Total Creators" in metric_labels
    assert "Needs Attention" in metric_labels
