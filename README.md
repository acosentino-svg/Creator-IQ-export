# Creator-IQ-export

A small, generic paginated REST → CSV export tool (`src/creatoriq_export.py`),
used here against the CreatorIQ CRM Publishers API to export **Active
Members**.

## Endpoint

```
GET https://apis.creatoriq.com/crm/v1/api/publishers
```

- Auth: header `x-api-key: <CREATORIQ_API_KEY>`
- Pagination: `page` / `size` query params (`size` max `1000`)
- Collection JSON path: `PublisherCollection`
- Grand-total JSON path: `total`
- Field projection: `fields=A,B,C` (server-side; greatly reduces payload size)
- Filtering: `filter=Field=Value` (repeatable query param for AND conditions).
  Only a specific whitelist of fields is filterable server-side (the API
  returns the whitelist in its 400 error body if you pass a disallowed
  field). `Status` is filterable.

## Probe results (unfiltered discovery)

The account's CRM has **948,334** total publisher records. A probe of the
`Status` field (sampled, then confirmed with authoritative server-side
`filter=Status=<value>` total counts) found the full, exhaustive breakdown:

| Status       | Count     |
|--------------|-----------|
| Approved     | 702,191   |
| Lost         | 132,736   |
| **Active**   | **42,990**|
| Open         | 18,625    |
| Incomplete   | 40,162    |
| Signed       | 3,001     |
| Rejected     | 8,616     |
| Suspended    | 13        |
| **Total**    | 948,334   |

`Status = "Active"` (paired with `StatusCategory = "In Network"` in nearly
every case) is the field/value that represents current **active members**.
Note: the live count is **42,990**, not ~69k — the ~69k figure from the task
description doesn't match any single status value or simple combination
found in the live data; 42,990 is the authoritative, server-confirmed count
for `Status=Active` today.

## Usage

```bash
export CREATORIQ_API_KEY=...

# 1. Probe (no filter): sample the collection and get authoritative
#    per-value counts for a field.
python3 src/creatoriq_export.py probe \
  --endpoint https://apis.creatoriq.com/crm/v1/api/publishers \
  --auth-header x-api-key --api-key-env CREATORIQ_API_KEY \
  --data-path PublisherCollection --total-path total \
  --field Status --sample-size 1000

# 2. Full fetch + CSV export, filtered to Active members.
python3 src/creatoriq_export.py export \
  --endpoint https://apis.creatoriq.com/crm/v1/api/publishers \
  --auth-header x-api-key --api-key-env CREATORIQ_API_KEY \
  --data-path PublisherCollection --total-path total \
  --filter Status=Active \
  --fields Id,NetworkPublisherId,PublisherId,PublisherName,Status,StatusCategory,Language,SecondaryLanguage,Size,LeadSource,EthnicBackground,Category,SubCategories,Gender,DateOfBirth,Description,LogoURL,DateRecruitingStarted,RecruiterName,SubNetworkName,InterfaceLocale,Unsubscribe,DontContact,Tags,TagNames,DateJoinedNetwork,DateLastPublisherPortalLogin,TermsAccepted,LastUpdated,CampaignsCount,TotalSubscribers,Country,LinkAccountsPage,PublisherCampaignsListLink \
  --max-size 1000 \
  --min-interval 0.25 \
  --out output/creatoriq_active_members.csv
```

The tool respects the API's rate limit (observed `x-ratelimit-limit: 5`) via
a client-side `--min-interval` throttle plus exponential-backoff retries on
HTTP 429/5xx responses.

## Filtering by tag

The API's server-side `filter=Field=Value` only does an exact **whole
field value** match. That's useless against `Tags`, which is a serialized,
comma-separated list of quoted tag entries per record (e.g.
`"Home Type|House","Niche|Home & Garden","Crm Adriana"`) — no `LIKE` /
`CONTAINS` operator is supported by the API (confirmed by testing several
operator syntaxes; all either no-op or 400).

So tag containment is filtered **client-side** while streaming pages to
CSV, via `--require-tag` (case-insensitive exact match against one entry in
the tag list, repeatable for OR):

```bash
python3 src/creatoriq_export.py export \
  --endpoint https://apis.creatoriq.com/crm/v1/api/publishers \
  --auth-header x-api-key --api-key-env CREATORIQ_API_KEY \
  --data-path PublisherCollection --total-path total \
  --filter Status=Active \
  --require-tag "Crm Adriana" \
  --fields Id,NetworkPublisherId,PublisherId,PublisherName,Status,StatusCategory,...,Tags,TagNames,... \
  --max-size 1000 --min-interval 0.25 \
  --out output/creatoriq_active_members_crm_adriana.csv
```

## Output

- [`output/creatoriq_active_members.csv`](output/creatoriq_active_members.csv)
  — all 42,990 `Status=Active` publishers/members, 34 columns.
- [`output/creatoriq_active_members_crm_adriana.csv`](output/creatoriq_active_members_crm_adriana.csv)
  — the 11,662 `Status=Active` publishers that also carry the exact tag
  `Crm Adriana` (case-insensitive; covers the `Crm Adriana` / `CRM Adriana`
  casing variants observed in the live data), scanned out of all 42,990
  active records.

## Tool reference

```
python3 src/creatoriq_export.py --help
python3 src/creatoriq_export.py probe --help
python3 src/creatoriq_export.py export --help
```

The tool is intentionally generic (endpoint, auth header, page/size param
names, data/total JSON paths, filters, and field projection are all CLI
flags), so it can be pointed at other CreatorIQ collections or other
paginated JSON APIs with a similar shape.
