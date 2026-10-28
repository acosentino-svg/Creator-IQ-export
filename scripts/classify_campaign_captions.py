#!/usr/bin/env python3
"""Tag exported campaign posts with caption theme flags and print counts.

Example:
  python scripts/classify_campaign_captions.py \\
    data/boosting_campaign_2206666_posts_2026-10-01_to_2026-10-28.csv \\
    -o data/boosting_oct_posts_by_theme.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from creatoriq_dashboard.caption_themes import (  # noqa: E402
    add_theme_columns,
    assign_primary_theme,
    theme_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify post captions into theme buckets.")
    parser.add_argument("input_csv", type=Path, help="CSV from export_campaign_posts.py")
    parser.add_argument("-o", "--output", type=Path, help="Optional tagged CSV output path")
    parser.add_argument("--caption-column", default="post_caption")
    args = parser.parse_args()

    df = pd.read_csv(args.input_csv)
    tagged = add_theme_columns(df, caption_col=args.caption_column)
    tagged["primary_theme"] = tagged.apply(assign_primary_theme, axis=1)

    total = len(tagged)
    with_caption = tagged[args.caption_column].fillna("").astype(str).str.strip().ne("").sum()
    print(f"Posts analyzed: {total} ({with_caption} with non-empty caption)\n")
    print("Theme counts (a post can match more than one theme):\n")
    summary = theme_summary(tagged)
    for _, row in summary.iterrows():
        print(f"  {row['theme']}: {row['post_count']}")

    print("\nPrimary theme (mutually exclusive, priority: halloween → pre_holiday → fall → category → single → other):\n")
    primary = tagged["primary_theme"].value_counts().sort_values(ascending=False)
    for name, count in primary.items():
        print(f"  {name}: {count}")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        tagged.to_csv(args.output, index=False)
        print(f"\nWrote tagged CSV: {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
