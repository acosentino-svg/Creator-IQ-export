"""Overview KPIs for the Active Creator Report (date-range activity rollup)."""
from __future__ import annotations

from typing import Any

import pandas as pd

from .hybrid_diagnostics import HybridDiagnostics


def _txn_amount_col(df: pd.DataFrame) -> str | None:
    for cand in df.columns:
        low = str(cand).lower()
        if "sale" in low and "amount" in low:
            return cand
        if low in ("total sales", "total_sales", "revenue", "sale_amount"):
            return cand
    return None


def _aggregate_transactions_in_range(transactions: pd.DataFrame) -> pd.DataFrame:
    if transactions.empty or "creator_id" not in transactions.columns:
        return pd.DataFrame(columns=["creator_id", "transactions_in_range", "sales_in_range"])

    out = transactions.copy()
    out["creator_id"] = out["creator_id"].astype(str).str.strip()
    amt_col = _txn_amount_col(out)
    if amt_col:
        out["sales_in_range"] = pd.to_numeric(out[amt_col], errors="coerce").fillna(0)
    else:
        out["sales_in_range"] = 0.0
    grp = (
        out.groupby("creator_id", as_index=False)
        .agg(transactions_in_range=("creator_id", "size"), sales_in_range=("sales_in_range", "sum"))
    )
    return grp


def compute_active_creator_overview(
    summary: pd.DataFrame,
    posts: pd.DataFrame,
    links: pd.DataFrame,
    transactions: pd.DataFrame,
    diagnostics: HybridDiagnostics | None,
) -> dict[str, Any]:
    """Active in range = posted and/or linked in range (transactions alone do not count)."""
    s = summary.copy() if summary is not None and not summary.empty else pd.DataFrame()

    if not s.empty:
        s["posts_in_range"] = pd.to_numeric(s.get("posts_in_range", 0), errors="coerce").fillna(0)
        s["links_in_range"] = pd.to_numeric(s.get("links_in_range", 0), errors="coerce").fillna(0)
        posted = s["posts_in_range"] > 0
        linked = s["links_in_range"] > 0
        active = posted | linked
        posting_creators = int(posted.sum())
        linking_creators = int(linked.sum())
        active_creators = int(active.sum())
    else:
        posting_creators = linking_creators = active_creators = 0

    total_posts = 0
    if posts is not None and not posts.empty and "posted_at" in posts.columns:
        total_posts = int(len(posts))
    elif not s.empty:
        total_posts = int(s["posts_in_range"].sum())

    total_links = 0
    if links is not None and not links.empty:
        total_links = int(len(links))
    elif not s.empty:
        total_links = int(s["links_in_range"].sum())

    txn_by_creator = _aggregate_transactions_in_range(transactions)
    rpis = int(len(txn_by_creator)) if not txn_by_creator.empty else 0
    total_sales = float(txn_by_creator["sales_in_range"].sum()) if not txn_by_creator.empty else 0.0

    if rpis == 0 and not s.empty and "has_transactions" in s.columns:
        rpis = int(s["has_transactions"].sum())
        if "total_sales" in s.columns:
            total_sales = float(pd.to_numeric(s.loc[s["has_transactions"], "total_sales"], errors="coerce").sum())

    top = pd.DataFrame()
    if not s.empty:
        merge = s
        if not txn_by_creator.empty:
            merge = s.merge(txn_by_creator, on="creator_id", how="left")
        for col in ("transactions_in_range", "sales_in_range"):
            if col not in merge.columns:
                merge[col] = 0
            merge[col] = pd.to_numeric(merge[col], errors="coerce").fillna(0)
        if "transactions_in_range" not in merge.columns:
            merge["transactions_in_range"] = merge.get("order_count", 0)
        if "sales_in_range" not in merge.columns:
            merge["sales_in_range"] = merge.get("total_sales", 0)

        pr = merge.get("posts_in_range", pd.Series(0, index=merge.index)).fillna(0)
        lr = merge.get("links_in_range", pd.Series(0, index=merge.index)).fillna(0)
        active_df = merge[(pr > 0) | (lr > 0)]
        if active_df.empty:
            active_df = merge
        score = (
            active_df.get("posts_in_range", 0).fillna(0) * 3
            + active_df.get("links_in_range", 0).fillna(0) * 2
            + active_df.get("transactions_in_range", 0).fillna(0) * 5
            + active_df.get("sales_in_range", 0).fillna(0) / 1000
        )
        active_df = active_df.copy()
        active_df["_score"] = score
        sort_cols = ["_score"]
        if "name" in active_df.columns:
            top = active_df.nlargest(25, sort_cols)
        else:
            top = active_df.nlargest(25, sort_cols)

    hybrid_line = None
    if diagnostics is not None:
        hybrid_line = diagnostics.render_markdown().split("\n\n")[1] if diagnostics else None
        for line in diagnostics.render_markdown().split("\n\n"):
            if line.startswith("**Hybrid split:**"):
                hybrid_line = line
                break

    return {
        "active_creators": active_creators,
        "posting_creators": posting_creators,
        "total_posts": total_posts,
        "linking_creators": linking_creators,
        "total_links": total_links,
        "rpis": rpis,
        "total_sales": total_sales,
        "top_25": top,
        "hybrid_line": hybrid_line,
        "txn_by_creator": txn_by_creator,
    }
