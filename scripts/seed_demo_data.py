#!/usr/bin/env python3
"""Write synthetic demo data into the local SQLite warehouse.

Handy for exercising the "live" code path (storage layer, incremental sync
bookkeeping) end-to-end without real CreatorIQ credentials.

Usage:
    python scripts/seed_demo_data.py
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from creatoriq_dashboard.config import load_config  # noqa: E402
from creatoriq_dashboard.demo_data import generate_demo_data  # noqa: E402
from creatoriq_dashboard.storage import get_engine, record_sync, write_table  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    config = load_config()
    demo = generate_demo_data()
    engine = get_engine(config.db_path)

    write_table(engine, "creators", demo.creators)
    write_table(engine, "campaigns", demo.campaigns)
    write_table(engine, "posts", demo.posts)
    write_table(engine, "links", demo.links)
    write_table(engine, "email_events", demo.email_events)

    now = datetime.now(timezone.utc)
    for resource in ("creators", "campaigns", "posts", "links", "email_events"):
        record_sync(engine, resource, now)

    logger.info("Seeded demo data into %s", config.db_path)
    logger.info(
        "creators=%d posts=%d links=%d email_events=%d",
        len(demo.creators),
        len(demo.posts),
        len(demo.links),
        len(demo.email_events),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
