# Pre-built halo effect exports (Google Sheets)

| File | Contents |
|------|----------|
| `halo_effect_google_sheets_bundle.zip` | Full posted export date range |
| `halo_effect_jul_sep_2026_google_sheets.zip` | **Jul 1 – Sep 30, 2026** posts only |

**Download:** open this folder on GitHub (branch `cursor/selection-impact-analytics-0773`), click the `.zip`, then **Download**.

**Into Google Sheets:** unzip on your computer → [sheets.google.com](https://sheets.google.com) → **File → Import → Upload** → `01_data_quality.csv`, then import `02`–`07` as **new sheets**.

Regenerate: Boosting app **Google Sheets Export** (upload both CSVs + set dates) or:

`PYTHONPATH=src python3 scripts/export_halo_effect_google_sheets.py --posted ... --selected ... --output-dir ./out --post-date-start 2026-07-01 --post-date-end 2026-09-30`
