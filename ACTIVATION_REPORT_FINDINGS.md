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
