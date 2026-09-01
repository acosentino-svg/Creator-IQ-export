"""Data quality checks for Boosting content uploads."""
from __future__ import annotations

import pandas as pd


def validate_content_raw(df: pd.DataFrame) -> dict:
    """Return warnings and duplicate flags without mutating data."""
    warnings: list[str] = []
    duplicate_urls: pd.DataFrame = pd.DataFrame()
    duplicate_keys: pd.DataFrame = pd.DataFrame()

    if df is None or df.empty:
        return {
            "warnings": ["No content rows loaded yet. Upload a monthly export or sync from CreatorIQ."],
            "duplicate_urls": duplicate_urls,
            "duplicate_keys": duplicate_keys,
            "row_count": 0,
            "eligible_count": 0,
        }

    if "creator_id" not in df.columns or df["creator_id"].isna().all():
        warnings.append("Missing Publisher ID — creator-level metrics will be incomplete.")
    elif df["creator_id"].astype(str).str.strip().isin(["", "nan"]).any():
        missing = int(df["creator_id"].astype(str).str.strip().isin(["", "nan"]).sum())
        warnings.append(f"{missing:,} rows missing Publisher ID.")

    if "post_date" in df.columns and df["post_date"].isna().all():
        warnings.append("Missing post dates — month assignments may be wrong.")

    if "paid_spend" in df.columns and (df["paid_spend"] < 0).any():
        warnings.append("Negative paid media spend detected.")
    if "boosted_revenue" in df.columns and (df["boosted_revenue"] < 0).any():
        warnings.append("Negative boosted revenue detected.")

    if "content_url" in df.columns:
        dup_mask = df.duplicated(subset=["content_url", "month"], keep=False)
        if dup_mask.any():
            duplicate_urls = df[dup_mask].sort_values(["content_url", "month"])
            warnings.append(
                f"{duplicate_urls['content_url'].nunique():,} content URLs appear more than once for the same month."
            )

    key_cols = [c for c in ("creator_id", "post_date", "platform") if c in df.columns]
    if len(key_cols) == 3:
        dup_key_mask = df.duplicated(subset=key_cols, keep=False)
        if dup_key_mask.any():
            duplicate_keys = df[dup_key_mask].sort_values(key_cols)
            warnings.append(
                f"{len(duplicate_keys):,} rows share the same Publisher ID + Post Date + Platform (possible duplicates)."
            )

    eligible_count = int(df["eligible"].sum()) if "eligible" in df.columns else 0
    if eligible_count == 0 and len(df) > 0:
        warnings.append(
            "No eligible content rows. Check that captions include both #WayfairCreator and #wayfairelevate "
            "(any capitalization counts), or map the Eligible column in your upload."
        )

    spend_available = "paid_spend" in df.columns and (df["paid_spend"] > 0).any()
    if not spend_available:
        warnings.append("ROAS will show as unavailable — no paid media spend in the dataset.")

    return {
        "warnings": warnings,
        "duplicate_urls": duplicate_urls,
        "duplicate_keys": duplicate_keys,
        "row_count": len(df),
        "eligible_count": eligible_count,
        "spend_available": spend_available,
    }
