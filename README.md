# Creator Activation Dashboard (CreatorIQ + Streamlit)

A dashboard for creator/community management teams to understand creator
engagement, see who needs outreach, and track activation over time — built
with **Streamlit + Python**, structured to plug in the real CreatorIQ API
later without touching page code.

Built with **Streamlit** (not Google Looker Studio) — see
[`docs/why-streamlit-not-looker-studio.md`](docs/why-streamlit-not-looker-studio.md)
for the full reasoning, and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for
how the pieces fit together.

## What you get

Every page shares one global sidebar: a **date range** selector (Last 7/30/60/90
days, This Month, or Custom) and two live-adjustable thresholds — **days
considered "Active"** and **days before "Went Dark"** — that every page and
KPI below responds to instantly.

- **Dashboard Overview** — KPI cards (total / active / inactive / never
  activated / newly activated / reactivated / went dark / consistently
  active creators, plus posts and links created in the selected range),
  an activation-state breakdown chart, and a program-wide activity trend
  with spike callouts.
- **Creator Activity** — a searchable, filterable, sortable, exportable
  table with one row per creator: name, handle, email, publisher ID, tags,
  status, first/last post & link dates, last email sent/opened/clicked,
  every "days since" recency metric, lifetime + in-range counts. Select a
  row to jump to that creator's full profile.
- **New Activations** — creators who just published their first-ever post
  or created their first-ever trackable link, creators who've linked but
  never posted, and time-to-activation metrics (join → first link, join →
  first post, first link → first post).
- **Momentum** — "Spikes This Week": creators whose posting/link-creation
  volume is significantly above their own historical average, with a
  spike-percentage ranking.
- **Went Dark** — previously-active creators who've gone quiet, each with a
  rule-based **recommended follow-up action** based on their email
  engagement history.
- **Email Engagement** — send/open/click funnel, days-since-last-open
  distribution, and three actionable cross-segments: clicked an email but
  never created a link, created a link but never posted, and never opened
  an email at all.
- **Creator Profile** — full detail + a stacked activity timeline (posts,
  links, email opens/clicks) for one creator, reachable by search or by
  clicking through from any other page.
- **Data & Settings** — current mode (mock vs. live), sync freshness, and
  where every remaining config value lives.

Runs out of the box in **mock-data mode** with a realistic synthetic creator
population — no CreatorIQ credentials required to explore every page above,
including examples of every activation state (there are always some Never
Activated, Went Dark, Reactivated, Newly Activated, and Consistently Active
creators in the generated data).

## Quickstart (mock data, no API key needed)

**New to this?** See [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md) for a
step-by-step guide in plain English.

```bash
pip install -r requirements.txt
pip install -e .
streamlit run app/streamlit_app.py
```

