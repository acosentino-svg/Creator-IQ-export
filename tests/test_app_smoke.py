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
    assert "Total enrolled" in metric_labels
    assert "Ever activated" in metric_labels
    assert "Ghosts" in metric_labels


def test_overview_page_handles_live_mode_before_any_sync(monkeypatch, tmp_path):
    """Regression test: switching to live mode before scripts/refresh_data.py
    has ever run must not crash -- the SQLite cache doesn't exist yet, so
    every table reads back with zero rows (previously zero *columns* too,
    which broke every merge downstream).

    Note: this only re-checks that the page doesn't raise. It can't reliably
    assert "0 creators" because app/common.py's st.cache_resource/cache_data
    (correctly, for real usage) persist across AppTest instances created
    within the same test process, so an earlier demo-mode test's cached
    config can still be in effect here. See
    tests/test_metrics.py::test_build_creator_summary_with_empty_but_shaped_tables
    for a deterministic, cache-free version of this same regression check.
    """
    monkeypatch.setenv("CREATORIQ_DASHBOARD_MODE", "live")
    monkeypatch.setenv("CREATORIQ_DB_PATH", str(tmp_path / "does_not_exist_yet.db"))
    at = AppTest.from_file(str(APP_DIR / "streamlit_app.py"))
    at.run(timeout=60)
    assert not at.exception
