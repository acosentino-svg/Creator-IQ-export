# Creator Activation Dashboard (CreatorIQ + Streamlit)

A self-serve dashboard for creator/influencer program managers to answer:
**"who's active, who's posted, where are the spikes, and who's gone quiet on
email?"** — built on top of the CreatorIQ API.

Built with **Streamlit** (not Google Looker Studio) — see
[`docs/why-streamlit-not-looker-studio.md`](docs/why-streamlit-not-looker-studio.md)
for the full reasoning, and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for
how the pieces fit together.

## What you get

- **Overview** — total creators, active rate, average activation score,
  segment breakdown, and a combined posts/link-click timeline with spike
  callouts.
- **Activity & Spikes** — posts and trackable-link clicks tracked as
  *separate* channels, with rolling z-score anomaly detection so a spike in
  one doesn't mask a lull in the other.
- **Email Engagement** — open rates, days-since-last-open distribution, and
  a filterable/exportable list of creators who haven't opened an email
  recently (the "email-cold" list).
- **Creator Explorer** — sortable/filterable roster with a 0-100 composite
  **activation score**, plus a per-creator drill-down timeline combining
  posts, link clicks, and email opens.
- **Needs Attention** — a prioritized, exportable outreach list combining
  activation segment + email coldness, with an optional one-click Slack
  digest.
- **Data & Settings** — sync freshness, demo/live mode toggle instructions,
  and every business-rule threshold (read live from `config/settings.yaml`).

Runs out of the box in **demo mode** with realistic synthetic data — no
CreatorIQ credentials required to explore it.

## Quickstart (demo mode, no API key needed)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app/streamlit_app.py
```

Open the URL Streamlit prints (defaults to http://localhost:8501). You're now
looking at ~180 synthetic creators with realistic posting/link-click/email
behavior, including a few deliberate activity spikes.

## Connecting your real CreatorIQ data

1. **Get API access.** Ask your CreatorIQ CSM / account admin for an API key
   and the base URL for your instance (CreatorIQ's API reference lives at
   https://apidocs.creatoriq.com but is gated behind your account's login —
   ask CreatorIQ support or your CSM if you don't have a login yet).
2. **Copy `.env.example` to `.env`** and fill in `CREATORIQ_BASE_URL`,
   `CREATORIQ_API_KEY`, and `CREATORIQ_ORG_ID` (if your account requires it).
3. **Confirm the endpoint paths and field names** in
   `config/endpoints.yaml` and `config/field_mappings.yaml` against your
   account's actual API docs / Postman collection. CreatorIQ's exact
   resource paths and JSON field casing can differ by account and API
   version, so this repo ships sensible *defaults* (based on CreatorIQ's
   publicly documented data model: Publishers, Campaigns, Social Posts,
   Links, Communications) rather than hard-coded assumptions — you edit YAML,
   not Python, to align them.
4. Set `CREATORIQ_DASHBOARD_MODE=live` in `.env`.
5. Pull data into the local cache:

   ```bash
   python scripts/refresh_data.py
   ```

6. Put that command on a schedule (cron, GitHub Actions, Airflow, etc.) — see
   [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#scheduling-refreshes) for a
   ready-to-use GitHub Actions example.
7. `streamlit run app/streamlit_app.py` again — you're now looking at real
   data, served instantly from the local SQLite cache instead of hitting the
   CreatorIQ API on every page view/filter change.

### About "who has/hasn't opened an email"

CreatorIQ's core product is influencer *campaign* data (posts, engagement,
links) — email open/click tracking is typically a separate **Communications
/ Message Center** feature for creator outreach. If your account exposes
that data via the API, point `config/endpoints.yaml`'s `email_events`
resource at it and map its fields in `config/field_mappings.yaml`. If it
doesn't (or you send creator emails through a separate ESP like Mailchimp,
Klaviyo, HubSpot, or Iterable), the cleanest path is:

- Export/sync opens from that ESP into the same `email_events` shape
  (`creator_id`, `message_id`, `sent_at`, `opened_at`, `clicked_at`), matched
  to CreatorIQ creators by email address, and land it in the same
  `email_events` table (`scripts/refresh_data.py` is a good place to add a
  second sync step).
- Everything downstream (the Email Engagement page, the cold-list export,
  the composite activation score) already expects exactly that shape, so no
  dashboard code changes are needed either way.

## Tuning the business rules

Every threshold that defines "active" / "at risk" / "dormant", the
activation-score weights, spike sensitivity, and email-cold rules live in
[`config/settings.yaml`](config/settings.yaml) — a config change, not a code
change. The **Data & Settings** page in the app always shows the values
currently in effect.

## Running tests / linting

```bash
pip install -r requirements-dev.txt
pytest tests/ -q
ruff check src/ app/ scripts/ tests/
```

`tests/test_app_smoke.py` runs every Streamlit page headlessly (via
`streamlit.testing.v1.AppTest`) in demo mode and fails the build if any page
raises — a cheap regression guard for a fast-moving Streamlit app.

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
src/creatoriq_dashboard/ API client, normalization, storage, ETL, and metrics (pure, unit-tested)
app/                      Streamlit multipage app
scripts/                  CLI entry points (refresh_data.py, seed_demo_data.py)
tests/                    pytest unit tests + Streamlit AppTest smoke tests
docs/                     Architecture + tool-choice rationale
```

## What else to consider (the "anything else" list)

Beyond what's built here, once this is live, the highest-leverage next steps
for increasing activation are usually:

1. **Onboarding funnel**: track time from "joined program" to "first post" —
   this dashboard's `Never Activated` segment is a start; add a cohort/funnel
   view once you have enough new-creator volume to segment by join month.
2. **Campaign-level activation rate**: % of briefed/invited creators who
   actually posted per campaign — a very different (and often more
   actionable) number than program-wide activation rate.
3. **A/B testing outreach**: use the "Needs Attention" export as your
   control/treatment list and measure lift in next-cycle activation from
   different nudges (email subject lines, SMS, bonus incentives, 1:1 manager
   outreach).
4. **Alerting, not just reporting**: the Slack digest button on the Needs
   Attention page is a start — wire `scripts/refresh_data.py` + a digest
   script into your existing cron/Actions so the list lands in Slack weekly
   without anyone opening the dashboard.
5. **Compliance/deliverables tracking**: if creators have contracted
   deliverable counts, layer "deliverables completed / deliverables owed" on
   top of raw post counts — activation and contract compliance aren't
   automatically the same thing.
