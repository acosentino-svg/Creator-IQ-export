#!/usr/bin/env python3
"""Huddle export: Oct vs Jul–Sep selection rate, posting, and drop-off.

  PYTHONPATH=src python scripts/export_huddle_oct_vs_jul_sep.py \\
    --posted path/to/posted.csv \\
    --selected path/to/selected.csv \\
    --output-dir exports/huddle_oct_vs_jul_sep_2026
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from creatoriq_dashboard.boosting_halo_effect import (  # noqa: E402
    merge_halo_effect_posts_and_selections,
    parse_halo_posted_csv,
    parse_halo_selected_csv,
)
from creatoriq_dashboard.boosting_selection_impact import build_huddle_oct_vs_jul_sep  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Oct vs Jul–Sep huddle CSV bundle")
    parser.add_argument("--posted", required=True)
    parser.add_argument("--selected", required=True)
    parser.add_argument("--output-dir", default="exports/huddle_oct_vs_jul_sep_2026")
    parser.add_argument("--active-days", type=int, default=30)
    args = parser.parse_args()

    posted = parse_halo_posted_csv(args.posted)
    selected = parse_halo_selected_csv(args.selected)
    content, diag = merge_halo_effect_posts_and_selections(posted, selected)

    period_df, monthly_df, cohort_df, segment_df, bullets = build_huddle_oct_vs_jul_sep(
        content, selected, active_days=args.active_days
    )

    out = Path(args.output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    period_df.to_csv(out / "01_period_comparison.csv", index=False)
    monthly_df.to_csv(out / "02_monthly_jul_oct.csv", index=False)
    cohort_df.to_csv(out / "03_jul_sep_cohort_in_october.csv", index=False)
    segment_df.to_csv(out / "04_segment_summary_at_period_end.csv", index=False)
    (out / "05_huddle_talking_points.txt").write_text("\n".join(f"• {b}" for b in bullets) + "\n", encoding="utf-8")

    readme = out / "README_google_sheets.txt"
    readme.write_text(
        """Huddle bundle — Oct vs Jul–Sep 2026
=====================================
Import into Google Sheets (File → Import → Upload):
  01_period_comparison.csv   — side-by-side KPIs
  02_monthly_jul_oct.csv     — Jul–Oct monthly program metrics
  03_jul_sep_cohort_in_october.csv — Jul–Sep actives → October behavior
  04_segment_summary_at_period_end.csv — who’s still posting vs dark (Sep 30 vs Oct 31)
  05_huddle_talking_points.txt — bullets for the meeting

Posted + selected merges use full-year exports; period filters apply only to metrics.
""",
        encoding="utf-8",
    )

    print(f"Wrote huddle bundle → {out}")
    print(f"  Full posted rows merged: {diag.get('posted_rows', 0):,}")
    for line in bullets:
        print(f"  • {line}")


if __name__ == "__main__":
    main()
