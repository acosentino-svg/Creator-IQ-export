# Architecture

```
                 ┌────────────────────┐
                 │   CreatorIQ API    │
                 └─────────┬──────────┘
                            │ paginated REST calls
                            │ (config/endpoints.yaml)
                 ┌─────────▼──────────┐
                 │  api_client.py     │  auth, pagination, retry/backoff
                 └─────────┬──────────┘
                            │ raw JSON records
                 ┌─────────▼──────────┐
                 │  normalize.py      │  dotted-path field mapping
                 │  (config/field_mappings.yaml)
                 └─────────┬──────────┘
                            │ normalized DataFrames
                 ┌─────────▼──────────┐
                 │  etl.py            │  incremental sync + upsert
                 └─────────┬──────────┘
                            │
                 ┌─────────▼──────────┐
                 │ storage.py (SQLite)│  data/warehouse.db
                 └─────────┬──────────┘
                            │ read by Streamlit (cached, TTL)
                 ┌─────────▼──────────┐
                 │  metrics.py        │  activation score, spikes, cohorts,
                 │  (pure functions,  │  email engagement — all pure pandas,
                 │   unit tested)     │  independently testable
                 └─────────┬──────────┘
                            │
                 ┌─────────▼──────────┐
                 │  app/ (Streamlit)  │  Overview / Spikes / Email / Explorer /
                 │                    │  Needs Attention / Data & Settings
                 └────────────────────┘
```

`scripts/refresh_data.py` (the ETL trigger) and the Streamlit app are
deliberately **separate processes**. The app never calls the CreatorIQ API
directly — it only reads the local SQLite cache. This means:

- Page loads and filter changes are instant regardless of CreatorIQ API
  latency or rate limits.
- You can refresh on whatever cadence makes sense (hourly, nightly) without
  touching the app.
- If CreatorIQ is down or your key expires, the dashboard keeps showing the
  last good sync instead of breaking for end users.

## Why a config-driven CreatorIQ client instead of hard-coded endpoints

CreatorIQ's API reference (https://apidocs.creatoriq.com) requires an
account login to view, and exact resource paths / JSON field names can vary
by account and API version. Hard-coding them would mean every user of this
repo has to fork-and-edit Python to match their account. Instead:

- `config/endpoints.yaml` defines resource paths, HTTP method, and
  pagination style (page / offset / cursor — CreatorIQ's docs don't publicly
  specify which one your account uses, so all three are supported).
- `config/field_mappings.yaml` maps normalized column names (`creator_id`,
  `posted_at`, `opened_at`, ...) to the raw JSON paths CreatorIQ actually
  returns (e.g. `Publisher.Id`, `PostDate`).
- `src/creatoriq_dashboard/api_client.py` and `normalize.py` are generic —
  they read those YAML files rather than assuming a schema.

To align this with your real account: sign in at apidocs.creatoriq.com (or
ask your CreatorIQ CSM for your account's Postman collection), hit each
resource once, and update the YAML to match the response you actually get.
No Python changes required for a schema/path difference.

## Incremental sync

`posts`, `links`, and `email_events` are pulled incrementally: `etl.py`
records the timestamp of the last successful sync per resource
(`sync_state` table) and passes it as an `updated_since` param on the next
run (see `config/endpoints.yaml`'s `{since}` placeholder). `creators` and
`campaigns` are pulled in full each run since program rosters are small
relative to activity/event volume — change this in `etl.py`'s
`INCREMENTAL_RESOURCES` set if your creator roster is large enough to
warrant incremental pulls too.

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
