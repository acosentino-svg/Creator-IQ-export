# Why Streamlit instead of Google (Looker) Data Studio

Short answer: **use Streamlit** for this specific use case (a CreatorIQ-API-driven
activation dashboard with custom scoring/anomaly logic), and reserve Looker
Studio for later, exec-facing summaries once the numbers are stable.

## The core constraint: Looker Studio doesn't call arbitrary REST APIs

Looker Studio (formerly Google Data Studio) is excellent at visualizing data
that's *already* in a supported source (Google Sheets, BigQuery, a JDBC/MySQL
connector, or one of its partner connectors). It has **no native CreatorIQ
connector** and no generic "call this REST API with a bearer token and page
through JSON" data source. Your realistic options to get CreatorIQ data into
Looker Studio are:

1. Pay for a third-party connector (e.g. via the CreatorIQ↔BI marketplace
   integrations, Improvado, Adverity, Supermetrics-style tools) — recurring
   cost, and you're still limited to whatever report shapes/fields that
   vendor exposes.
2. Build a **custom Looker Studio Community Connector** in Apps Script that
   calls the CreatorIQ API — this is real engineering work (Apps Script has
   execution-time limits, weaker debugging, and no local dev loop) to end up
   with *less* flexibility than just writing Python.
3. Land CreatorIQ data in BigQuery/Sheets yourself (i.e., you still need to
   write the exact same extraction/pagination/auth code this repo has), and
   *then* point Looker Studio at that.

In other words: with Looker Studio you either pay a vendor for a black-box
connector, or you write custom extraction code anyway and Looker Studio only
handles the last-mile chart rendering.

## What this dashboard specifically needs that a BI tool struggles with

- **Composite activation scoring** (recency decay + frequency + channel
  diversity + trend, see `src/creatoriq_dashboard/metrics.py`) — expressible
  in Looker Studio's calculated fields, but painful, and version-control-hostile
  (calculated fields live in the UI, not in a diffable file).
- **Spike detection** via rolling z-scores — needs a real windowed
  statistical function per activity type; Looker Studio's calculated fields
  don't support rolling windows without pre-aggregating in the source data
  anyway (at which point you're doing this in Python/SQL regardless).
- **Cross-channel joins** (posts + trackable links + a separate email/ESP
  engagement source) with different keys and cadences — much more natural in
  pandas than in Looker Studio's blending UI, which caps the number of joined
  sources and joins.
- **Actionability**: one-click CSV export of a specific filtered creator list,
  a Slack digest button, a per-creator drill-down page — these are app
  *interactions*, not just charts. Looker Studio is a reporting canvas, not an
  app framework.

## What Looker Studio (or any BI tool) is genuinely better at

- Distributing a **read-only, no-login-friction** summary to executives who
  don't want a URL that requires app hosting/auth.
- Combining CreatorIQ metrics with other warehouse data (spend, revenue,
  finance) that's *already* centralized in BigQuery/Sheets for other reasons.
- Zero-maintenance for people who will never touch the underlying data model.

## Recommended path

1. **Now**: this Streamlit app, reading a local SQLite cache refreshed on a
   schedule. Fast to build, fully custom logic, git-diffable config, and you
   (or anyone on the team) can run it locally in five minutes.
2. **Later, if useful**: once `scripts/refresh_data.py` is reliably landing
   clean data, point a scheduled export at BigQuery/Sheets from the *same*
   normalized tables this app already produces (`creators`, `posts`,
   `links`, `email_events` in `data/warehouse.db`), and build a lightweight
   Looker Studio summary on top of that for leadership reporting. You get the
   best of both without re-doing the CreatorIQ integration work twice.
