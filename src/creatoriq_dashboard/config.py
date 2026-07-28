"""Loads environment variables and YAML configuration for the dashboard."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing config file: {path}. The repo ships defaults in config/; "
            "did you move or delete it?"
        )
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@dataclass(frozen=True)
class Settings:
    """Business-rule thresholds loaded from config/settings.yaml."""

    raw: dict[str, Any] = field(default_factory=dict)

    def get(self, *keys: str, default: Any = None) -> Any:
        node: Any = self.raw
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node


@dataclass(frozen=True)
class AppConfig:
    mode: str
    base_url: str
    api_key: str
    org_id: str
    db_path: Path
    slack_webhook_url: str
    settings: Settings
    endpoints: dict[str, Any]
    field_mappings: dict[str, Any]

    @property
    def is_demo(self) -> bool:
        return self.mode.lower() != "live"


@lru_cache(maxsize=1)
def load_config() -> AppConfig:
    """Load .env + YAML config once per process. Cached for cheap re-use.

    On Streamlit Community Cloud, secrets from the app Settings → Secrets
    tab are read via ``st.secrets`` (root-level keys are also env vars, but
    we check both to be safe).
    """
    load_dotenv(REPO_ROOT / ".env", override=False)

    def _env(key: str, default: str = "") -> str:
        val = os.environ.get(key)
        if val:
            return val
        try:
            import streamlit as st  # noqa: WPS433 — optional runtime dependency

            if key in st.secrets:
                return str(st.secrets[key])
        except Exception:
            pass
        return default

    db_path_raw = _env("CREATORIQ_DB_PATH", "data/warehouse.db")
    db_path = Path(db_path_raw)
    if not db_path.is_absolute():
        db_path = REPO_ROOT / db_path

    settings = Settings(raw=_load_yaml(CONFIG_DIR / "settings.yaml"))
    endpoints = _load_yaml(CONFIG_DIR / "endpoints.yaml")
    field_mappings = _load_yaml(CONFIG_DIR / "field_mappings.yaml")

    return AppConfig(
        mode=_env("CREATORIQ_DASHBOARD_MODE", "demo"),
        base_url=_env("CREATORIQ_BASE_URL", "https://api.creatoriq.com/api"),
        api_key=_env("CREATORIQ_API_KEY", ""),
        org_id=_env("CREATORIQ_ORG_ID", ""),
        db_path=db_path,
        slack_webhook_url=_env("SLACK_WEBHOOK_URL", ""),
        settings=settings,
        endpoints=endpoints,
        field_mappings=field_mappings,
    )


def reset_config_cache() -> None:
    """Test helper: clear the cached config so a fresh load() picks up env changes."""
    load_config.cache_clear()
