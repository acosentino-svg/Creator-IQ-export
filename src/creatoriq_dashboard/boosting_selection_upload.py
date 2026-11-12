"""Monthly boosting selection roster uploads (who was picked last month)."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from .config import AppConfig
from .storage import get_engine, read_table, record_sync, write_table

TABLE = "boosting_monthly_selections"


def _find_column(columns: list[str], aliases: tuple[str, ...]) -> str | None:
    norm = {c.lower().replace(" ", "").replace("_", ""): c for c in columns}
    for alias in aliases:
        key = alias.lower().replace(" ", "").replace("_", "")
        if key in norm:
            return norm[key]
    return None


def parse_selection_csv(source: bytes | str) -> pd.DataFrame:
    raw = pd.read_csv(source if isinstance(source, str) else __import__("io").BytesIO(source))
    if raw.empty:
        return pd.DataFrame(columns=["creator_id", "selection_month", "selected", "name"])

    cid = _find_column(list(raw.columns), ("creator_id", "publisherid", "publisher id", "id"))
    month = _find_column(list(raw.columns), ("month", "selection_month", "period", "reporting month"))
    sel = _find_column(list(raw.columns), ("selected", "paid team selected", "is selected", "picked"))
    name = _find_column(list(raw.columns), ("publisher name", "name", "creator name"))

    if not cid:
        raise ValueError("Selection CSV needs a Publisher / Creator ID column.")

    out = pd.DataFrame()
    out["creator_id"] = raw[cid].astype(str).str.strip()
    if month:
        out["selection_month"] = raw[month].astype(str).str.strip()
    else:
        out["selection_month"] = ""
    if sel:
        truthy = raw[sel].astype(str).str.lower().isin({"true", "yes", "y", "1", "selected", "picked"})
        out["selected"] = truthy
    else:
        out["selected"] = True
    out["name"] = raw[name].astype(str) if name else ""
    out = out[out["creator_id"].str.len() > 0].drop_duplicates(subset=["creator_id", "selection_month"], keep="last")
    return out


def merge_selection_frames(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    if existing.empty:
        return new
    if new.empty:
        return existing
    combined = pd.concat([existing, new], ignore_index=True)
    return combined.drop_duplicates(subset=["creator_id", "selection_month"], keep="last")


def load_boosting_selections(config: AppConfig) -> pd.DataFrame:
    try:
        return read_table(get_engine(config.db_path), TABLE)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


def persist_selection_upload(config: AppConfig, parsed: pd.DataFrame) -> int:
    engine = get_engine(config.db_path)
    existing = read_table(engine, TABLE)
    merged = merge_selection_frames(existing, parsed)
    write_table(engine, TABLE, merged)
    record_sync(engine, TABLE, datetime.now(timezone.utc))
    return len(parsed)
