# Pre-built halo effect exports (Google Sheets)

| File | Contents |
|------|----------|
| `halo_effect_google_sheets_bundle.zip` | Full posted export date range |
| `halo_effect_jul_sep_2026_minimal_google_sheets.zip` | Minimal Jul–Sep bundle (3 tabs) |
| `campaign_2206666_posts_since_july.csv` | **Campaign 2206666** posts from **2026-07-01** onward (CreatorIQ-style columns for halo merge) |

**Download:** open this folder on GitHub (branch `cursor/selection-impact-analytics-0773`), click the file, then **Download**.

**Posted export columns:** `Post Id`, `Creator Name`, `SocialHandle`, `Post Description`, `Post Link`, `Post Date`, `Publisher Id`

Regenerate posted export (requires live `.env` / API key):

`PYTHONPATH=src CREATORIQ_DASHBOARD_MODE=live python3 scripts/export_campaign_posts.py --campaign-id 2206666 --since 2026-07-01 --output exports/campaign_2206666_posts_since_july.csv`

**Into Google Sheets:** [sheets.google.com](https://sheets.google.com) → **File → Import → Upload** → choose `campaign_2206666_posts_since_july.csv` (or unzip a halo `.zip` and import each CSV as new sheets).

Regenerate halo bundles: Boosting app **Google Sheets Export** (upload both CSVs + set dates) or:

`PYTHONPATH=src python3 scripts/export_halo_effect_google_sheets.py --posted ... --selected ... --output-dir ./out --post-date-start 2026-07-01 --post-date-end 2026-09-30`
