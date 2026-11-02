#!/usr/bin/env python3
"""Pull boosting posts from CreatorIQ API + merge tracker → Google Sheets CSVs.

No Streamlit app required. Put the same secrets in a `.env` file in the repo root.

  pip install -r requirements.txt
  # .env: CREATORIQ_DASHBOARD_MODE=live, CREATORIQ_API_KEY=..., CREATORIQ_BASE_URL=...

  PYTHONPATH=src python scripts/pull_boosting_halo_google_sheets.py \\
    --selected /path/to/WCP_Boosting_Tracker.csv \\
    --output-dir ./halo_oct_2026 \\
    --post-date-start 2026-10-01 --post-date-end 2026-10-31 --minimal
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from creatoriq_dashboard.boosting_data_access import sync_and_store_boosting_content  # noqa: E402
from creatoriq_dashboard.boosting_halo_effect import export_halo_effect_csv_dir  # noqa: E402
from creatoriq_dashboard.config import load_config  # noqa: E402


def api_content_to_posted_csv(content: pd.DataFrame, path: Path) -> None:
    """Write CreatorIQ-shaped posted CSV so halo merge can run."""
    desc = content["eligible"].map(
        lambda ok: "#WayfairCreator #wayfairelevate" if ok else ""
    ) if "eligible" in content.columns else ""
    out = pd.DataFrame(
        {
            "Post Id": "",
            "Creator Name": content.get("creator_name", pd.Series("", index=content.index)),
            "SocialHandle": content.get("creator_handle", pd.Series("", index=content.index)),
            "Post Description": desc,
            "Post Link": content["content_url"],
            "Post Date": content["post_date"],
            "Publisher Id": content["creator_id"],
        }
    )
    out.to_csv(path, index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="API sync + tracker → Google Sheets CSV bundle")
    parser.add_argument("--selected", required=True, help="WCP Boosting Tracker CSV")
    parser.add_argument("--output-dir", required=True, help="Folder for CSV exports")
    parser.add_argument("--post-date-start", default=None)
    parser.add_argument("--post-date-end", default=None)
    parser.add_argument("--minimal", action="store_true")
    args = parser.parse_args()

    config = load_config()
    if config.is_demo:
        print("ERROR: Set CREATORIQ_DASHBOARD_MODE=live in .env (not just Streamlit secrets).")
        sys.exit(1)

    print("Syncing boosting posts from CreatorIQ API…")
    content = sync_and_store_boosting_content(config)
    if content.empty:
        print("ERROR: API returned 0 rows. Check key, campaign 2206666, WBP tags.")
        sys.exit(1)

    print(f"Synced {len(content):,} rows · max post_date {content['post_date'].max()}")

    out_dir = Path(args.output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    content.to_csv(out_dir / "api_content_raw_snapshot.csv", index=False)

    posted_path = out_dir / "_posted_from_api.csv"
    api_content_to_posted_csv(content, posted_path)

    diag = export_halo_effect_csv_dir(
        str(posted_path),
        str(Path(args.selected).expanduser()),
        str(out_dir),
        post_date_start=args.post_date_start,
        post_date_end=args.post_date_end,
        minimal=args.minimal,
        config=config,
    )
    print(f"Wrote Google Sheets CSVs → {diag['output_dir']}")
    print(f"  Eligible posts in filter: {diag.get('eligible_posts', 0):,}")


if __name__ == "__main__":
    main()
