"""Parse CreatorIQ Active Members (or similar) CSV exports for link-creation dates.

Wayfair's Active Members report typically includes when a creator last created
a trackable link — the signal we need for activation metrics that the campaign
activity API does not expose.
"""
from __future__ import annotations

import io
import re
from typing import BinaryIO

import pandas as pd

from .metrics import _to_datetime_utc

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

_LAST_LINK_ALIASES = (
    "last link created",
    "last link creation",
    "last link date",
    "last link generated",
    "date last link created",
    "last trackable link",
    "last link",
    "lastlinkcreated",
    "lastlinkdate",
)

_FIRST_LINK_ALIASES = (
    "first link created",
    "first link creation",
    "first link date",
    "first link generated",
    "date first link created",
    "first link",
)


def _normalize_header(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name).strip().lower())


def _find_column(columns: list[str], aliases: tuple[str, ...]) -> str | None:
    normalized = {_normalize_header(c): c for c in columns}
    for alias in aliases:
        key = _normalize_header(alias)
        if key in normalized:
            return normalized[key]
    return None


def parse_active_members_csv(source: str | bytes | BinaryIO) -> pd.DataFrame:
    """Return creator_id, last_link, and optional first_link from a CSV export."""
    if isinstance(source, str):
        df = pd.read_csv(source)
    else:
        df = pd.read_csv(source)

    if df.empty:
        return pd.DataFrame(columns=["creator_id", "last_link", "first_link"])

    creator_col = _find_column(list(df.columns), _CREATOR_ID_ALIASES)
    last_col = _find_column(list(df.columns), _LAST_LINK_ALIASES)
    first_col = _find_column(list(df.columns), _FIRST_LINK_ALIASES)

    if not creator_col:
        raise ValueError(
            "Could not find a creator ID column. Expected something like "
            "'Publisher Id', 'PublisherId', or 'Id'."
        )
    if not last_col and not first_col:
        raise ValueError(
            "Could not find a link date column. Expected something like "
            "'Last Link Created' or 'Last Link Date'."
        )

    out = pd.DataFrame()
    work = df.copy()
    work["creator_id"] = work[creator_col].astype(str).str.strip()
    work = work[work["creator_id"].ne("") & work["creator_id"].ne("nan")]
    out["creator_id"] = work["creator_id"].values

    if last_col:
        out["last_link"] = _to_datetime_utc(work[last_col])
    else:
        out["last_link"] = pd.NaT

    if first_col:
        out["first_link"] = _to_datetime_utc(work[first_col])
    else:
        out["first_link"] = out["last_link"]

    out = out.dropna(subset=["last_link", "first_link"], how="all")
    out = out.drop_duplicates(subset=["creator_id"], keep="last")
    return out.reset_index(drop=True)


def parse_active_members_csv_preview(source: str | bytes | BinaryIO) -> dict:
    """Parse plus metadata for the upload UI."""
    if isinstance(source, bytes):
        buffer: str | bytes | BinaryIO = io.BytesIO(source)
    else:
        buffer = source
    df = parse_active_members_csv(buffer)
    return {
        "rows": len(df),
        "with_last_link": int(df["last_link"].notna().sum()) if not df.empty else 0,
        "sample": df.head(5),
    }
