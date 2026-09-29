#!/usr/bin/env python3
"""Export halo-effect report as CSVs for Google Sheets (one file per tab).

Example:
  PYTHONPATH=src python scripts/export_halo_effect_google_sheets.py \\
    --posted ~/Downloads/boosting_halo_effect_-_2026_posted.csv \\
    --selected ~/Downloads/boosting_halo_effect_-_2026_selected.csv \\
    --output-dir ~/Downloads/halo_effect_for_google_sheets
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from creatoriq_dashboard.boosting_halo_effect import export_halo_effect_csv_dir  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Export halo effect tables as CSVs for Google Sheets.")
    parser.add_argument("--posted", required=True, help="CreatorIQ posted CSV")
    parser.add_argument("--selected", required=True, help="Boosting selected tracker CSV")
    parser.add_argument(
        "--output-dir",
        default="halo_effect_for_google_sheets",
        help="Folder to write numbered CSV files (default: halo_effect_for_google_sheets)",
    )
    parser.add_argument("--drought-days", type=int, default=90)
    parser.add_argument("--active-days", type=int, default=30)
    parser.add_argument(
        "--post-date-start",
        default=None,
        help="Only posts on/after this date (e.g. 2026-07-01)",
    )
    parser.add_argument(
        "--post-date-end",
        default=None,
        help="Only posts on/before this date (e.g. 2026-09-30)",
    )
    args = parser.parse_args()

    diag = export_halo_effect_csv_dir(
        str(Path(args.posted).expanduser()),
        str(Path(args.selected).expanduser()),
        str(Path(args.output_dir).expanduser()),
        drought_days=args.drought_days,
        active_days=args.active_days,
        post_date_start=args.post_date_start,
        post_date_end=args.post_date_end,
    )
    print(f"Wrote CSV bundle to {diag['output_dir']}")
    print("  Open 01_data_quality.csv in Google Sheets for the Check / Result table.")
    print(f"  Posts: {diag.get('posted_rows', 0):,} | Selected not in posted: {diag.get('selected_not_in_posted', 0):,}")


if __name__ == "__main__":
    main()
