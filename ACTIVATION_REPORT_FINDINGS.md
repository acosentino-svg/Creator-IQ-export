# Activation report: what's possible via the CRM API today

Investigated pulling a per-creator activation report (for `Status=Active` +
tag `Crm Adriana`) with the columns:

```
Creator Name, Time Since Last Post, Last Post Date,
Time Since Last Link Creation, Last Link Creation Date,
Link Clicks, Links Generated,
Time Since Last Revenue Generation, Last Transaction Date,
Last Email Opened, Last Email Clicked On
```

## Summary

This exact set of columns matches what looks like a built-in **"Active
Members" report inside the CreatorIQ web app** (probably under a Reports /
Creator Program dashboard tab) — it blends data from several backend
systems that are **not** exposed by the CRM v1 Publishers API we have
credentials for. Some columns can be approximated from the CRM API;
others are hard-blocked.

## What's confirmed accessible (CRM v1 `/publisher/{id}/...`)

- **Creator Name** — `Publisher.PublisherName`. ✅ Reliable.
- Per-social-account snapshot via `/publisher/{id}/socialAccounts`:
  `NumberOfPosts`, `Followers`, `LastPostDate`. The `LastPostDate` field
  *does* get populated for some accounts, but it's clearly a stale,
  one-time-scrape value in most cases (e.g. seen dates from 2017, 2020,
  2021 on accounts that are otherwise active), not a continuously updated
  "last activity" timestamp. **Not reliable** for "Time Since Last Post" /
  "Last Post Date" in the sense of a recent-activation report.
- Per-publisher `EventLog` (`/publisher/{id}/log`) and `Messages`
  (`/publisher/{id}/messages`) contain individual **commission payment
  events** (e.g. `"Commission payment item ... created for
  PublisherId=X, CampaignId=Y. Amount=33.48 USD"`, and structured
  `Messages` with `{"CampaignId":...,"Amount":...}`), sorted by time
  descending. These *can* be parsed to derive "Last Transaction Date" /
  "Time Since Last Revenue Generation" — but only via one extra API call
  per creator (there's no bulk "transactions" or "ecommerce" collection
  endpoint), and completeness depends on how far back in the log/messages
  the last payment falls.
- No post-level history endpoint exists (`.../socialAccounts/{id}/posts`,
  `.../posts`, `.../socialPosts` all 404), so per-window post counts
  (e.g. "how many posts Sept 1 2025–Jan 2026" vs "Jan 1 2026–today")
  **cannot be computed** from this API at all — there's only a single
  cumulative `NumberOfPosts` snapshot, not dated individual posts.

## What's hard-blocked (confirmed via direct testing)

- **Link Tracking API** (`https://apis.creatoriq.com/linktracking/v1/api/...`)
  → `403 Forbidden` / `ForbiddenException` at the API-gateway level (not an
  application error) for every path and auth-header variant tried
  (`x-api-key`, `Authorization: Bearer`, `X-Authorization`). This is the
  product that would hold **Links Generated** and **Link Clicks**.
- **Payments API** (`https://apis.creatoriq.com/payments/v1/api/...`) →
  same `403 Forbidden` / gateway-level rejection.
- **SafeIQ API** → same `403 Forbidden`.
- No accessible `Ecommerce`, `ConversionMetrics`, or `Reports` resource
  under the CRM v1 API (all guessed paths 404 "Route not found"); a
  `campaign/{id}/publishers` route exists but times out (504) rather than
  responding.
- No evidence of an email-open/click-tracking resource anywhere in the CRM
  v1 API. The per-publisher `Messages` collection is internal CRM
  messages (with an `IsRead` flag) — not marketing-email open/click
  tracking.

