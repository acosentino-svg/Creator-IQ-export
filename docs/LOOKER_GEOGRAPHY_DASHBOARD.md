# Creator geography in Looker Studio (no Streamlit)

For **where enrolled creators live** (CRM City / State / Country), Looker Studio is a better fit than Streamlit:

- Read-only maps and bar charts — no app boot time for 43k rows
- Shareable link for leadership
- CreatorIQ data lands in **Google Sheets or BigQuery** first; Looker only visualizes

This repo pulls geography from the CreatorIQ API (`Country`, `State`, `City` on `/publishers`). Looker does not call CreatorIQ directly — you land the table in Sheets or BigQuery first.

---

## Architecture

| Stage | Tool |
|-------|------|
| Extract | **GitHub Actions** (this repo) |
| Store | **Google Sheets** (v1) or **BigQuery** (v2) |
| Visualize | **Looker Studio** |

### Columns (vs ChatGPT’s suggested table)

| Column | CreatorIQ API? | Notes |
|--------|----------------|-------|
| Creator | Yes | `PublisherName` |
| Creator ID | Yes | `Id` |
| City | Yes | CRM |
| State/Region | Yes | CRM |
| Country | Yes | CRM |
| Program Status | Yes | `Status` (Active = enrolled) |
| Latitude / Longitude | **No** | Not on `/publishers` — use `state_code` for US maps |
| Platform / Followers | **No** on roster | Add in v2 via other API calls |

---

## Path A — Google Sheets → Looker (start here)

### 1. Sync via GitHub

1. Repo **Settings → Secrets → Actions** → `CREATORIQ_API_KEY`, `CREATORIQ_BASE_URL`
2. **Actions → Sync enrolled creators (API geography) → Run workflow**
3. Wait for full workflow green (all chunks + export job)
4. Download artifact **`creators-geography-csv`** → `creators_geography.csv`

### 2. Google Sheet

1. [Google Sheets](https://sheets.google.com) → blank spreadsheet
2. **File → Import → Upload** → `creators_geography.csv` → **Replace current sheet**

### 3. Looker Studio

1. [lookerstudio.google.com](https://lookerstudio.google.com) → **Create → Report**
2. **Add data → Google Sheets** → your spreadsheet
3. Charts:
   - **Geo chart (United States)** — Dimension: `state_code`, Metric: Record Count
   - **Bar chart** — top states by count
   - **Table** — `city`, `state_code`, count

### Refresh weekly

Re-run GitHub workflow → download new CSV → Sheets **Import → Replace data at row 1**.

---

## Path B — BigQuery → Looker

Load `creators_geography.csv` into BigQuery, connect Looker to that table. Better for automated schedules at scale.

---

## Export locally (optional)

```bash
python scripts/export_geography_table.py
```

Requires `data/warehouse.db` from a prior sync.

---

## Why Streamlit felt slow

Streamlit reloads and renders on every visit. Looker reads a flat table in Sheets/BigQuery — API sync runs in GitHub, not when someone opens the report.

Use Streamlit for interactive activation tools; use Looker for geography snapshots shared with leadership.
