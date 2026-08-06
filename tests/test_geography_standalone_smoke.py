"""Smoke test: standalone geography app modules import."""
from __future__ import annotations


def test_geography_standalone_common_imports():
    from geography_standalone.common import get_config, load_creators  # noqa: WPS433

    config = get_config()
    assert config is not None
