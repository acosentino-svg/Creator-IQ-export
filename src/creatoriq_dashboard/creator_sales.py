"""Optional affiliate sales / transactions file (creator_sales_ranking.csv)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

SALES_FILENAME = "creator_sales_ranking.csv"


def default_sales_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / SALES_FILENAME


def load_creator_sales(path: Path | None = None) -> pd.DataFrame:
    """Return one row per publisher with transaction totals (empty if file missing)."""
    path = path or default_sales_path()
    if not path.is_file():
        return pd.DataFrame(columns=["creator_id", "total_sales", "total_commission", "order_count"])

    df = pd.read_csv(path)
    col_id = next((c for c in df.columns if "publisher" in c.lower() and "id" in c.lower()), None)
    if col_id is None:
        return pd.DataFrame(columns=["creator_id", "total_sales", "total_commission", "order_count"])

    rename = {col_id: "creator_id"}
    for c in df.columns:
        low = c.lower()
        if "total sales" in low:
            rename[c] = "total_sales"
        elif "commission" in low:
            rename[c] = "total_commission"
        elif "order" in low:
            rename[c] = "order_count"

    out = df.rename(columns=rename)
    out["creator_id"] = out["creator_id"].astype(str).str.strip()
    for col in ("total_sales", "total_commission", "order_count"):
        if col not in out.columns:
            out[col] = 0
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0)
    return out[["creator_id", "total_sales", "total_commission", "order_count"]].drop_duplicates(subset=["creator_id"])


def merge_sales_into_summary(summary: pd.DataFrame, sales: pd.DataFrame) -> pd.DataFrame:
    if summary.empty:
        return summary
    out = summary.copy()
    if sales.empty:
        out["total_sales"] = 0.0
        out["order_count"] = 0
        out["has_transactions"] = False
        return out
    merged = out.merge(sales, on="creator_id", how="left")
    merged["total_sales"] = merged["total_sales"].fillna(0)
    merged["order_count"] = merged["order_count"].fillna(0)
    merged["has_transactions"] = merged["order_count"] > 0
    return merged
