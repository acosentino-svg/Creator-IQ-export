#!/usr/bin/env python3
"""
Fetch a CreatorIQ async "view" report (Reports/*) in large chunks, filter
each chunk down to a known set of creator IDs as it arrives, and write the
filtered rows to a JSONL file (one JSON object per line).

These reports are backed by an async task queue: a GET request returns a
TaskId immediately (TaskStatus=CREATED), and the *same* request must be
re-issued to poll status (CREATED -> PROCESSING -> DONE); when DONE, the
result JSON is at Result.Headers.Location (a pre-signed S3 URL).

Empirically, processing time is roughly constant (~45-90s) up to a few
hundred thousand rows per request, then stalls/hangs for much larger
`take` values (e.g. 1,000,000+ rows never completed in testing). So this
fetches the full report in fixed-size chunks via `skip`/`take`, which
keeps each individual request in the reliable range.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://apis.creatoriq.com/crm/v1/api/view"


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def request_task(view, take, skip, api_key, extra_params=None):
    params = [
        ("view", view),
        ("requestData[take]", take),
        ("requestData[skip]", skip),
    ]
    if extra_params:
        params.extend(extra_params)
    url = BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"x-api-key": api_key, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def poll_until_done(view, take, skip, api_key, extra_params=None, max_wait_s=600, poll_interval_s=20):
    t0 = time.time()
    while True:
        data = request_task(view, take, skip, api_key, extra_params)
        status = data.get("TaskStatus")
        if status == "DONE":
            return data
        if time.time() - t0 > max_wait_s:
            return data  # give up, caller decides what to do
        time.sleep(poll_interval_s)


def fetch_result_json(task_data):
    loc = task_data.get("Result", {}).get("Headers", {}).get("Location")
    if not loc:
        return None
    req = urllib.request.Request(loc)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--view", required=True, help="e.g. Reports/DailyCampaignPosts")
    ap.add_argument("--chunk-size", type=int, default=300000)
    ap.add_argument("--total", type=int, required=True, help="Total row count to fetch (from the report's `count` field)")
    ap.add_argument("--id-field", default="creatorid", help="Field in each row holding the creator/publisher id")
    ap.add_argument("--keep-ids-file", required=True, help="Text file, one creator id per line, to filter rows down to")
    ap.add_argument("--out", required=True, help="Output JSONL path for matching rows")
    ap.add_argument("--api-key-env", default="CREATORIQ_API_KEY")
    ap.add_argument("--max-wait-s", type=int, default=420)
    ap.add_argument("--poll-interval-s", type=float, default=20)
    ap.add_argument("--start-skip", type=int, default=0)
    args = ap.parse_args()

    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        raise SystemExit(f"{args.api_key_env} not set")

    with open(args.keep_ids_file) as f:
        keep_ids = set(line.strip() for line in f if line.strip())
    log(f"Filtering to {len(keep_ids)} creator ids")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    out_f = open(args.out, "a")

    total_matched = 0
    total_scanned = 0
    skip = args.start_skip
    while skip < args.total:
        take = min(args.chunk_size, args.total - skip)
        log(f"Requesting {args.view} skip={skip} take={take} ...")
        task = poll_until_done(args.view, take, skip, api_key,
                                max_wait_s=args.max_wait_s, poll_interval_s=args.poll_interval_s)
        if task.get("TaskStatus") != "DONE":
            log(f"  WARNING: task not done after max wait (status={task.get('TaskStatus')}); skipping this chunk, will need retry: skip={skip}")
            skip += args.chunk_size
            continue
        result = fetch_result_json(task)
        rows = result.get("results", []) if result else []
        matched = 0
        for row in rows:
            rid = row.get(args.id_field)
            if rid is not None and str(rid) in keep_ids:
                out_f.write(json.dumps(row) + "\n")
                matched += 1
        out_f.flush()
        total_matched += matched
        total_scanned += len(rows)
        log(f"  chunk done: scanned={len(rows)} matched={matched} (running totals: scanned={total_scanned} matched={total_matched})")
        skip += args.chunk_size

    out_f.close()
    log(f"DONE. Total scanned={total_scanned} matched={total_matched}. Output: {args.out}")


if __name__ == "__main__":
    main()
