#!/usr/bin/env python3
"""Export campaign activity posts (with captions) for a date range.

Uses CreatorIQ GET /campaign/{id}/activity (same source as the Boosting scorecard).
Requires CREATORIQ_API_KEY and CREATORIQ_DASHBOARD_MODE=live in the environment.

Example:
  python scripts/export_campaign_posts.py \\
    --campaign-id 2206666 \\
    --start 2026-10-01 --end 2026-10-28 \\
    --timezone America/New_York \\
    -o data/boosting_oct_posts.csv
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from creatoriq_dashboard.api_client import CreatorIQClient  # noqa: E402
from creatoriq_dashboard.config import load_config, reset_config_cache  # noqa: E402
from creatoriq_dashboard.normalize import clean_id_columns, normalize_records  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_EXPORT_COLUMNS = [
    "post_id",
    "creator_id",
    "posted_at",
    "platform",
    "post_url",
    "post_caption",
    "views",
    "likes",
    "comments",
    "link_clicks",
    "campaign_name",
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export CreatorIQ campaign posts for a date range.")
    parser.add_argument("--campaign-id", default="2206666", help="CreatorIQ campaign id (default: boosting campaign)")
    parser.add_argument("--start", required=True, help="Inclusive start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="Inclusive end date (YYYY-MM-DD)")
    parser.add_argument(
        "--timezone",
        default="America/New_York",
        help="IANA timezone for interpreting naive API timestamps and date bounds (default: America/New_York)",
    )
    parser.add_argument("-o", "--output", type=Path, required=True, help="Output CSV path")
    parser.add_argument(
        "--progress-every",
        type=int,
        default=10,
        help="Log progress every N API pages (default: 10)",
    )
    return parser.parse_args()


def fetch_campaign_posts(client: CreatorIQClient, campaign_id: str, post_mapping: dict, progress_every: int) -> pd.DataFrame:
    """Page through campaign activity and normalize rows."""
    rows: list[dict] = []
    api_pages = 0
    for raw in client.iter_nested_resource("campaign_activity", path_params={"campaign_id": campaign_id}):
        rows.append(raw)
        if len(rows) % 100 == 0:
            api_pages += 1
            if progress_every and api_pages % progress_every == 0:
                logger.info("Fetched %d API pages (%d posts so far)...", api_pages, len(rows))
    logger.info("Finished API fetch: %d posts", len(rows))
    df = clean_id_columns(pd.DataFrame(normalize_records(rows, post_mapping)), ["post_id", "creator_id", "campaign_id"])
    return df


def filter_by_date_range(
    df: pd.DataFrame,
    start_date: str,
    end_date: str,
    tz_name: str,
) -> pd.DataFrame:
    if df.empty or "posted_at" not in df.columns:
        return df

    start = pd.Timestamp(start_date, tz=tz_name)
    end_exclusive = pd.Timestamp(end_date, tz=tz_name) + pd.Timedelta(days=1)

    posted = pd.to_datetime(df["posted_at"], errors="coerce")
    if posted.dt.tz is None:
        posted = posted.dt.tz_localize(tz_name, ambiguous="infer", nonexistent="NaT")

    mask = (posted >= start) & (posted < end_exclusive)
    out = df.loc[mask].copy()
    out["posted_at"] = posted.loc[mask]
    return out.sort_values("posted_at")


def main() -> int:
    args = _parse_args()
    reset_config_cache()
    config = load_config()
    if config.is_demo and not config.api_key:
        logger.error("Set CREATORIQ_DASHBOARD_MODE=live and CREATORIQ_API_KEY before running.")
        return 1

    post_mapping = config.field_mappings.get("posts", {})
    client = CreatorIQClient(config)

    logger.info(
        "Exporting campaign %s posts from %s through %s (%s)...",
        args.campaign_id,
        args.start,
        args.end,
        args.timezone,
    )
    df = fetch_campaign_posts(client, str(args.campaign_id), post_mapping, args.progress_every)
    if df.empty:
        logger.warning("No posts returned for campaign %s", args.campaign_id)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=DEFAULT_EXPORT_COLUMNS).to_csv(args.output, index=False)
        return 0

    filtered = filter_by_date_range(df, args.start, args.end, args.timezone)
    export_cols = [c for c in DEFAULT_EXPORT_COLUMNS if c in filtered.columns]
    export = filtered[export_cols]

    if "post_caption" in export.columns:
        filled = export["post_caption"].fillna("").astype(str).str.strip().ne("").sum()
        logger.info("Posts in range: %d (%d with non-empty caption)", len(export), filled)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    export.to_csv(args.output, index=False)
    logger.info("Wrote %s (%d rows)", args.output, len(export))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
