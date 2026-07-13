# Creator-IQ-export

Export large CreatorIQ reports (e.g. the **Active Members** report) straight
from the CreatorIQ API, bypassing the CreatorIQ UI's ~20,000-row export cap.

The included script (`creatoriq_export.py`) pages through the *entire*
result set — 69,000 rows or any other size — writes every record to a local
file as it goes (so a network hiccup never loses progress), and then
flattens everything into one CSV you can open in Excel/Sheets.

## Why this works

The 20k limit you're hitting is a limit on the **UI's "Export" button**, not
on the underlying data. The CreatorIQ REST API returns results a page at a
time (e.g. 100–1000 records per request, depending on the endpoint), and you
just keep asking for the next page until there's nothing left — there's no
69k (or 690k) ceiling on that. This script automates the "keep asking for
the next page" part, plus retries, rate-limit backoff, resuming after a
crash, and de-duplication.

## 0. Prerequisites

```bash
python3 -m pip install -r requirements.txt
cp .env.example .env
# then edit .env and paste your real CreatorIQ API key into CREATORIQ_API_KEY
```

`creatoriq_export.py` reads the key from the `CREATORIQ_API_KEY` environment
variable (via `.env`), so it's never typed on the command line or committed
to git. `.env` is already in `.gitignore`.

## 1. Find the exact endpoint & filters for "Active Members"

CreatorIQ's API docs (apidocs.creatoriq.com) are behind a login and are
account/contract-specific, so the exact endpoint path and query params for
your instance aren't something a script can guess. Here's the fastest way to
find them — takes about five minutes:

1. Open the **Active Members** report in the CreatorIQ web app, with your
   browser's DevTools open (F12 → **Network** tab, filter to `Fetch/XHR`).
2. Reload the report (or click into it). Look for the request the page
   makes to load the table data — it'll be a `GET` (occasionally `POST`) to
   something under `apis.creatoriq.com/...` (most commonly the **Publishers**
   or **CRM Publishers** endpoint, or a **Reports** endpoint if it's a
   custom saved report).
3. Click that request and note down:
   - **Full URL** (path + query string) → this is your `--endpoint` and
     `--params`.
   - Any **filter/list ID** in the query string or request body (e.g.
     `list_id`, `status=active`, `segment_id`) — "Active Members" is
     typically either a saved **List** in CreatorIQ CRM or a status filter
     on the Publishers endpoint. Copy whatever uniquely identifies it.
   - The **pagination params** it sends (commonly `limit`/`offset`, or
     `page`/`per_page`).
   - Response shape: which key holds the array of records (commonly `data`,
     `results`, or `publishers`) and whether there's a total-count field
     (commonly under `meta.total`, `pagination.total`, or similar).
4. Right-click that request → **Copy as cURL**, and swap the browser's
   session cookie/bearer token for your API key when testing with the
   script (the API key auth is normally `Authorization: Bearer <key>`, but
   confirm — some CreatorIQ endpoints use an `X-API-Key` header or an
   `apiKey` query param instead).

If you'd rather not reverse-engineer it from the browser, your CreatorIQ
CSM/support contact can tell you directly which endpoint backs "Active
Members" and its exact filter for your account — that's a one-line question
for them and avoids any guesswork.

### Sanity-check with `probe` before pulling everything

Once you have a candidate endpoint + params, run `probe` — it fetches **one
page only** and prints the response structure, so you can confirm/adjust
`--data-path`, `--total-path`, and auth *before* committing to a 69k-record
pull:

```bash
python3 creatoriq_export.py probe \
  --endpoint "https://apis.creatoriq.com/crm/v2/publishers" \
  --params '{"list_id": 123456, "status": "active"}' \
  --auth-style bearer \
  --data-path data \
  --total-path meta.total \
  --page-size 5
```

It prints the top-level JSON keys, the first record's keys/contents, and
also saves the full raw response to `probe_response.json` for closer
inspection. Adjust `--data-path` / `--total-path` / `--auth-style` until the
printed record count and total look right (in your case, total should read
~69000).

## 2. Pull everything

Once `probe` looks right, run `fetch` with the same flags, dropping
`--page-size 5` down to something larger (500–1000, whatever the endpoint's
max is) so it finishes in dozens of requests instead of thousands:

```bash
python3 creatoriq_export.py fetch \
  --endpoint "https://apis.creatoriq.com/crm/v2/publishers" \
  --params '{"list_id": 123456, "status": "active"}' \
  --auth-style bearer \
  --data-path data \
  --total-path meta.total \
  --id-field id \
  --page-size 500 \
  --sleep 0.3 \
  --output exports/active_members.jsonl
```

