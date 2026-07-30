"""Maps raw CreatorIQ API records onto the dashboard's normalized schema.

The mapping itself lives in config/field_mappings.yaml so it can be adjusted
per-account without touching this code.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from .api_client import get_path


def normalize_record(raw: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    """Apply a {normalized_field: raw_dotted_path} mapping to one raw record."""
    return {normalized_field: get_path(raw, raw_path) for normalized_field, raw_path in mapping.items()}


def normalize_records(raw_records: list[dict[str, Any]], mapping: dict[str, str]) -> list[dict[str, Any]]:
    return [normalize_record(r, mapping) for r in raw_records]


def clean_id_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """CreatorIQ returns IDs as JSON numbers; once a column has any missing
    values pandas silently promotes it to float64 (turning e.g. creator_id
    28604720 into "28604720.0" once stringified), which breaks equality
    joins against the same ID formatted as a clean int elsewhere. Normalize
    every ID-like column to a clean nullable string early, right after
    building a DataFrame from normalized records.
    """
    if df.empty:
        return df
    df = df.copy()
    for col in columns:
        if col not in df.columns:
            continue
        numeric = pd.to_numeric(df[col], errors="coerce")
        is_whole_number = numeric.notna() & (numeric % 1 == 0)
        cleaned = df[col].astype("string")
        cleaned[is_whole_number] = numeric[is_whole_number].astype("int64").astype(str)
        df[col] = cleaned
    return df
