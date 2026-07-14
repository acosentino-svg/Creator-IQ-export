#!/usr/bin/env python3
"""
CreatorIQ large-report exporter.

Works around the CreatorIQ UI's ~20k row export cap by pulling a report
(e.g. the "Active Members" report / publisher list) straight from the
CreatorIQ API, page by page, until every row has been retrieved -- then
flattens the results into a single CSV.

Usage overview
--------------
1. `probe`   - fetch one page and print the raw JSON shape, so you can
               confirm --data-path / --total-path / --id-field before
               committing to a full pull.
2. `fetch`   - paginate through the *entire* result set and write every
               record to a local .jsonl file (one JSON object per line).
               Safe to Ctrl-C and re-run: it resumes from a checkpoint
               file instead of starting over or double-counting rows.
3. `to-csv`  - flatten the .jsonl file into a single, Excel/Sheets-ready
               CSV with a unioned header.
4. `run`     - convenience wrapper that does fetch + to-csv in one shot.

Nothing here is CreatorIQ-account-specific except the endpoint URL and
query parameters you pass in on the command line -- see README.md for
how to find the right values for your CreatorIQ instance.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Iterator

import requests

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


DEFAULT_TIMEOUT = 30
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def dig(obj: Any, dotted_path: str) -> Any:
    """Walk a dotted path (e.g. 'data.publishers') into nested dict/list JSON."""
    if not dotted_path:
        return obj
    current = obj
    for key in dotted_path.split("."):
        if current is None:
            return None
        if isinstance(current, list):
            current = current[int(key)] if key.isdigit() else None
        elif isinstance(current, dict):
            current = current.get(key)
        else:
            return None
    return current


def flatten(obj: Any, prefix: str = "") -> dict:
    """Flatten a nested dict into dot-notation columns; lists become JSON strings."""
    out: dict = {}
    if isinstance(obj, dict):
        if not obj:
            out[prefix or "value"] = ""
            return out
        for k, v in obj.items():
            new_key = f"{prefix}.{k}" if prefix else str(k)
            out.update(flatten(v, new_key))
    elif isinstance(obj, list):
        out[prefix or "value"] = json.dumps(obj, ensure_ascii=False)
    else:
        out[prefix or "value"] = obj
    return out


def build_session(api_key: str, auth_style: str, header_name: str) -> requests.Session:
    session = requests.Session()
    if auth_style == "bearer":
        session.headers["Authorization"] = f"Bearer {api_key}"
    elif auth_style == "apikey-header":
        session.headers[header_name] = api_key
    # "query" style handled per-request in fetch_page()
    session.headers["Accept"] = "application/json"
    return session


def request_with_retry(
    session: requests.Session,
    method: str,
    url: str,
    params: dict,
    max_retries: int,
    base_sleep: float,
) -> requests.Response:
    attempt = 0
    while True:
        attempt += 1
        try:
            resp = session.request(method, url, params=params, timeout=DEFAULT_TIMEOUT)
        except requests.RequestException as exc:
            if attempt > max_retries:
                raise
            wait = base_sleep * (2 ** (attempt - 1))
            print(f"  [retry] network error ({exc}); sleeping {wait:.1f}s", file=sys.stderr)
            time.sleep(wait)
            continue

        if resp.status_code in RETRYABLE_STATUS:
            if attempt > max_retries:
                resp.raise_for_status()
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else base_sleep * (2 ** (attempt - 1))
            print(
                f"  [retry] HTTP {resp.status_code} on attempt {attempt}; "
                f"sleeping {wait:.1f}s",
                file=sys.stderr,
            )
            time.sleep(wait)
            continue

        resp.raise_for_status()
        return resp


# --------------------------------------------------------------------------
# Core pagination
# --------------------------------------------------------------------------
def paginate(
    session: requests.Session,
    endpoint: str,
    static_params: dict,
    pagination_style: str,
    limit_param: str,
    offset_param: str,
    page_param: str,
    page_size: int,
    start_offset: int,
    start_page: int,
    data_path: str,
    total_path: str,
    max_records: int | None,
    max_retries: int,
    sleep_between: float,
    auth_style: str,
    api_key: str,
    apikey_query_param: str,
) -> Iterator[tuple[list[dict], int, int, int | None, int]]:
    """Yields (records, offset_used, page_used, total_if_known, fetched_so_far) per page."""
    fetched = 0
    total: int | None = None
    offset = start_offset
    page = start_page

    while True:
        params = dict(static_params)
        if pagination_style == "offset":
            params[limit_param] = page_size
            params[offset_param] = offset
        elif pagination_style == "page":
            params[page_param] = page
            params[limit_param] = page_size
        else:
            raise ValueError(f"Unknown pagination style: {pagination_style}")

        if auth_style == "query":
            params[apikey_query_param] = api_key

        resp = request_with_retry(session, "GET", endpoint, params, max_retries, sleep_between or 1.0)
        payload = resp.json()

        records = dig(payload, data_path)
        if records is None:
            records = []
        if not isinstance(records, list):
            raise ValueError(
                f"--data-path '{data_path}' did not resolve to a list "
                f"(got {type(records).__name__}). Run the 'probe' command "
                f"to inspect the response shape."
            )

        if total is None and total_path:
            maybe_total = dig(payload, total_path)
            if isinstance(maybe_total, int):
                total = maybe_total

        fetched += len(records)
        yield records, offset, page, total, fetched

        if not records:
            break
        if max_records and fetched >= max_records:
            break
        if total is not None and fetched >= total:
            break
        if len(records) < page_size and pagination_style in ("offset", "page"):
            # Short page almost always means we've hit the end.
            break

        offset += page_size
        page += 1
        if sleep_between:
            time.sleep(sleep_between)


# --------------------------------------------------------------------------
# Subcommands
# --------------------------------------------------------------------------
def cmd_probe(args: argparse.Namespace) -> None:
    api_key = require_api_key(args)
    session = build_session(api_key, args.auth_style, args.header_name)
    static_params = json.loads(args.params) if args.params else {}

    params = dict(static_params)
    if args.pagination_style == "offset":
        params[args.limit_param] = args.page_size
        params[args.offset_param] = args.start_offset
    else:
        params[args.page_param] = args.start_page
        params[args.limit_param] = args.page_size
    if args.auth_style == "query":
        params[args.apikey_query_param] = api_key

    resp = request_with_retry(session, "GET", args.endpoint, params, args.max_retries, args.sleep)
    payload = resp.json()

    print("=== Top-level response keys ===")
    if isinstance(payload, dict):
        print(list(payload.keys()))
    else:
        print(f"(response is a {type(payload).__name__}, not an object)")

    records = dig(payload, args.data_path)
    print(f"\n=== dig(payload, '{args.data_path}') -> {type(records).__name__} ===")
    if isinstance(records, list):
        print(f"{len(records)} record(s) on this page")
        if records:
            print("\n=== First record keys ===")
            print(list(records[0].keys()) if isinstance(records[0], dict) else records[0])
            print("\n=== First record (pretty) ===")
            print(json.dumps(records[0], indent=2, ensure_ascii=False)[:3000])
    else:
        print("Not a list -- adjust --data-path. Full payload (truncated):")
        print(json.dumps(payload, indent=2, ensure_ascii=False)[:3000])

    if args.total_path:
        total = dig(payload, args.total_path)
        print(f"\n=== dig(payload, '{args.total_path}') -> {total!r} ===")

    print(
        "\nRaw response saved to probe_response.json for full inspection."
    )
    Path("probe_response.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False))


def load_checkpoint(checkpoint_file: Path) -> dict:
    if checkpoint_file.exists():
        return json.loads(checkpoint_file.read_text())
    return {"offset": 0, "page": 1, "fetched": 0, "seen_ids": []}


def save_checkpoint(checkpoint_file: Path, state: dict) -> None:
    checkpoint_file.write_text(json.dumps(state))


def cmd_fetch(args: argparse.Namespace) -> None:
    api_key = require_api_key(args)
    session = build_session(api_key, args.auth_style, args.header_name)
    static_params = json.loads(args.params) if args.params else {}

    out_path = Path(args.output)
    checkpoint_path = Path(args.checkpoint_file or (str(out_path) + ".checkpoint.json"))

    seen_ids: set[str] = set()
    start_offset = args.start_offset
    start_page = args.start_page
    fetched_before = 0

    if args.resume and checkpoint_path.exists():
        state = load_checkpoint(checkpoint_path)
        start_offset = state.get("offset", start_offset)
        start_page = state.get("page", start_page)
        fetched_before = state.get("fetched", 0)
        seen_ids = set(state.get("seen_ids_sample", []))
        print(
            f"Resuming from checkpoint: offset={start_offset} page={start_page} "
            f"(already fetched ~{fetched_before} records into {out_path})"
        )
        write_mode = "a"
    else:
        write_mode = "w"
        if out_path.exists() and not args.resume:
            print(f"Overwriting existing {out_path} (pass --resume to continue instead).")

    id_field = args.id_field
    new_dupes = 0
    total_written = fetched_before

    with out_path.open(write_mode, encoding="utf-8") as fh:
        for records, offset_used, page_used, total, _fetched_so_far in paginate(
            session=session,
            endpoint=args.endpoint,
            static_params=static_params,
            pagination_style=args.pagination_style,
            limit_param=args.limit_param,
            offset_param=args.offset_param,
            page_param=args.page_param,
            page_size=args.page_size,
            start_offset=start_offset,
            start_page=start_page,
            data_path=args.data_path,
            total_path=args.total_path,
            max_records=args.max_records,
            max_retries=args.max_retries,
            sleep_between=args.sleep,
            auth_style=args.auth_style,
            api_key=api_key,
            apikey_query_param=args.apikey_query_param,
        ):
            for rec in records:
                rec_id = str(rec.get(id_field)) if isinstance(rec, dict) and id_field else None
                if rec_id is not None:
                    if rec_id in seen_ids:
                        new_dupes += 1
                        continue
                    seen_ids.add(rec_id)
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                total_written += 1
            fh.flush()

            total_str = f"/{total}" if total is not None else ""
            print(f"  page offset={offset_used} page={page_used}: "
                  f"+{len(records)} records ({total_written}{total_str} total so far)")

            # Checkpoint points to the *next* page to fetch, so a resumed run
            # never re-requests a page it already wrote to disk.
            save_checkpoint(
                checkpoint_path,
                {
                    "offset": offset_used + args.page_size,
                    "page": page_used + 1,
                    "fetched": total_written,
                    "seen_ids_sample": list(seen_ids)[-5000:],
                },
            )

    print(f"\nDone. Wrote {total_written} unique records to {out_path}")
    if new_dupes:
        print(f"Skipped {new_dupes} duplicate record(s) detected by --id-field '{id_field}'.")
    print(f"Checkpoint saved at {checkpoint_path} (safe to delete once you've verified the export).")


def cmd_to_csv(args: argparse.Namespace) -> None:
    in_path = Path(args.input)
    out_path = Path(args.output)

    rows: list[dict] = []
    with in_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            rows.append(flatten(rec))

    if not rows:
        print("No records found in input file -- nothing to write.")
        return

    fieldnames: list[str] = []
    seen = set()
    priority = [c.strip() for c in (args.priority_columns.split(",") if args.priority_columns else []) if c.strip()]
    for col in priority:
        if col not in seen:
            fieldnames.append(col)
            seen.add(col)
    for row in rows:
        for key in row.keys():
            if key not in seen:
                fieldnames.append(key)
                seen.add(key)

    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, restval="", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"Wrote {len(rows)} rows x {len(fieldnames)} columns to {out_path}")


def cmd_run(args: argparse.Namespace) -> None:
    cmd_fetch(args)
    to_csv_args = argparse.Namespace(
        input=args.output,
        output=args.csv_output,
        priority_columns=args.priority_columns,
    )
    cmd_to_csv(to_csv_args)


def require_api_key(args: argparse.Namespace) -> str:
    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        print(
            f"ERROR: environment variable {args.api_key_env} is not set.\n"
            f"Set it in a .env file (see .env.example) or export it before running, e.g.\n"
            f"  export {args.api_key_env}=your-real-key",
            file=sys.stderr,
        )
        sys.exit(1)
    return api_key


# --------------------------------------------------------------------------
# CLI wiring
# --------------------------------------------------------------------------
def add_common_fetch_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--endpoint", required=True, help="Full CreatorIQ API URL to page through.")
    p.add_argument("--params", default=None, help='JSON string of static query params/filters, e.g. \'{"list_id": 12345}\'')
    p.add_argument("--api-key-env", default="CREATORIQ_API_KEY", help="Env var holding the API key.")
    p.add_argument("--auth-style", choices=["bearer", "apikey-header", "query"], default="bearer")
    p.add_argument("--header-name", default="X-API-Key", help="Header name when --auth-style=apikey-header.")
    p.add_argument("--apikey-query-param", default="apiKey", help="Query param name when --auth-style=query.")
    p.add_argument("--pagination-style", choices=["offset", "page"], default="offset")
    p.add_argument("--limit-param", default="limit")
    p.add_argument("--offset-param", default="offset")
    p.add_argument("--page-param", default="page")
    p.add_argument("--page-size", type=int, default=500)
    p.add_argument("--start-offset", type=int, default=0)
    p.add_argument("--start-page", type=int, default=1)
    p.add_argument("--data-path", default="data", help="Dotted path to the records list inside the JSON response.")
    p.add_argument("--total-path", default=None, help="Optional dotted path to a total-record-count field.")
    p.add_argument("--max-records", type=int, default=None, help="Safety cap on total records to fetch.")
    p.add_argument("--max-retries", type=int, default=5)
    p.add_argument("--sleep", type=float, default=0.3, help="Seconds to sleep between page requests.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_probe = sub.add_parser("probe", help="Fetch one page and print the response shape.")
    add_common_fetch_args(p_probe)
    p_probe.set_defaults(func=cmd_probe)

    p_fetch = sub.add_parser("fetch", help="Paginate through the full result set into a .jsonl file.")
    add_common_fetch_args(p_fetch)
    p_fetch.add_argument("--output", required=True, help="Path to .jsonl output file.")
    p_fetch.add_argument("--checkpoint-file", default=None)
    p_fetch.add_argument("--id-field", default="id", help="Field used to de-dup records across pages.")
    p_fetch.add_argument("--resume", action="store_true", help="Resume from the checkpoint file instead of starting over.")
    p_fetch.set_defaults(func=cmd_fetch)

    p_csv = sub.add_parser("to-csv", help="Flatten a .jsonl file into a single CSV.")
    p_csv.add_argument("--input", required=True, help="Path to .jsonl file produced by 'fetch'.")
    p_csv.add_argument("--output", required=True, help="Path to write the final CSV.")
    p_csv.add_argument("--priority-columns", default="id,name,email,status", help="Comma-separated columns to put first, if present.")
    p_csv.set_defaults(func=cmd_to_csv)

    p_run = sub.add_parser("run", help="fetch + to-csv in one step.")
    add_common_fetch_args(p_run)
    p_run.add_argument("--output", required=True, help="Path to intermediate .jsonl file.")
    p_run.add_argument("--csv-output", required=True, help="Path to final CSV file.")
    p_run.add_argument("--checkpoint-file", default=None)
    p_run.add_argument("--id-field", default="id")
    p_run.add_argument("--resume", action="store_true")
    p_run.add_argument("--priority-columns", default="id,name,email,status")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