This writes one JSON object per line to `exports/active_members.jsonl` as
each page comes in, and prints running progress (`fetched X/69000...`).

- **If it gets rate-limited (HTTP 429)** or hits a transient network/5xx
  error, it automatically backs off and retries (honoring `Retry-After` if
  the API sends one) — you don't need to do anything.
- **If it crashes or you Ctrl-C it partway through**, just re-run the exact
  same command with `--resume` appended. It picks up from the last
  successful page using a small checkpoint file
  (`exports/active_members.jsonl.checkpoint.json`) instead of starting over
  or double-counting rows. `--id-field` (default `id`) is used to silently
  skip any record it's already written, as a second safety net against
  duplicates if pages ever overlap.
- Use `--max-records` while testing (e.g. `--max-records 100`) to do a
  quick, cheap trial run before committing to the full 69k pull.

## 3. Flatten to CSV

```bash
python3 creatoriq_export.py to-csv \
  --input exports/active_members.jsonl \
  --output exports/active_members.csv
```

This reads every line of the `.jsonl` file, flattens nested objects into
`parent.child` columns (e.g. a `profile: {followers: 1000}` field becomes a
`profile.followers` column) and JSON-encodes any nested lists (e.g. tags)
into a single cell, then writes one CSV with a header covering every column
seen across all records. Put your most important columns first with
`--priority-columns "id,name,email,status"` (default) so they show up at
the start of the spreadsheet.

Or do both steps in one command:

```bash
python3 creatoriq_export.py run \
  --endpoint "https://apis.creatoriq.com/crm/v2/publishers" \
  --params '{"list_id": 123456, "status": "active"}' \
  --data-path data --total-path meta.total \
  --output exports/active_members.jsonl \
  --csv-output exports/active_members.csv
```

## 4. Verify

```bash
wc -l exports/active_members.jsonl   # should read 69000 (or your real total)
python3 - <<'PY'
import csv
with open("exports/active_members.csv") as f:
    rows = list(csv.DictReader(f))
print("rows:", len(rows))
print("unique ids:", len({r["id"] for r in rows}))
PY
```

If the row count and unique-ID count both match the number your CreatorIQ
report shows, the export is complete and clean.

## CLI reference

Run `python3 creatoriq_export.py <command> --help` for full flag docs. Key
flags across `probe` / `fetch` / `run`:

| Flag | Meaning |
|---|---|
| `--endpoint` | Full API URL to page through |
| `--params` | JSON string of static filters (list/segment/status, etc.) |
| `--auth-style` | `bearer` (default, `Authorization: Bearer <key>`), `apikey-header` (custom header, see `--header-name`), or `query` (key as a query param, see `--apikey-query-param`) |
| `--pagination-style` | `offset` (default: `limit`/`offset` params) or `page` (`page`/`per_page`-style) |
| `--page-size` | Rows per request (500 is a reasonable default; raise it if the API allows more, to cut down request count) |
| `--data-path` | Dotted path to the record array in the JSON response (e.g. `data`, `results.publishers`) |
| `--total-path` | Dotted path to a total-count field, if the API returns one (used to know when to stop and for progress display) |
| `--sleep` | Delay between page requests, to stay comfortably under rate limits |
| `--max-retries` | Retry attempts per page on 429/5xx/network errors, with exponential backoff |
| `--id-field` | Field used to de-duplicate records across pages/resumes (default `id`) |
| `--resume` | Continue from the checkpoint file instead of restarting |

## Testing without hitting your real CreatorIQ account

`tests/mock_creatoriq_server.py` is a tiny local Flask server that mimics a
paginated, occasionally-rate-limited CreatorIQ-style endpoint with 2,500
fake records. It's handy for dry-running changes to the script (or just
building confidence in the tool) without touching production data:

```bash
python3 -m pip install -r requirements-dev.txt
python3 tests/mock_creatoriq_server.py &      # serves on :8765

export CREATORIQ_API_KEY=test-secret-key
python3 creatoriq_export.py run \
  --endpoint http://127.0.0.1:8765/publishers \
  --data-path data --total-path meta.total \
  --page-size 500 \
  --output /tmp/mock.jsonl --csv-output /tmp/mock.csv
```

## Security notes

- Never commit your real `.env`, any `*.jsonl` export, or the final CSV —
  they contain creator PII (emails, etc.). `.gitignore` already excludes
  these, but double-check before pushing anywhere.
- If you're running this from a shared machine/CI, prefer exporting
  `CREATORIQ_API_KEY` as an environment variable/secret over writing it to
  a `.env` file that could be accidentally committed.
