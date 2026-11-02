#!/usr/bin/env python3
"""Export campaign activity as CreatorIQ-style posted CSV (for halo merge).

  PYTHONPATH=src python scripts/export_campaign_posts.py \\
    --campaign-id 2206666 \\
    --since 2026-07-01 \\
    --output campaign_2206666_posts_since_july.csv
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from creatoriq_dashboard.api_client import CreatorIQClient  # noqa: E402
from creatoriq_dashboard.boosting_creatoriq import _fetch_campaign_roster  # noqa: E402
from creatoriq_dashboard.config import load_config  # noqa: E402
from creatoriq_dashboard.normalize import clean_id_columns, normalize_records  # noqa: E402


_TIKTOK_HANDLE_RE = re.compile(r"tiktok\.com/@([^/?#]+)", re.IGNORECASE)


def _handle_from_post_url(url: str) -> str:
    if not url or str(url).lower() in {"nan", "none"}:
        return ""
    match = _TIKTOK_HANDLE_RE.search(str(url))
    return match.group(1).strip() if match else ""


EXPORT_COLUMNS = [
    "Post Id",
    "Creator Name",
    "SocialHandle",
    "Post Description",
    "Post Link",
    "Post Date",
    "Publisher Id",
]


def posts_to_export_df(posts: pd.DataFrame, roster: pd.DataFrame) -> pd.DataFrame:
    name_map: dict[str, str] = {}
    handle_map: dict[str, str] = {}
    if not roster.empty and "creator_id" in roster.columns:
        for _, row in roster.iterrows():
            cid = str(row.get("creator_id", "")).strip()
            if not cid:
                continue
            for col in ("name", "creator_name", "PublisherName"):
                if col in row.index and str(row.get(col, "")).strip() not in {"", "nan"}:
                    name_map[cid] = str(row[col]).strip()
            for col in ("handle", "creator_handle", "username"):
                if col in row.index and str(row.get(col, "")).strip() not in {"", "nan"}:
                    handle_map[cid] = str(row[col]).strip()

    rows = []
    for _, p in posts.iterrows():
        cid = str(p.get("creator_id", "")).strip()
        caption = p.get("post_caption") or p.get("Caption") or ""
        url = p.get("post_url") or ""
        handle = handle_map.get(cid, p.get("creator_handle", "")) or _handle_from_post_url(str(url))
        posted = pd.to_datetime(p.get("posted_at"), utc=True, errors="coerce")
        rows.append(
            {
                "Post Id": p.get("post_id", ""),
                "Creator Name": name_map.get(cid, p.get("creator_name", "")),
                "SocialHandle": handle,
                "Post Description": caption,
                "Post Link": url,
                "Post Date": posted,
                "Publisher Id": cid,
            }
        )
    return pd.DataFrame(rows, columns=EXPORT_COLUMNS)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", default="2206666")
    parser.add_argument("--since", default="2026-07-01", help="Include posts on/after this date (UTC)")
    parser.add_argument("--until", default=None, help="Include posts on/before this date")
    parser.add_argument("--output", default="campaign_posts_export.csv")
    args = parser.parse_args()

    config = load_config()
    if config.is_demo:
        print("ERROR: CREATORIQ_DASHBOARD_MODE=live required (.env or environment).")
        sys.exit(1)

    client = CreatorIQClient(config)
    post_mapping = config.field_mappings.get("posts", {})
    cid = str(args.campaign_id)

    print(f"Fetching activity for campaign {cid}…")
    raw = client.fetch_nested_all("campaign_activity", path_params={"campaign_id": cid})
    posts = clean_id_columns(
        pd.DataFrame(normalize_records(raw, post_mapping)),
        ["post_id", "creator_id", "campaign_id"],
    )
    if posts.empty:
        print("ERROR: No posts returned. Check campaign ID and API access.")
        sys.exit(1)

    posts["posted_at"] = pd.to_datetime(posts["posted_at"], utc=True, errors="coerce")
    since = pd.Timestamp(args.since, tz="UTC")
    posts = posts[posts["posted_at"] >= since]
    if args.until:
        until = pd.Timestamp(args.until, tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        posts = posts[posts["posted_at"] <= until]

    roster = _fetch_campaign_roster(config, client, [cid])
    out = posts_to_export_df(posts, roster)
    out = out.sort_values("Post Date")
    out = out.fillna("")

    path = Path(args.output).expanduser().resolve()
    out.to_csv(path, index=False)
    print(f"Wrote {len(out):,} rows → {path}")
    if not out.empty:
        print(f"  Date range: {out['Post Date'].min()} → {out['Post Date'].max()}")


if __name__ == "__main__":
    main()
