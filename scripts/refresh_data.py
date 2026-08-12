#!/usr/bin/env python3
"""Pull the latest data from the CreatorIQ API into the local SQLite cache.

Run this on a schedule (cron, GitHub Actions, Airflow, etc.) so the
Streamlit app always has fresh data without calling the API on every page
load. Requires CREATORIQ_DASHBOARD_MODE=live and valid API credentials
in .env (see .env.example).

Usage:
    python scripts/refresh_data.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from creatoriq_dashboard.config import load_config  # noqa: E402
from creatoriq_dashboard.etl import sync_all, sync_enrolled_creators  # noqa: E402
from creatoriq_dashboard.storage import ensure_performance_indexes, get_engine  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Refresh CreatorIQ data into the local SQLite cache.")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Use live_sync.cloud_safe limits (few campaigns/pages) — for Streamlit Cloud.",
    )
    parser.add_argument(
        "--enrolled-only",
        action="store_true",
        help="Sync enrolled /publishers only (geography map) — skips campaigns, posts, and email.",
    )
    parser.add_argument(
        "--start-page",
        type=int,
        default=1,
        help="Publisher API page to start from (1-based). Use with --max-pages for chunked GitHub sync.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Max publisher API pages to fetch this run. Omit for full sync (all pages).",
    )
    args = parser.parse_args()

    if args.quick:
        os.environ["CREATORIQ_SYNC_PROFILE"] = "cloud_safe"
        logger.info(
            "Quick sync profile: live_sync.cloud_safe limits (~500 enrolled creators, not full program)"
        )

    config = load_config()
    if config.is_demo:
        logger.error(
            "CREATORIQ_DASHBOARD_MODE=%s (demo). Set it to 'live' in your .env and "
            "provide CREATORIQ_API_KEY before running a real refresh.",
            config.mode,
        )
        return 1

    logger.info("Starting CreatorIQ sync against %s ...", config.base_url)
    ensure_performance_indexes(get_engine(config.db_path))
    if args.enrolled_only:
        logger.info("Mode: enrolled creators only (geography / location fields)")
        counts = sync_enrolled_creators(
            config,
            start_page=max(1, args.start_page),
            max_pages=args.max_pages,
        )
    else:
        counts = sync_all(config)
    for resource, count in counts.items():
        if isinstance(count, bool):
            logger.info("  %-14s %s", resource, count)
        else:
            logger.info("  %-14s %d records", resource, count)
    logger.info("Sync complete. Warehouse: %s", config.db_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
