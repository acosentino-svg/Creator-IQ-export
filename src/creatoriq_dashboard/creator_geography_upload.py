"""Parse CreatorIQ Creators / Publishers CSV exports for CRM location fields."""
from __future__ import annotations

import io
import re
from typing import BinaryIO

import pandas as pd

from .active_members import _find_column, _normalize_header

_COUNTRY_ALIASES = (
    "country",
    "countryname",
    "publishercountry",
    "publisher country",
)

_STATE_ALIASES = (
    "state",
    "stateprovince",
    "state province",
    "state/province",
    "publisherstate",
    "publisher state",
)

_CITY_ALIASES = (
    "city",
    "publishercity",
    "publisher city",
)

_NAME_ALIASES = (
    "name",
    "publishername",
    "publisher name",
    "creatorname",
    "creator name",
)

_CREATOR_ID_ALIASES = (
    "creator_id",
    "publisherid",
    "publisher id",
    "publisher_id",
    "id",
    "networkpublisherid",
    "network publisher id",
    "network_publisher_id",
)


def parse_creator_geography_csv(source: str | bytes | BinaryIO | pd.DataFrame) -> pd.DataFrame:
    """Return creator_id, name, country, state, city from a CreatorIQ CSV export."""
    if isinstance(source, pd.DataFrame):
        df = source.copy()
    elif isinstance(source, str):
        df = pd.read_csv(source)
    else:
        df = pd.read_csv(source)

    empty_cols = ["creator_id", "name", "country", "state", "city"]
    if df.empty:
        return pd.DataFrame(columns=empty_cols)

    columns = list(df.columns)
    creator_col = _find_column(columns, _CREATOR_ID_ALIASES)
    country_col = _find_column(columns, _COUNTRY_ALIASES)
    state_col = _find_column(columns, _STATE_ALIASES)
    city_col = _find_column(columns, _CITY_ALIASES)
    name_col = _find_column(columns, _NAME_ALIASES)

    if not state_col and not city_col and not country_col:
        raise ValueError(
            "Could not find location columns. Expected Country, State, or City "
            "(or Publisher Country / State / City)."
        )

    out = pd.DataFrame()
    work = df.copy()
    if creator_col:
        work["creator_id"] = work[creator_col].astype(str).str.strip()
        work = work[work["creator_id"].ne("") & work["creator_id"].ne("nan")]
        out["creator_id"] = work["creator_id"].values
    else:
        work["creator_id"] = [f"row_{i}" for i in range(len(work))]
        out["creator_id"] = work["creator_id"].values

    out["name"] = work[name_col].astype(str) if name_col else ""
    out["country"] = work[country_col].astype(str) if country_col else ""
    out["state"] = work[state_col].astype(str) if state_col else ""
    out["city"] = work[city_col].astype(str) if city_col else ""

    for col in ("name", "country", "state", "city"):
        out[col] = out[col].replace({"nan": "", "None": ""}).fillna("")

    if creator_col:
        out = out.drop_duplicates(subset=["creator_id"], keep="last")
    return out.reset_index(drop=True)


def merge_geography_creator_frames(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Combine partial CreatorIQ exports (upload 20k rows at a time)."""
    empty = pd.DataFrame(columns=["creator_id", "name", "country", "state", "city"])
    base = empty if existing is None or existing.empty else existing.copy()
    if new is None or new.empty:
        return base.reset_index(drop=True)

    combined = pd.concat([base, new], ignore_index=True)
    combined["creator_id"] = combined["creator_id"].astype(str).str.strip()

    def _pick_nonempty(series: pd.Series) -> str:
        for val in series:
            text = str(val).strip()
            if text and text.lower() not in {"nan", "none"}:
                return text
        return ""

    merged = (
        combined.groupby("creator_id", as_index=False)
        .agg(
            name=("name", _pick_nonempty),
            country=("country", _pick_nonempty),
            state=("state", _pick_nonempty),
            city=("city", _pick_nonempty),
        )
        .reset_index(drop=True)
    )
    return merged


def merge_geography_into_creators(creators: pd.DataFrame, geography: pd.DataFrame) -> pd.DataFrame:
    """Overlay uploaded location fields onto the enrolled creators table."""
    if geography.empty:
        return creators.copy()

    geo = geography.copy()
    geo["creator_id"] = geo["creator_id"].astype(str).str.strip()
    geo = geo.drop_duplicates(subset=["creator_id"], keep="last")

    if creators.empty or "creator_id" not in creators.columns:
        out = geo.copy()
        for col in ("creator_id", "name", "handle", "email", "status", "tier", "tags", "joined_date"):
            if col not in out.columns:
                out[col] = pd.NA if col == "joined_date" else ""
        return out.reset_index(drop=True)

    out = creators.copy()
    out["creator_id"] = out["creator_id"].astype(str).str.strip()
    geo = geo.set_index("creator_id")
    for col in ("name", "country", "state", "city"):
        if col not in out.columns:
            out[col] = ""
        mapped = out["creator_id"].map(geo[col] if col in geo.columns else pd.Series(dtype=str))
        filled = mapped.fillna("").astype(str).str.strip()
        keep_old = out[col].fillna("").astype(str).str.strip()
        out[col] = filled.where(filled.ne("") & filled.str.lower().ne("nan"), keep_old)

    missing = geo.index.difference(out["creator_id"])
    if len(missing):
        extra = geo.loc[missing].reset_index()
        for col in out.columns:
            if col not in extra.columns:
                extra[col] = pd.NA if col == "joined_date" else ""
        out = pd.concat([out, extra], ignore_index=True)
    return out.reset_index(drop=True)


def parse_creator_geography_csv_preview(source: str | bytes | BinaryIO) -> dict:
    if isinstance(source, bytes):
        buffer: str | bytes | BinaryIO = io.BytesIO(source)
    else:
        buffer = source
    df = parse_creator_geography_csv(buffer)
    with_state = int((df["state"].astype(str).str.strip() != "").sum()) if not df.empty else 0
    with_city = int((df["city"].astype(str).str.strip() != "").sum()) if not df.empty else 0
    return {
        "rows": len(df),
        "with_state": with_state,
        "with_city": with_city,
        "sample": df.head(5),
    }
