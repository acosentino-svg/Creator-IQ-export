"""Shared helpers for resilient table display (live CreatorIQ data may omit columns)."""
from __future__ import annotations

import pandas as pd


def pick_columns(df: pd.DataFrame, columns: list[str], renames: dict[str, str] | None = None) -> pd.DataFrame:
    """Select columns that exist; skip missing ones instead of raising KeyError."""
    if df is None or df.empty:
        return pd.DataFrame()
    available = [c for c in columns if c in df.columns]
    if not available:
        return pd.DataFrame()
    out = df[available].copy()
    if renames:
        out = out.rename(columns={k: v for k, v in renames.items() if k in out.columns})
    return out


def merge_creator_identity(
    metrics_df: pd.DataFrame,
    classified: pd.DataFrame,
    extra_cols: list[str] | None = None,
) -> pd.DataFrame:
    """Attach name / tier / handle when available."""
    identity_cols = ["creator_id", "name", "handle", "tier", "email", "tags"]
    if extra_cols:
        identity_cols.extend(extra_cols)
    identity_cols = list(dict.fromkeys(identity_cols))
    available = [c for c in identity_cols if c in classified.columns]
    if metrics_df.empty:
        return metrics_df
    if "creator_id" not in metrics_df.columns or not available:
        return metrics_df
    identity = classified[available].drop_duplicates(subset=["creator_id"])
    return metrics_df.merge(identity, on="creator_id", how="left")
