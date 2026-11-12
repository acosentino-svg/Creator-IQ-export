"""Clear boosting scoped warehouse tables (Streamlit local cache)."""
from __future__ import annotations

from sqlalchemy import text

from .config import AppConfig
from .storage import get_engine

_BOOSTING_TABLES = (
    "boosting_content",
    "boosting_roster",
    "active_member_links",
    "links",
    "boosting_monthly_selections",
)


def clear_boosting_warehouse(config: AppConfig) -> list[str]:
    engine = get_engine(config.db_path)
    cleared: list[str] = []
    with engine.begin() as conn:
        for name in _BOOSTING_TABLES:
            try:
                conn.execute(text(f'DROP TABLE IF EXISTS "{name}"'))
                cleared.append(name)
            except Exception:  # noqa: BLE001
                continue
    return cleared
