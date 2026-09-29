#!/usr/bin/env python3
"""Build Excel halo-effect report from CreatorIQ posted + boosting selected CSVs.

Example:
  PYTHONPATH=src python scripts/export_halo_effect_excel.py \\
    --posted ~/Downloads/boosting_halo_effect_-_2026_posted.csv \\
    --selected ~/Downloads/boosting_halo_effect_-_2026_selected.csv \\
    --output ~/Downloads/boosting_halo_effect_report.xlsx
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from creatoriq_dashboard.boosting_halo_effect import export_halo_effect_workbook  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Export halo effect analysis to Excel.")
    parser.add_argument("--posted", required=True, help="CreatorIQ posted CSV (Post Link, Post Date, Publisher Id)")
    parser.add_argument("--selected", required=True, help="Boosting tracker CSV (Content Used, Duration of Usage)")
    parser.add_argument(
        "--output",
        default="boosting_halo_effect_report.xlsx",
        help="Output .xlsx path (default: boosting_halo_effect_report.xlsx)",
    )
    parser.add_argument("--drought-days", type=int, default=90, help="Days without selection = dried up")
    parser.add_argument("--active-days", type=int, default=30, help="Days to count as still posting")
    args = parser.parse_args()

    out = Path(args.output).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    diag = export_halo_effect_workbook(
        str(Path(args.posted).expanduser()),
        str(Path(args.selected).expanduser()),
        str(out),
        drought_days=args.drought_days,
        active_days=args.active_days,
    )
    print(f"Wrote {out}")
    print(f"  Posts: {diag.get('posted_rows', 0):,} | Selected matched: {diag.get('posts_matched_to_selection', 0):,}")
    print(f"  Selected not in posted: {diag.get('selected_not_in_posted', 0):,}")


if __name__ == "__main__":
    main()