The `403 Forbidden` responses come back as raw AWS API Gateway
`ForbiddenException` errors (not CreatorIQ's normal JSON error shape),
which strongly suggests these are genuinely separate product
subscriptions/API keys that the current `CREATORIQ_API_KEY` was never
provisioned for — not something fixable by changing request headers or
paths.

## Conclusion / recommendation

**Links Generated, Link Clicks, Last Email Opened, and Last Email Clicked
On cannot currently be pulled via API** with the credentials available in
this environment. Also, per-window post counts (Sept 2025–Jan 2026 vs.
Jan 2026–today) aren't derivable at all from this API's data model.

Two ways to get the actual report:

1. **If this report already exists in the CreatorIQ web app** (which the
   exact column set strongly suggests), the fastest path is to export it
   directly from the CreatorIQ UI (Reports / Creator Program dashboard),
   for the Crm Adriana tag and each date range, then hand us that
   export — we can merge/filter/format it from there.
2. **If API access should be used instead**, we'd need credentials/scopes
   for the Link Tracking API and Payments API (currently both return
   `403 Forbidden`), plus confirmation of whichever system tracks email
   opens/clicks. With that, we could extend `src/creatoriq_export.py` to
   join those sources onto the Crm Adriana creator list for both date
   windows.

In the meantime, `output/creatoriq_active_members_crm_adriana.csv` (11,662
rows, `Status=Active` + tag `Crm Adriana`) is available as the creator
list to join against once one of the above is available.

## Follow-up: is there a "run this saved report via API" endpoint?

Also tested whether a report built in the CreatorIQ web UI (filters +
column selection) could be fetched back out via the API — i.e. build it
once in the app, then pull its data with `CREATORIQ_API_KEY`. Tried ~15
more candidate resource names under `/crm/v1/api/...`
(`report(s)`, `customReport(s)`, `savedReport(s)`, `reportBuilder`,
`export(s)`, `activationReport(s)`, `insights`, `analytics`, `dashboard`,
`metrics`, `publisherReport(s)`, `activation`, `activationMetrics`,
`creatorReport`) — all return `404 Route not found`. Also checked the
`Lists` resource (which *is* accessible) as a possible vehicle: a `List`
is just a static, named group of publisher IDs with no metrics attached
(confirmed by inspecting `GET /crm/v1/api/list/{id}`), so it can't carry
report data either.

**Conclusion:** there is no discoverable public-API equivalent of the
in-app report builder/export reachable with `CREATORIQ_API_KEY`. The
in-app report almost certainly runs through a separate, session
(browser-login) authenticated internal API, not the public CRM REST API
this key is scoped to. Practical options to get that report's data out:

1. **Export it directly from the CreatorIQ UI** (build the report with
   the desired filters/columns, then use its Export/Download-CSV action)
   and hand us the file — this is the most reliable option since it's
   the same pipe that already has access to link-tracking/payments/email
   data.
2. If the report page has no visible export button but loads data via
   AJAX, the underlying request can be captured from the browser
   (DevTools → Network tab → find the XHR/fetch call that returns the
   report's JSON/CSV) and shared with us as a "Copy as cURL". Note this
   will very likely be authenticated with a live browser session
   cookie/JWT rather than an API key, so it'd work as a one-off pull but
   not as a long-lived automated integration.

## Update: the async `Reports/*` view API (major breakthrough)

The user found CreatorIQ API-docs entries for a whole family of endpoints
at `GET /crm/v1/api/view?view=Reports/<Name>` (e.g. `Reports/Publishers`,
`Reports/CreatorsReport`, `Reports/Campaigns/CampaignPublishers`,
`Reports/Campaigns/CampaignPosts`, `Reports/DailyCampaignPosts`,
`Reports/CreatorConnectCreators`, `Reports/CreatorPromoteReport`,
`Reports/LinkedAccountsByNetwork/BrokenLinks`,
`Reports/CreatorsPaymentCollectionStatusDetails`,
`Reports/CreatorPaymentsReport`). These are real and accessible with
`CREATORIQ_API_KEY` (unlike the separate LinkTracking/Payments/SafeIQ
products, which are `403 Forbidden`).

**How it works:** each GET is an async job. The first call returns
`TaskStatus=CREATED`; the *same* request must be re-issued to poll status
(`CREATED` → `PROCESSING` → `DONE`); once `DONE`, the actual result JSON
is at `Result.Headers.Location` (a pre-signed S3 URL, valid ~24h).
Processing time is **roughly constant (~45-90s) regardless of request
size**, up to a few hundred thousand rows (`requestData[take]`) — but
requests for very large `take` (1,000,000+) or, separately, requests with
a large `requestData[skip]` **can hang indefinitely** (observed: a
600k-row report timed out repeatedly for any request with `skip>=50000`,
even with `take` as small as 1000 — a classic offset-pagination
performance cliff on the backend, unrelated to result size). None of the
guessed filter params (`creatorId`, `publisherId`, `from`, `dateFrom`,
etc.) actually filter server-side for any of these views — pagination
via `take`/`skip` only, filtering has to happen client-side after
fetching.

**What we found in each report:**

- **`Reports/DailyCampaignPosts`** — the big win. A *daily-snapshot* fact
  table: every post, once per day it was tracked (so one real post
  appears as several rows). 3,067,480 rows total, paginates reliably in
  300k-row chunks (11 chunks, ~20 min total). Fields include `creatorid`,
  `postid`, `postdate` (constant per post, i.e. the real post date —
  reliable, unlike the stale `SocialAccounts.LastPostDate`), `campaign`,
  `platform`, engagement metrics, and a `clicks` field that actually *is*
  sometimes populated (confirmed non-null examples) — though this looks
  like organic post-engagement clicks, not Wayfair/CJ affiliate
  tracking-link clicks specifically. Fetched and filtered to the 11,662
  Crm Adriana creators (1,125,355 matching rows; only 1,432 creators have
  any tracked post) — used to build real Last Post Date / Time Since
  Last Post / per-window post counts (see `output/crm_adriana_post_activity.csv`).
- **`Reports/CreatorPaymentsReport`** — per (creator, campaign) payment
  status with `RequirementsCompletedAt`, `FinalPayout`, `StatusOfPayment`
  (`Paid` / `Ready to Pay` / null). This is the closest thing found to
  "Last Transaction Date" / revenue, but it's flat campaign-gifting
  payouts, not ongoing CJ affiliate commission revenue. **Full coverage
  wasn't achievable**: 601,430 total rows, but every request with
  `skip >= 50000` hung indefinitely (tested repeatedly, including with
  `take` as small as 1000), so only the first ~50,000 rows (in whatever
  default sort order the report uses) were retrievable. That covers only
  **882 of 11,662 (7.6%)** of our tagged creators —
  `output/crm_adriana_payments_PARTIAL.csv` (2,566 deduplicated rows) is
  provided for reference only and should **not** be treated as complete
  or representative; most creators' absence from it reflects the
  pagination limitation, not an absence of payments.
- **`Reports/CreatorsReport`**, **`Reports/Publishers`**,
  **`Reports/Campaigns/CampaignPublishers`**,
  **`Reports/Campaigns/CampaignPosts`** — creator/campaign profile and
  audience-engagement data (social handles, follower counts, recruiting
  status, contact email). No link-click or revenue columns.
- **`Reports/CreatorPromoteReport`** — returned 0 rows for this account.
- **`Reports/LinkedAccountsByNetwork/BrokenLinks`** — about *social
  account* linking health (token broken/linked/unlinked), not affiliate
  tracking links.
- **`Reports/CreatorsPaymentCollectionStatusDetails`** — payment
  *onboarding* status (whether a creator has a payable account set up),
  not transaction history.

**Net effect on the original ask:** Last Post Date / Time Since Last
Post / post counts per date window are now solved with real data for the
Crm Adriana creators. Last Transaction Date / revenue is only ~7.6%
coverable due to a backend pagination limitation on
`CreatorPaymentsReport`. Links Generated, Link Clicks (affiliate/CJ
specific), and Last Email Opened/Clicked remain not found anywhere
accessible.
