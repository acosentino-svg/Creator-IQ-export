"""Load historical CSV backlog exports (links, posts, transactions, names)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import AppConfig


def _hybrid_paths(config: AppConfig) -> dict[str, Path | None]:
    cfg = config.settings.get("boosting", "hybrid", default={}) or {}
    paths = cfg.get("csv_paths") or {}
    root = Path(__file__).resolve().parents[2] / "data" / "backlog"

    def resolve(key: str, default_name: str | None) -> Path | None:
        raw = paths.get(key) or default_name
        if not raw:
            return None
        p = Path(raw)
        if not p.is_absolute():
            p = root / p
        return p if p.is_file() else None

    return {
        "links": resolve("links", "links.csv"),
        "posts": resolve("posts", "posts.csv"),
        "transactions": resolve("transactions", "transactions.csv"),
        "publisher_names": resolve("publisher_names", "publisher_names.csv"),
    }


def _read_csv(path: Path | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False)


def _find_date_col(df: pd.DataFrame) -> str | None:
    for cand in df.columns:
        low = str(cand).lower()
        if any(token in low for token in ("date", "created", "posted", "timestamp")):
            return cand
    return None


def _normalize_creator_col(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    for cand in ("creator_id", "PublisherId", "Publisher Id", "publisher_id", "Publisher ID"):
        if cand in df.columns:
            out = df.copy()
            out["creator_id"] = out[cand].astype(str).str.strip()
            return out
    return df


def filter_by_date_range(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if df.empty:
        return df
    col = _find_date_col(df)
    if not col:
        return df
    dates = pd.to_datetime(df[col], utc=True, errors="coerce")
    return df[(dates >= start) & (dates <= end)]


def load_csv_backlog(config: AppConfig) -> dict[str, pd.DataFrame]:
    paths = _hybrid_paths(config)
    return {key: _normalize_creator_col(_read_csv(path)) for key, path in paths.items()}


def backlog_file_totals(backlog: dict[str, pd.DataFrame]) -> dict[str, int]:
    return {
        "csv_total_links": len(backlog.get("links", pd.DataFrame())),
        "csv_total_transactions": len(backlog.get("transactions", pd.DataFrame())),
        "csv_total_posts": len(backlog.get("posts", pd.DataFrame())),
        "csv_total_publisher_names": len(backlog.get("publisher_names", pd.DataFrame())),
    }
