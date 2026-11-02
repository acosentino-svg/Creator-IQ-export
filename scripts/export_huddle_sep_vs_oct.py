#!/usr/bin/env python3
"""Huddle follow-up: September baseline vs October (post-switch).

Last month’s read was effectively “where we are through September.” This export
compares **Sep vs Oct only** — not October vs Jul–Sep lumped.

  PYTHONPATH=src python scripts/export_huddle_sep_vs_oct.py \\
    --posted path/to/posted.csv \\
    --selected path/to/selected.csv \\
    --output-dir exports/huddle_sep_vs_oct_2026
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from creatoriq_dashboard.boosting_halo_effect import (  # noqa: E402
    merge_halo_effect_posts_and_selections,
    parse_halo_posted_csv,
    parse_halo_selected_csv,
)
from creatoriq_dashboard.boosting_brief_themes import summarize_brief_themes_by_month  # noqa: E402
from creatoriq_dashboard.boosting_scorecard import _eligible_content, normalize_content_raw  # noqa: E402
from creatoriq_dashboard.boosting_selection_impact import (  # noqa: E402
    build_huddle_sep_vs_oct,
    build_creator_selection_timeline,
    summarize_timeline_segments_enriched,
    _timeline_at,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sep vs Oct huddle CSV bundle (follow-up)")
    parser.add_argument("--posted", required=True)
    parser.add_argument("--selected", required=True)
    parser.add_argument("--output-dir", default="exports/huddle_sep_vs_oct_2026")
    parser.add_argument("--active-days", type=int, default=30)
    args = parser.parse_args()

    posted = parse_halo_posted_csv(args.posted)
    selected = parse_halo_selected_csv(args.selected)
    content, diag = merge_halo_effect_posts_and_selections(posted, selected)

    period_df, monthly_df, cohort_df, segment_df, dark_df, retention_df, bullets = build_huddle_sep_vs_oct(
        content, selected, active_days=args.active_days
    )

    content_norm = normalize_content_raw(content)
    eligible = _eligible_content(content_norm)
    brief_monthly = summarize_brief_themes_by_month(eligible)

    tl_sep = _timeline_at(content, "2026-09-30", active_days=args.active_days)
    tl_oct = _timeline_at(content, "2026-10-31", active_days=args.active_days)
    segment_enriched = pd.concat(
        [
            summarize_timeline_segments_enriched(
                tl_sep, content_norm, focus_month="2026-09", as_of="2026-09-30"
            ),
            summarize_timeline_segments_enriched(
                tl_oct, content_norm, focus_month="2026-10", as_of="2026-10-31"
            ),
        ],
        ignore_index=True,
    )

    out = Path(args.output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    period_df.to_csv(out / "01_sep_vs_oct_kpis.csv", index=False)
    monthly_df.to_csv(out / "02_monthly_aug_sep_oct.csv", index=False)
    cohort_df.to_csv(out / "03_september_actives_in_october.csv", index=False)
    segment_df.to_csv(out / "04_segments_sep30_vs_oct31_simple.csv", index=False)
    segment_enriched.to_csv(out / "04_segment_summary_enriched.csv", index=False)
    brief_monthly.to_csv(out / "08_brief_themes_by_month.csv", index=False)
    dark_df.to_csv(out / "05_stopped_posting_between_months.csv", index=False)
    retention_df.to_csv(out / "06_month_to_month_retention.csv", index=False)
    (out / "07_huddle_talking_points.txt").write_text("\n".join(f"• {b}" for b in bullets) + "\n", encoding="utf-8")

    readme = out / "README_google_sheets.txt"
    readme.write_text(
        """Huddle follow-up — September vs October 2026
=============================================
Compares **Sep** (last month’s baseline) to **Oct** (brief + higher boosting).
Does NOT lump Jul–Aug with September.

Import into Google Sheets:
  01_sep_vs_oct_kpis.csv
  04_segment_summary_enriched.csv — segments + avg posts, Oct brief-themed creators
  08_brief_themes_by_month.csv — fall / Halloween / holiday / pet / etc. in captions
  05_stopped_posting_between_months.csv — Sep→Oct drop-off vs Aug→Sep
  03_september_actives_in_october.csv — Sep cohort continuation
  07_huddle_talking_points.txt
""",
        encoding="utf-8",
    )

    print(f"Wrote huddle bundle → {out}")
    print(f"  Full posted rows merged: {diag.get('posted_rows', 0):,}")
    for line in bullets:
        print(f"  • {line}")


if __name__ == "__main__":
    main()
