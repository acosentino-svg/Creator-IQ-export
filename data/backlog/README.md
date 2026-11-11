# CSV backlog (hybrid with Live API)

The **creator-activity-dash** uses historical CSV exports plus a live CreatorIQ API window.  
The **boosting** app uses the same pattern but **only campaign 2206666** (and WBP roster).

Place exports here (filenames are defaults; override paths in `config/settings.yaml` → `boosting.hybrid.csv_paths`):

| File | Purpose |
|------|---------|
| `links.csv` | Link creation events (must include **PublisherId** + date column) |
| `posts.csv` | Historical posts (campaign id/name or boosting-only export) |
| `transactions.csv` | Dated transactions (PublisherId + date) |
| `publisher_names.csv` | Publisher Id → display name |

Until these files exist, diagnostics show **0** on the CSV side and **API-only** counts after **Refresh from CreatorIQ**.

Transaction totals also use `data/creator_sales_ranking.csv` (lifetime, not dated).
