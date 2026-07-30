# Architecture

```
        ┌───────────────────────────────────────────────────────┐
        │                     CreatorIQ API                     │
        │  /campaigns  /campaign/{id}/publishers                │
        │  /campaign/{id}/activity  /publisher/{id}/messages    │
        │  /publisher/{id}/summary  /publishers?filter=Id=...   │
        └───────────────────────┬─────────────────────────────-─┘
                                 │ per-campaign fan-out
                                 │ (config/endpoints.yaml)
                     ┌───────────▼────────────┐
                     │  api_client.py         │  auth, pagination (3 different
                     │                        │  styles!), retry/backoff
                     └───────────┬────────────┘
                                 │ raw JSON records
                     ┌───────────▼────────────┐
                     │  normalize.py          │  dotted-path field mapping
                     │  (config/field_mappings.yaml)
                     └───────────┬────────────┘
                                 │ normalized DataFrames
                     ┌───────────▼────────────┐
                     │  etl.py                │  campaign fan-out, roster
                     │                        │  dedup, link-click snapshots,
                     │                        │  bounded email lookups
                     └───────────┬────────────┘
                                 │
                     ┌───────────▼────────────┐
                     │ storage.py (SQLite)    │  data/warehouse.db
                     └───────────┬────────────┘
                                 │ read by Streamlit (cached, TTL)
                     ┌───────────▼────────────┐
                     │  metrics.py            │  activation score, spikes,
                     │  (pure functions,      │  cohorts, email engagement —
                     │   unit tested)         │  all pure pandas
                     └───────────┬────────────┘
                                 │
                     ┌───────────▼────────────┐
                     │  app/ (Streamlit)      │  Overview / Creator Activity /
                     │                        │  New Activations / Momentum /
                     │                        │  Went Dark / Email Engagement /
                     │                        │  Creator Profile / Settings
                     └────────────────────────┘
```

In **mock/demo mode** (the default), `src/creatoriq_dashboard/demo_data.py`
generates the `creators`/`posts`/`links`/`email_events` tables directly and
the CreatorIQ API boxes above are simply unused — `data_access.load_inputs()`
is the one place that decides which path to take, so no page or metrics code
needs to know or care which mode is active.

`scripts/refresh_data.py` (the ETL trigger) and the Streamlit app are
deliberately **separate processes**. The app never calls the CreatorIQ API
directly — it only reads the local SQLite cache. This means:

- Page loads and filter changes are instant regardless of CreatorIQ API
  latency or rate limits.
- You can refresh on whatever cadence makes sense (hourly, nightly) without
  touching the app.
- If CreatorIQ is down or your key expires, the dashboard keeps showing the
  last good sync instead of breaking for end users.

## CreatorIQ's real data model (verified against a live account)

This is genuinely messier than a typical REST API, which is exactly why the
paths/shapes live in `config/endpoints.yaml` rather than being hard-coded:

- **There's no flat "give me all creators" or "give me all posts"
  endpoint.** Everything except the creator-search index (`/publishers`,
  which returns the *entire* cross-brand discovery database, not your
  roster) is scoped to a campaign: `/campaign/{id}/publishers` for the
  roster, `/campaign/{id}/activity` for posts. `etl.py` fans out over every
  (status-filtered, capped) campaign and dedupes creators across them.
- **Three different pagination styles, in the same API:**
  - `/publishers`, `/campaigns`, `/publisher/{id}/messages`: a top-level
    `{count, total, page, "<Key>": [...]}` envelope. The page-size query
    param is `size` (confirmed) — `page_size`/`limit`/`per_page` are all
    silently ignored and fall back to a default of 20/page.
  - `/campaign/{id}/activity`: pagination metadata lives *inside* the
    response wrapper (`{"CampaignActivity": {"items": [...], "pagination":
    {"total_pages": N}}}`), not at the top level.
  - `/campaign/{id}/publishers`: ignores `?page=` entirely and always
    returns everything in one call.
- **Two different "list of records" shapes:** most collections are a plain
  JSON array, but `CampaignPublisher` comes back as an object keyed by
  string indices (`{"0": {...}, "1": {...}}`). `api_client.py`'s
  `coerce_to_record_list()` normalizes both.
