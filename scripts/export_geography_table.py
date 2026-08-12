#!/usr/bin/env python3
"""Export enrolled creator location fields for Looker Studio / Google Sheets.

Reads the local SQLite warehouse (from GitHub Actions sync or refresh_data.py)
and writes a flat CSV with normalized geography columns Looker can map.

Usage:
    python scripts/export_geography_table.py
    python scripts/export_geography_table.py --output data/creators_geography.csv
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from creatoriq_dashboard.config import load_config  # noqa: E402
from creatoriq_dashboard.geography import enrich_creator_locations  # noqa: E402
from creatoriq_dashboard.storage import get_engine, read_table  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

LOOKER_COLUMNS = [
    "creator",
    "creator_id",
    "network_publisher_id",
    "city",
    "state_region",
    "country",
    "state_code",
    "program_status",
    "tier",
    "joined_date",
]


def build_geography_table(db_path: Path, us_only_program: bool = True):
    import pandas as pd

    engine = get_engine(db_path)
    creators = read_table(engine, "creators")
    if creators.empty:
        return pd.DataFrame(columns=LOOKER_COLUMNS)

    enriched = enrich_creator_locations(creators, us_only_program=us_only_program)
    return pd.DataFrame(
        {
            "creator": enriched.get("name"),
            "creator_id": enriched.get("creator_id"),
            "network_publisher_id": enriched.get("network_publisher_id"),
            "city": enriched.get("city_normalized"),
            "state_region": enriched.get("state"),
            "country": enriched.get("country_normalized"),
            "state_code": enriched.get("state_normalized"),
            "program_status": enriched.get("status"),
            "tier": enriched.get("tier"),
            "joined_date": enriched.get("joined_date"),
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Export creator geography CSV for Looker Studio.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output CSV path (default: data/creators_geography.csv next to warehouse.db)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to warehouse.db (default: from config / CREATORIQ_DB_PATH)",
    )
    args = parser.parse_args()

    config = load_config()
    db_path = args.db or config.db_path
    if not db_path.exists():
        logger.error("No warehouse at %s — run GitHub Actions sync or refresh_data.py first.", db_path)
        return 1

    us_only = bool(config.settings.get("geography", "us_only_program", default=True))
    table = build_geography_table(db_path, us_only_program=us_only)
    output = args.output or db_path.parent / "creators_geography.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(output, index=False)
    logger.info("Exported %d creators → %s", len(table), output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
