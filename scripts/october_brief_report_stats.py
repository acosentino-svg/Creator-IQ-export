#!/usr/bin/env python3
"""Print October brief report stats from CreatorIQ export CSVs (eligible posts only)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from creatoriq_dashboard.boosting_rules import is_eligible_boosting_content  # noqa: E402
from creatoriq_dashboard.caption_themes import THEME_COLUMNS, add_theme_columns  # noqa: E402
from creatoriq_dashboard.config import load_config  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("october_csv", type=Path)
    parser.add_argument("--september-posts", type=int, default=661, help="Sep eligible posts (prior baseline)")
    parser.add_argument("--september-creators", type=int, default=166, help="Sep active eligible creators")
    args = parser.parse_args()

    config = load_config()
    df = pd.read_csv(args.october_csv)
    mask = df.apply(lambda row: is_eligible_boosting_content(row, config=config), axis=1)
    elig = df.loc[mask].copy()
    tagged = add_theme_columns(elig)

    oct_posts = len(elig)
    oct_creators = elig["creator_id"].nunique()
    sep_posts = args.september_posts
    sep_creators = args.september_creators

    post_delta = oct_posts - sep_posts
    post_pct = post_delta / sep_posts if sep_posts else 0
    creator_delta = oct_creators - sep_creators

    sep_ppc = sep_posts / sep_creators if sep_creators else 0
    oct_ppc = oct_posts / oct_creators if oct_creators else 0
    ppc_pct = (oct_ppc - sep_ppc) / sep_ppc if sep_ppc else 0

    main_themes = [
        "theme_fall_or_fall_refresh",
        "theme_halloween",
        "theme_pre_holiday",
        "theme_category_specific",
        "theme_single_product_highlight",
    ]
    any_theme = tagged[main_themes].any(axis=1).sum()

    print("=== General boosting program (eligible posts, both hashtags) ===")
    print(f"September posts: {sep_posts}")
    print(f"October posts: {oct_posts}")
    print(f"Change: +{post_delta} ({post_pct * 100:.1f}%)")
    print(f"September creators: {sep_creators}")
    print(f"October creators: {oct_creators}")
    print(f"Creator change: {creator_delta:+d}")
    print(f"Posts per active creator: ~{sep_ppc:.1f} (Sep) → ~{oct_ppc:.1f} (Oct) ({ppc_pct * 100:+.0f}%)")
    print()
    print("=== Content vs brief themes (October, eligible; pillars can overlap) ===")
    labels = {
        "theme_fall_or_fall_refresh": "1. Fall/fall refresh",
        "theme_halloween": "2. Halloween",
        "theme_pre_holiday": "3. Pre-holiday",
        "theme_category_specific": "4. Category-specific (any)",
        "theme_category_sideboard": "   Sideboards/consoles",
        "theme_category_pet": "   Pet",
        "theme_category_wayfair_verified": "   Wayfair Verified",
        "theme_single_product_highlight": "5. Single product highlights",
    }
    for col in THEME_COLUMNS:
        print(f"{labels.get(col, col)}: {int(tagged[col].sum())}")
    print(f"Eligible posts matching ≥1 pillar: {any_theme} ({any_theme / oct_posts * 100:.0f}% of October eligible)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
