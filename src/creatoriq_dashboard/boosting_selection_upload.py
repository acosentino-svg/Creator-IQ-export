"""Monthly boosting selection roster uploads (who was picked; multiple picks per month OK)."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from .config import AppConfig
from .storage import get_engine, read_table, record_sync, write_table

TABLE = "boosting_monthly_selections"

_DEDUPE_COLS = ("creator_id", "selection_month", "selection_date", "content_url")


def _find_column(columns: list[str], aliases: tuple[str, ...]) -> str | None:
    norm = {c.lower().replace(" ", "").replace("_", ""): c for c in columns}
    for alias in aliases:
        key = alias.lower().replace(" ", "").replace("_", "")
        if key in norm:
            return norm[key]
    return None


def parse_selection_csv(source: bytes | str) -> pd.DataFrame:
    """Each row is usually one selection event. Same creator + month may appear many times."""
    raw = pd.read_csv(source if isinstance(source, str) else __import__("io").BytesIO(source))
    if raw.empty:
        return pd.DataFrame(
            columns=["creator_id", "selection_month", "selected", "name", "selection_date", "content_url", "selection_count"]
        )

    cid = _find_column(list(raw.columns), ("creator_id", "publisherid", "publisher id", "id"))
    month = _find_column(list(raw.columns), ("month", "selection_month", "period", "reporting month"))
    sel = _find_column(list(raw.columns), ("selected", "paid team selected", "is selected", "picked"))
    name = _find_column(list(raw.columns), ("publisher name", "name", "creator name"))
    sdate = _find_column(list(raw.columns), ("selection date", "date selected", "selected date", "selection_date"))
    curl = _find_column(list(raw.columns), ("content url", "post url", "url", "content_url"))
    scount = _find_column(list(raw.columns), ("selection count", "times selected", "selection_count", "pick count"))

    if not cid:
        raise ValueError("Selection CSV needs a Publisher / Creator ID column.")

    out = pd.DataFrame()
    out["creator_id"] = raw[cid].astype(str).str.strip()
    out["selection_month"] = raw[month].astype(str).str.strip() if month else ""
    if sel:
        truthy = raw[sel].astype(str).str.lower().isin({"true", "yes", "y", "1", "selected", "picked"})
        out["selected"] = truthy
    else:
        out["selected"] = True
    out["name"] = raw[name].astype(str) if name else ""
    out["selection_date"] = raw[sdate].astype(str).str.strip() if sdate else ""
    out["content_url"] = raw[curl].astype(str).str.strip() if curl else ""
    if scount:
        out["selection_count"] = pd.to_numeric(raw[scount], errors="coerce").fillna(1).astype(int).clip(lower=1)
    else:
        out["selection_count"] = 1

    out = out[out["creator_id"].str.len() > 0]
    for col in _DEDUPE_COLS:
        if col not in out.columns:
            out[col] = ""
    # Keep multiple rows per creator/month (each row = one pick unless Selection Count > 1).
    return out.reset_index(drop=True)


def summarize_selections(df: pd.DataFrame) -> dict[str, int]:
    if df.empty:
        return {
            "selection_rows": 0,
            "total_picks": 0,
            "creators_with_picks": 0,
            "creators_picked_more_than_once": 0,
        }
    work = df[df.get("selected", False) == True].copy()  # noqa: E712
    if work.empty:
        return {
            "selection_rows": len(df),
            "total_picks": 0,
            "creators_with_picks": 0,
            "creators_picked_more_than_once": 0,
        }
    picks = work["selection_count"].fillna(1).astype(int) if "selection_count" in work.columns else pd.Series(1, index=work.index)
    work = work.assign(_picks=picks)
    by_creator = work.groupby("creator_id", as_index=False)["_picks"].sum()
    return {
        "selection_rows": len(df),
        "total_picks": int(work["_picks"].sum()),
        "creators_with_picks": int(len(by_creator)),
        "creators_picked_more_than_once": int((by_creator["_picks"] > 1).sum()),
    }


def merge_selection_frames(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    if existing.empty:
        return new
    if new.empty:
        return existing
    combined = pd.concat([existing, new], ignore_index=True)
    dedupe_cols = [c for c in ("creator_id", "selection_month", "selection_date", "content_url", "selection_count", "selected", "name") if c in combined.columns]
    return combined.drop_duplicates(subset=dedupe_cols, keep="last").reset_index(drop=True)


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
