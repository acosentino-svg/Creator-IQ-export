"""Diagnostics text for CSV backlog + Live API (active creator report)."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class HybridDiagnostics:
    activity_start: str
    activity_end: str
    csv_range_start: str | None = None
    csv_range_end: str | None = None
    csv_links_in_range: int = 0
    csv_transactions_in_range: int = 0
    csv_posts_in_range: int = 0
    api_range_start: str | None = None
    api_range_end: str | None = None
    api_links_in_range: int = 0
    api_transactions_in_range: int = 0
    api_posts_in_range: int = 0
    csv_total_links: int = 0
    csv_total_transactions: int = 0
    csv_total_posts: int = 0
    csv_total_publisher_names: int = 0
    range_links: int = 0
    range_posts: int = 0
    range_transactions: int = 0
    links_fetch_rows: int = 0
    links_fetch_pages: int = 0
    transactions_fetch_rows: int = 0
    transactions_fetch_pages: int = 0
    publishers_with_links: int = 0
    publishers_with_posts: int = 0
    creator_names_resolved: int = 0
    links_rows: int = 0
    links_publisher_col: str = "PublisherId"
    links_with_publisher_id: int = 0
    activity_rows: int = 0
    activity_publisher_col: str = "PublisherId"
    activity_with_publisher_id: int = 0
    txn_rows: int = 0
    txn_publisher_col: str = "PublisherId"
    txn_with_publisher_id: int = 0
    campaign_id: str = "2206666"
    notes: list[str] = field(default_factory=list)

    def render_markdown(self) -> str:
        lines = [
            "**Data source:** CSV backlog + Live API",
            (
                f"**Hybrid split:** CSV {self.csv_range_start}–{self.csv_range_end} "
                f"({self.csv_links_in_range:,} links / {self.csv_transactions_in_range:,} tx / {self.csv_posts_in_range:,} posts) · "
                f"API {self.api_range_start}–{self.api_range_end} "
                f"({self.api_links_in_range:,} links / {self.api_transactions_in_range:,} tx / {self.api_posts_in_range:,} posts)"
            ),
            (
                f"**CSV file totals (all dates):** {self.csv_total_links:,} links · "
                f"{self.csv_total_transactions:,} transactions · {self.csv_total_posts:,} posts · "
                f"{self.csv_total_publisher_names:,} publisher names"
            ),
            (
                f"**Records in selected date range:** {self.range_links:,} links · "
                f"{self.range_posts:,} posts · {self.range_transactions:,} transactions"
            ),
            f"**Links fetch:** {self.links_fetch_rows:,}/{self.links_fetch_rows:,} records · {self.links_fetch_pages} pages",
            (
                f"**Transactions fetch:** {self.transactions_fetch_rows:,}/{self.transactions_fetch_rows:,} records · "
                f"{self.transactions_fetch_pages} pages"
            ),
            (
                f"**Publishers counted:** {self.publishers_with_links:,} with links · "
                f"{self.publishers_with_posts:,} with posts · {self.creator_names_resolved:,} creator names resolved"
            ),
            "",
            f"**Campaign activity** ({self.campaign_id}) — {self.activity_rows:,} rows · "
            f"publisher column: {self.activity_publisher_col} · {self.activity_with_publisher_id:,} rows with a publisher id",
            "",
            f"**Links** — {self.links_rows:,} rows · publisher column: {self.links_publisher_col} · "
            f"{self.links_with_publisher_id:,} rows with a publisher id",
            "",
            f"**Transactions** — {self.txn_rows:,} rows · publisher column: {self.txn_publisher_col} · "
            f"{self.txn_with_publisher_id:,} rows with a publisher id",
        ]
        for note in self.notes:
            lines.append(f"- _{note}_")
        return "\n\n".join(lines)


def _publisher_col(df: pd.DataFrame) -> tuple[str, pd.Series]:
    for cand in ("creator_id", "PublisherId", "Publisher Id", "publisher_id", "PublisherID"):
        if cand in df.columns:
            return cand, df[cand].astype(str)
    return "creator_id", pd.Series(dtype=str)


def _count_publishers(df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    _, col = _publisher_col(df)
    return col.replace("", pd.NA).dropna().nunique()


def _rows_with_publisher(df: pd.DataFrame) -> tuple[int, int, str]:
    if df.empty:
        return 0, 0, "PublisherId"
    name, col = _publisher_col(df)
    valid = col.str.strip().replace({"nan": "", "none": ""})
    with_id = int((valid != "").sum())
    return len(df), with_id, name


def build_hybrid_diagnostics(
    *,
    activity_start: pd.Timestamp,
    activity_end: pd.Timestamp,
    posts: pd.DataFrame,
    links: pd.DataFrame,
    transactions: pd.DataFrame,
    publisher_names: pd.DataFrame,
    csv_posts: pd.DataFrame | None = None,
    csv_links: pd.DataFrame | None = None,
    csv_transactions: pd.DataFrame | None = None,
    api_meta: dict | None = None,
    campaign_id: str = "2206666",
) -> HybridDiagnostics:
    meta = api_meta or {}
    start_s = activity_start.date().isoformat()
    end_s = activity_end.date().isoformat()

    csv_p = csv_posts if csv_posts is not None else pd.DataFrame()
    csv_l = csv_links if csv_links is not None else pd.DataFrame()
    csv_t = csv_transactions if csv_transactions is not None else pd.DataFrame()

    act_rows, act_with, act_col = _rows_with_publisher(posts)
    link_rows, link_with, link_col = _rows_with_publisher(links)
    txn_rows, txn_with, txn_col = _rows_with_publisher(transactions)

    return HybridDiagnostics(
        activity_start=start_s,
        activity_end=end_s,
        csv_range_start=start_s,
        csv_range_end=end_s,
        csv_links_in_range=len(csv_l),
        csv_transactions_in_range=len(csv_t),
        csv_posts_in_range=len(csv_p),
        api_range_start=start_s,
        api_range_end=end_s,
        api_links_in_range=meta.get("api_links", len(links)),
        api_transactions_in_range=meta.get("api_transactions", len(transactions)),
        api_posts_in_range=meta.get("api_posts", len(posts)),
        csv_total_links=meta.get("csv_total_links", len(csv_l)),
        csv_total_transactions=meta.get("csv_total_transactions", len(csv_t)),
        csv_total_posts=meta.get("csv_total_posts", len(csv_p)),
        csv_total_publisher_names=len(publisher_names),
        range_links=len(links),
        range_posts=len(posts),
        range_transactions=len(transactions),
        links_fetch_rows=meta.get("links_fetch_rows", len(links)),
        links_fetch_pages=meta.get("links_fetch_pages", 0),
        transactions_fetch_rows=meta.get("transactions_fetch_rows", len(transactions)),
        transactions_fetch_pages=meta.get("transactions_fetch_pages", 0),
        publishers_with_links=_count_publishers(links),
        publishers_with_posts=_count_publishers(posts),
        creator_names_resolved=len(publisher_names),
        links_rows=link_rows,
        links_publisher_col=link_col,
        links_with_publisher_id=link_with,
        activity_rows=act_rows,
        activity_publisher_col=act_col,
        activity_with_publisher_id=act_with,
        txn_rows=txn_rows,
        txn_publisher_col=txn_col,
        txn_with_publisher_id=txn_with,
        campaign_id=campaign_id,
        notes=meta.get("notes", []),
    )
