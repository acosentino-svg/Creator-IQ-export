#!/usr/bin/env python3
"""
Generic paginated REST -> CSV export tool, built for the CreatorIQ CRM API
but written to work against any JSON REST API that:

  - paginates with page/size style query params
  - returns a list of records at some JSON path (--data-path)
  - reports a grand total at some JSON path (--total-path)
  - authenticates via a single request header carrying an API key

Two subcommands:

  probe   Fetch a small unfiltered sample and report the grand total plus,
          for a chosen field, the exact record count for each candidate
          value (via server-side filter=field=value requests with size=1,
          which is cheap because it only needs the "total" from each call).

  export  Page through the (optionally filtered) collection end-to-end and
          stream the results to a CSV file.

Example (CreatorIQ CRM Publishers):

  export CREATORIQ_API_KEY=...

  python3 creatoriq_export.py probe \
      --endpoint https://apis.creatoriq.com/crm/v1/api/publishers \
      --auth-header x-api-key --api-key-env CREATORIQ_API_KEY \
      --data-path PublisherCollection --total-path total \
      --field Status

  python3 creatoriq_export.py export \
      --endpoint https://apis.creatoriq.com/crm/v1/api/publishers \
      --auth-header x-api-key --api-key-env CREATORIQ_API_KEY \
      --data-path PublisherCollection --total-path total \
      --filter Status=Active \
      --out output/active_members.csv
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, OrderedDict


def log(*args):
    print(*args, file=sys.stderr, flush=True)


def get_json_path(obj, path):
    """Resolve a dotted path like 'a.b.c' against a JSON object."""
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def unwrap_record(item):
    """
    CreatorIQ (and many HAL-ish APIs) wrap each collection item as:
        {"type": "Publisher", "href": "...", "Publisher": {...fields...}}
    Unwrap to the inner fields dict when that shape is detected, otherwise
    return the item unchanged.
    """
    if isinstance(item, dict):
        t = item.get("type")
        if t and isinstance(item.get(t), dict):
            return item[t]
    return item


class ApiClient:
    def __init__(self, endpoint, auth_header, api_key, page_param, size_param,
                 max_size, data_path, total_path, extra_params=None,
                 max_retries=8, base_delay=1.0, min_interval=0.0):
        self.endpoint = endpoint
        self.auth_header = auth_header
        self.api_key = api_key
        self.page_param = page_param
        self.size_param = size_param
        self.max_size = max_size
        self.data_path = data_path
        self.total_path = total_path
        self.extra_params = extra_params or {}
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.min_interval = min_interval
        self._last_request_ts = 0.0

    def _throttle(self):
        if self.min_interval <= 0:
            return
        elapsed = time.time() - self._last_request_ts
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

    def request(self, params):
        # params is a list of (key, value) tuples; duplicate keys (e.g.
        # repeated `filter` params for AND conditions) are preserved.
        query = list(self.extra_params.items()) + list(params)
        url = self.endpoint + "?" + urllib.parse.urlencode(query)
        headers = {self.auth_header: self.api_key, "Accept": "application/json"}
        req = urllib.request.Request(url, headers=headers)

        delay = self.base_delay
        last_err = None
        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            try:
                self._last_request_ts = time.time()
                with urllib.request.urlopen(req, timeout=60) as resp:
                    body = resp.read()
                return json.loads(body)
            except urllib.error.HTTPError as e:
                body = e.read()
                last_err = e
                if e.code == 429 or 500 <= e.code < 600:
                    retry_after = e.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after else delay
                    log(f"  [retry] HTTP {e.code} on attempt {attempt}, "
                        f"waiting {wait:.1f}s")
                    time.sleep(wait)
                    delay = min(delay * 2, 30)
                    continue
                log(f"  [error] HTTP {e.code}: {body[:500]!r}")
                raise
            except (urllib.error.URLError, TimeoutError) as e:
                last_err = e
                log(f"  [retry] network error on attempt {attempt}: {e}, "
                    f"waiting {delay:.1f}s")
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue
        raise RuntimeError(f"request failed after {self.max_retries} attempts: {last_err}")

    def fetch_page(self, page, size, filters=None, fields=None):
        params = [(self.page_param, page), (self.size_param, size)]
        if fields:
            params.append(("fields", ",".join(fields)))
        if filters:
            # The API accepts one `filter` query param per condition, shaped
            # as "Field=Value" (it echoes this back internally as a
            # filter[i][0..2] field/operator/value triple in the `href` it
            # returns, but the wire format we must *send* is the plain
            # "Field=Value" string). Repeat the `filter` key to AND multiple
            # conditions together.
            for field, value in filters:
                params.append(("filter", f"{field}={value}"))
        data = self.request(params)
        total = get_json_path(data, self.total_path)
        records = get_json_path(data, self.data_path) or []
        return total, records


def parse_filters(filter_args):
    filters = []
    for f in filter_args or []:
        if "=" not in f:
            raise ValueError(f"invalid --filter '{f}', expected field=value")
        field, value = f.split("=", 1)
        filters.append((field, value))
    return filters


def build_client(args):
    api_key = os.environ.get(args.api_key_env)
    if not api_key:
        raise SystemExit(f"Environment variable {args.api_key_env} is not set")
    return ApiClient(
        endpoint=args.endpoint,
        auth_header=args.auth_header,
        api_key=api_key,
        page_param=args.page_param,
        size_param=args.size_param,
        max_size=args.max_size,
        data_path=args.data_path,
        total_path=args.total_path,
        min_interval=args.min_interval,
    )


def cmd_probe(args):
    client = build_client(args)
    sample_size = min(args.sample_size, args.max_size)
    total, records = client.fetch_page(1, sample_size)
    log(f"Grand total (unfiltered): {total}")
    log(f"Sample size fetched: {len(records)}")

    unwrapped = [unwrap_record(r) for r in records]

    if unwrapped:
        keys = list(unwrapped[0].keys()) if isinstance(unwrapped[0], dict) else []
        log(f"Record has {len(keys)} fields, e.g.: {', '.join(keys[:20])}"
            + (" ..." if len(keys) > 20 else ""))

    if args.field:
        counts = Counter()
        for r in unwrapped:
            if isinstance(r, dict):
                counts[r.get(args.field)] += 1
        log(f"\nSample distribution of field '{args.field}' "
            f"(out of {len(unwrapped)} sampled records):")
        for value, count in counts.most_common():
            log(f"  {value!r}: {count}")

        candidates = args.candidate_values or [v for v in counts if v is not None]
        if candidates:
            log(f"\nAuthoritative server-side counts for field '{args.field}' "
                f"(via filter={args.field}=<value>, size=1 total lookup):")
            grand_total_check = 0
            results = OrderedDict()
            for value in candidates:
                exact_total, _ = client.fetch_page(
                    1, 1, filters=[(args.field, value)]
                )
                results[value] = exact_total
                grand_total_check += exact_total or 0
                log(f"  {args.field}={value!r}: {exact_total}")
            log(f"\nSum of authoritative counts above: {grand_total_check} "
                f"(grand total unfiltered: {total})")
            if args.probe_output:
                with open(args.probe_output, "w") as f:
                    json.dump({"grand_total": total, "field": args.field,
                               "counts": results}, f, indent=2)
                log(f"Wrote probe results to {args.probe_output}")


def cmd_export(args):
    client = build_client(args)
    filters = parse_filters(args.filter)
    fields = args.fields.split(",") if args.fields else None

    size = args.max_size
    total, first_records = client.fetch_page(1, size, filters=filters, fields=fields)
    if total is None:
        raise SystemExit("Could not resolve total from response; check --total-path")
    pages = (total + size - 1) // size
    log(f"Filter: {filters or 'none'}")
    log(f"Matching total: {total} across {pages} pages of size {size}")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)

    writer = None
    csv_file = open(args.out, "w", newline="", encoding="utf-8")
    written = 0

    def write_records(records):
        nonlocal writer, written
        for item in records:
            row = unwrap_record(item)
            if not isinstance(row, dict):
                continue
            if writer is None:
                fieldnames = fields if fields else list(row.keys())
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
            writer.writerow(row)
            written += 1

    try:
        write_records(first_records)
        t0 = time.time()
        for page in range(2, pages + 1):
            _, records = client.fetch_page(page, size, filters=filters, fields=fields)
            write_records(records)
            if page % args.log_every == 0 or page == pages:
                elapsed = time.time() - t0
                rate = written / elapsed if elapsed > 0 else 0
                log(f"  page {page}/{pages} | rows written: {written}/{total} "
                    f"| elapsed {elapsed:.0f}s | {rate:.0f} rows/s")
    finally:
        csv_file.close()

    log(f"\nDone. Wrote {written} rows to {args.out}")


def add_common_args(p):
    p.add_argument("--endpoint", required=True, help="Full collection URL, e.g. https://apis.creatoriq.com/crm/v1/api/publishers")
    p.add_argument("--auth-header", default="x-api-key", help="HTTP header name used to send the API key")
    p.add_argument("--api-key-env", default="CREATORIQ_API_KEY", help="Env var holding the API key")
    p.add_argument("--page-param", default="page")
    p.add_argument("--size-param", default="size")
    p.add_argument("--max-size", type=int, default=1000)
    p.add_argument("--data-path", default="PublisherCollection", help="Dotted JSON path to the list of records in each page")
    p.add_argument("--total-path", default="total", help="Dotted JSON path to the grand total count")
    p.add_argument("--min-interval", type=float, default=0.0, help="Minimum seconds between requests (client-side throttle)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_probe = sub.add_parser("probe", help="Unfiltered sample + authoritative per-value counts for a field")
    add_common_args(p_probe)
    p_probe.add_argument("--sample-size", type=int, default=1000)
    p_probe.add_argument("--field", default=None, help="Field to profile, e.g. Status")
    p_probe.add_argument("--candidate-values", nargs="*", default=None,
                          help="Explicit values to test counts for; default is every distinct value seen in the sample")
    p_probe.add_argument("--probe-output", default=None, help="Optional path to write probe results JSON")
    p_probe.set_defaults(func=cmd_probe)

    p_export = sub.add_parser("export", help="Full paginated fetch (optionally filtered) to CSV")
    add_common_args(p_export)
    p_export.add_argument("--filter", action="append", default=[], help="field=value; repeatable for AND filters")
    p_export.add_argument("--fields", default=None, help="Comma-separated list of fields to request/write (server-side projection if supported)")
    p_export.add_argument("--out", required=True, help="Output CSV path")
    p_export.add_argument("--log-every", type=int, default=25)
    p_export.set_defaults(func=cmd_export)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
