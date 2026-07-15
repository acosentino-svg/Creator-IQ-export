#!/usr/bin/env python3
"""
Build the per-creator activation report columns we can derive from
Reports/DailyCampaignPosts (posts) and Reports/CreatorPaymentsReport
(payments), for the Crm Adriana / Status=Active creator set.

DailyCampaignPosts is a *daily snapshot* fact table: each row is one
(post, day-pulled) combination, so the same post appears many times. We
de-duplicate by `postid` per creator (postdate is constant across a
post's snapshot rows) before computing last-post-date / per-window counts.
"""

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, date

TODAY = date.today()
WINDOW_1 = (date(2025, 9, 1), date(2026, 1, 1))   # Sep 1 2025 - Jan 1 2026 (exclusive end)
WINDOW_2 = (date(2026, 1, 1), TODAY)               # Jan 1 2026 - today


def parse_date(s):
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.split(".")[0] if "." in s and fmt == "%Y-%m-%d" else s, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def in_window(d, window):
    if d is None:
        return False
    dd = d.date()
    return window[0] <= dd < window[1]


def load_creator_ids(path):
    with open(path) as f:
        return {line.strip() for line in f if line.strip()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--posts-jsonl", required=True)
    ap.add_argument("--creators-csv", required=True, help="output/creatoriq_active_members_crm_adriana.csv")
    ap.add_argument("--out-csv", required=True)
    ap.add_argument("--verified-ids-file", default=None,
                     help="Optional: text file of creator ids for which --posts-jsonl has *complete* "
                          "coverage (came from a full unfiltered scan). Creators not in this set get "
                          "DataStatus=Pending instead of a confirmed zero-post count.")
    args = ap.parse_args()

    creators = []
    with open(args.creators_csv) as f:
        r = csv.DictReader(f)
        for row in r:
            creators.append(row)
    print(f"Loaded {len(creators)} creators")

    posts_by_creator = defaultdict(dict)  # creator_id (str) -> {postid: postdate}
    with open(args.posts_jsonl) as f:
        for line in f:
            row = json.loads(line)
            cid = str(row["creatorid"])
            postid = row.get("postid")
            pdate = parse_date(row.get("postdate"))
            if postid is None or pdate is None:
                continue
            existing = posts_by_creator[cid].get(postid)
            if existing is None or pdate > existing:
                posts_by_creator[cid][postid] = pdate

    n_with_posts = sum(1 for v in posts_by_creator.values() if v)
    print(f"Creators with >=1 distinct post: {n_with_posts}")

    verified_ids = load_creator_ids(args.verified_ids_file) if args.verified_ids_file else None

    out_fields = [
        "Id", "PublisherId", "PublisherName", "Status",
        "LastPostDate", "TimeSinceLastPost_Days",
        "PostsCount_Sep2025_Jan2026", "PostsCount_Jan2026_Today",
        "TotalDistinctPostsTracked", "DataStatus",
    ]
    n_pending = 0
    with open(args.out_csv, "w", newline="") as out_f:
        w = csv.DictWriter(out_f, fieldnames=out_fields)
        w.writeheader()
        for c in creators:
            cid = c["Id"]
            is_verified = verified_ids is None or cid in verified_ids
            post_dates = list(posts_by_creator.get(cid, {}).values())
            last_post = max(post_dates) if post_dates else None
            w1_count = sum(1 for d in post_dates if in_window(d, WINDOW_1))
            w2_count = sum(1 for d in post_dates if in_window(d, WINDOW_2))
            days_since = (TODAY - last_post.date()).days if last_post else ""
            if not is_verified:
                n_pending += 1
            w.writerow({
                "Id": cid,
                "PublisherId": c.get("PublisherId"),
                "PublisherName": c.get("PublisherName"),
                "Status": c.get("Status"),
                "LastPostDate": last_post.strftime("%Y-%m-%d") if last_post else ("" if is_verified else "Pending"),
                "TimeSinceLastPost_Days": days_since if is_verified else "",
                "PostsCount_Sep2025_Jan2026": w1_count if is_verified else "",
                "PostsCount_Jan2026_Today": w2_count if is_verified else "",
                "TotalDistinctPostsTracked": len(post_dates) if is_verified else "",
                "DataStatus": "Verified" if is_verified else "Pending",
            })
    print(f"Wrote {args.out_csv} ({n_pending} rows marked Pending)")


if __name__ == "__main__":
    main()