Open the URL Streamlit prints (defaults to http://localhost:8501).

## Designed to swap mock data for the real CreatorIQ API later

Every page and every function in `src/creatoriq_dashboard/metrics.py` only
ever consumes four plain, normalized tables — `creators`, `posts`, `links`,
`email_events` — regardless of where they came from. There's exactly one
switch point:

- `src/creatoriq_dashboard/demo_data.py` generates those four tables as
  realistic mock data (the current default, `CREATORIQ_DASHBOARD_MODE=demo`).
- `src/creatoriq_dashboard/data_access.load_inputs()` is that switch point —
  in `live` mode it returns the exact same table shapes, instead read from a
  local SQLite cache populated by `scripts/refresh_data.py` against the real
  CreatorIQ API.

No dashboard/page code needs to change either way — only which data source
`load_inputs()` reads from.

### Connecting your real CreatorIQ data

The CreatorIQ API client, endpoint paths, and field mappings for this are
already built and **verified against a live CreatorIQ account** (not just
guessed from public docs) — see `config/endpoints.yaml` and
`config/field_mappings.yaml` for the confirmed schema and the quirks
discovered along the way (results sometimes come back as a JSON array and
sometimes as an object keyed by string indices; pagination metadata lives in
different places per resource; the page-size query param is `size`, not the
more common `page_size`/`limit`; etc.).

1. **Get API access.** Ask your CreatorIQ CSM / account admin for an API key
   (CreatorIQ's interactive API reference lives at
   https://apidocs.creatoriq.com but is gated behind your account's login).
2. **Copy `.env.example` to `.env`** and set `CREATORIQ_API_KEY`. The default
   `CREATORIQ_BASE_URL` (`https://api.creatoriq.com/api`) already matches
   what a live account returned.
3. Set `CREATORIQ_DASHBOARD_MODE=live` in `.env`.
4. **Start small.** `config/settings.yaml`'s `live_sync` section caps how
   much a sync pulls (`max_campaigns: 10`, `max_email_lookups: 300` by
   default) — CreatorIQ's data model is campaign-centric (there's no single
   "give me all my creators/posts" endpoint; you have to fan out over every
   campaign's roster + activity), so a full sync across hundreds of
   campaigns is a lot of API calls. Confirm a small sync works, then raise
   the caps.
5. Pull data into the local cache: `python scripts/refresh_data.py`.
6. Put that command on a schedule (cron, GitHub Actions, Airflow, etc.) — see
   [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#scheduling-refreshes).
7. `streamlit run app/streamlit_app.py` again — you're now looking at real
   data.

**One semantic gap worth resolving as part of that work:** in mock mode,
`links` represents link-*creation* events (matching "Total links created" /
"New Activations" in the UI spec). CreatorIQ's own API, at least on the
account this was verified against, doesn't expose a "trackable link
creation" event at all — only a cumulative click counter per post — so the
live pipeline currently derives `links` from click-count deltas instead
(see the caveat below). Check whether your account has a genuine link-
creation resource before assuming it doesn't; `config/field_mappings.yaml`
has the full explanation and exactly where to point a real `links` endpoint
if you find one.

#### Two confirmed data-quality caveats on the live side

**Link clicks are a cumulative counter, not an event log — and may not be
populated at all.** CreatorIQ's `/campaign/{id}/activity` endpoint reports a
`LinkClicks` field per post as a running total-to-date, not a timestamped
event. `etl.py` snapshots that counter on every sync and derives day-over-day
deltas — meaning **the first live sync always shows zero link activity**;
you need at least two scheduled syncs before deltas exist. Separately, on
the account this was tested against, `LinkClicks` came back `null` for every
post — some accounts don't populate it at all (link tracking may run
through a separate affiliate platform like Impact, CJ, or Rakoten instead).

**Email "opens" via CreatorIQ's API may not be trustworthy.** CreatorIQ's
`/publisher/{id}/messages` endpoint returns an `IsRead` flag on in-platform
Message Center notifications, which the live pipeline maps to `opened_at` as
a best-effort signal. On the account this was tested against, `IsRead`
stayed `False` for every message, including ones sent to creators who were
clearly actively posting — meaning creators read the actual email rather
than logging into the CreatorIQ portal, so the in-platform "read" flag never
got set. If that happens on your account too, sync real open-pixel data from
your ESP (Mailchimp, Klaviyo, HubSpot, Iterable, etc.) into the same
`email_events` shape instead — no dashboard code changes needed either way.

## Tuning the business rules

**Date range, "Active" days, and "Went Dark" days are adjustable live in the
sidebar** on every page — no restart needed. Their defaults, plus momentum
sensitivity and (once you're on live mode) API sync limits, live in
[`config/settings.yaml`](config/settings.yaml). The **Data & Settings** page
always shows the values currently in effect.

## Running tests / linting

```bash
pip install -r requirements-dev.txt
pytest tests/ -q
ruff check src/ app/ scripts/ tests/
```

`tests/test_app_smoke.py` runs every Streamlit page headlessly (via
`streamlit.testing.v1.AppTest`) and fails the build if any page raises — a
cheap regression guard for a fast-moving Streamlit app.

## Deploying it for the team

- **Fastest**: [Streamlit Community Cloud](https://streamlit.io/cloud) —
  point it at this repo/branch, set the same env vars as secrets, done.
- **Self-hosted**: `docker build -t creatoriq-dashboard . && docker run -p 8501:8501 --env-file .env creatoriq-dashboard`
  (see [`Dockerfile`](Dockerfile)).
- Either way, run `scripts/refresh_data.py` on a schedule *outside* the
  Streamlit process (cron / GitHub Actions / your existing orchestrator) so
  the app stays fast and never blocks a page load on a live CreatorIQ API
  call.

## Repo layout

```
config/                  Business rules + CreatorIQ endpoint/field config (YAML, no code changes needed)
src/creatoriq_dashboard/ Mock data generator, CreatorIQ API client, ETL, storage, and metrics (pure, unit-tested)
app/                      Streamlit multipage app
scripts/                  CLI entry points (refresh_data.py, seed_demo_data.py)
tests/                    pytest unit tests + Streamlit AppTest smoke tests
docs/                     Architecture + tool-choice rationale
```

## What else to consider

Beyond what's built here, the highest-leverage next steps for increasing
activation are usually:

1. **Campaign-level activation rate**: % of briefed/invited creators who
   actually posted per campaign — a different (and often more actionable)
   number than program-wide activation rate.
2. **A/B testing outreach**: use the Went Dark export as your control/
   treatment list and measure lift in next-cycle activation from different
   nudges (email subject lines, SMS, bonus incentives, 1:1 manager outreach).
3. **Alerting, not just reporting**: wire `scripts/refresh_data.py` + a
   digest script into your existing cron/Actions so the Went Dark / New
   Activations lists land in Slack automatically, without anyone opening
   the dashboard.
4. **Compliance/deliverables tracking**: if creators have contracted
   deliverable counts, layer "deliverables completed / owed" on top of raw
   post counts — activation and contract compliance aren't the same thing.