- **Two different creator ID spaces**: campaign-scoped endpoints use an
  internal numeric `PublisherId`; per-creator endpoints
  (`/publisher/{id}/summary`, `/publisher/{id}/messages`) need the longer
  `NetworkPublisherId` instead. A post's own record conveniently includes
  both; for creators who haven't posted, `etl.py` resolves it via
  `/publishers?filter=Id={id}` (one extra API call, bounded by
  `live_sync.max_email_lookups` in `config/settings.yaml`).

`config/field_mappings.yaml` documents two further, empirically-confirmed
data-quality caveats specific to this account (no literal "post date" field,
just `DateSubmitted`; and `LinkClicks` is a cumulative counter, not an event
log) — read the comments there, and the README's "Two confirmed
data-quality caveats" section, before trusting either metric blindly on your
own account.

To (re-)verify any of this against your own account: hit each endpoint once
with `curl -H "Authorization: Bearer $CREATORIQ_API_KEY"
https://api.creatoriq.com/api/<path>` and compare the shape to what's in
`config/endpoints.yaml`. No Python changes are needed for a schema/path
difference — only the YAML.

## Link-click deltas (snapshot-based, not event-based)

CreatorIQ's `LinkClicks` field on a post is a running total, not a
timestamped click log. `storage.append_link_click_snapshot()` records that
counter (plus `creator_id`/`campaign_id`) on every sync into an append-only
`link_click_snapshots` table; `storage.derive_link_click_deltas()` then
diffs consecutive snapshots per post and turns any *increase* into a
`links` row (`clicked_at` = the snapshot's timestamp, `clicks` = the size of
the increase). Practically: **the first sync ever run always produces zero
link-click rows** (nothing to diff against yet) — this is expected, not a
bug, and the Momentum page says so explicitly in live mode.

## Sync scope and safety limits

Because a full sync fans out over every campaign (roster + posts) and then
over every unique creator (email/messages), `config/settings.yaml`'s
`live_sync` section caps the blast radius: `max_campaigns`,
`campaign_status_filter`, and `max_email_lookups`. Each sync currently
re-fetches roster/posts in full for the campaigns in scope rather than
pulling incrementally — fine for the "cap at N campaigns" default, but worth
revisiting (e.g. skip campaigns whose `LastModified`/status hasn't changed
since the last sync) if you raise the caps enough that a full run gets slow.

## Scheduling refreshes

### Cron (simplest, if you have any always-on machine/VM)

```cron
# Refresh every hour
0 * * * * cd /path/to/repo && /path/to/repo/.venv/bin/python scripts/refresh_data.py >> /var/log/creatoriq-refresh.log 2>&1
```

### GitHub Actions

```yaml
# .github/workflows/refresh-creatoriq-data.yml
name: Refresh CreatorIQ data
on:
  schedule:
    - cron: "0 * * * *" # hourly
  workflow_dispatch: {}
jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: python scripts/refresh_data.py
        env:
          CREATORIQ_DASHBOARD_MODE: live
          CREATORIQ_BASE_URL: ${{ secrets.CREATORIQ_BASE_URL }}
          CREATORIQ_API_KEY: ${{ secrets.CREATORIQ_API_KEY }}
          CREATORIQ_ORG_ID: ${{ secrets.CREATORIQ_ORG_ID }}
      - run: |
          # Persist data/warehouse.db somewhere durable (e.g. commit to a
          # data branch, upload as an artifact, or push to S3/GCS) — a
          # GitHub Actions runner's filesystem doesn't persist between runs.
          echo "Wire this step up to your actual storage target."
```

Note the caveat in that last step: Actions runners are ephemeral, so
`data/warehouse.db` needs to live somewhere durable that both the refresh
job and the deployed Streamlit app can reach (S3/GCS bucket, a small
persistent VM, a managed Postgres instead of SQLite, etc.) once you're
running this for real outside of a single long-lived machine.

## Scaling beyond SQLite

SQLite is intentionally the default because it's zero-setup for a first
pass. If your creator program is large (tens of thousands of creators /
millions of events) or multiple people need to write to the warehouse
concurrently, swap `storage.py`'s `create_engine("sqlite:///...")` for a
Postgres/MySQL URL — everything else (`etl.py`, `metrics.py`, the Streamlit
pages) is unchanged since they all go through SQLAlchemy/pandas.
