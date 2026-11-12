"""Save backlog CSV uploads to data/backlog/ (links, posts, transactions)."""
from __future__ import annotations

from pathlib import Path

from creatoriq_dashboard.config import AppConfig

BACKLOG_FILES = {
    "links": "links.csv",
    "posts": "posts.csv",
    "transactions": "transactions.csv",
    "publisher_names": "publisher_names.csv",
}


def backlog_dir(config: AppConfig) -> Path:
    root = config.db_path.parent.parent if config.db_path.parent.name == "data" else config.db_path.parent
    repo_data = Path(__file__).resolve().parents[2] / "data" / "backlog"
    return repo_data


def save_backlog_upload(config: AppConfig, kind: str, data: bytes) -> Path:
    if kind not in BACKLOG_FILES:
        raise ValueError(f"Unknown backlog type: {kind}")
    dest = backlog_dir(config) / BACKLOG_FILES[kind]
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return dest
