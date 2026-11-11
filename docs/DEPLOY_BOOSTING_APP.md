# Boosting Program dashboard (separate Streamlit app)

Use this when you want the same idea as **creator-activity-dash.streamlit.app**, but **only the Wayfair Boosting program** — not the whole creator activation Command Center.

The activation dashboard (`streamlit_app.py`) tracks enrollments, links, email, went-dark, etc. across the full program. This app tracks **boosting scorecard** metrics: eligible content, selection, paid spend, ROAS, retention, and funnel stages for campaign **2206666** and **WBP** creators.

## Pages in this app

| Page | What it shows |
|------|----------------|
| **Home** | Executive KPIs, program insights, trends |
| **Data Source** | Sync status, API refresh, CSV supplement |
| **Creator Health** | Monthly creator movement and searchable roster |
| **Content Funnel** | Eligible → selected → boosted |
| **Performance** | Spend vs revenue, top creators |
| **Retention** | Month-over-month creator retention |
| **Data Quality** | Coverage and rule checks |

## Deploy on Streamlit Community Cloud

1. Go to https://share.streamlit.io → **Create app**
2. **Repository:** `acosentino-svg/Creator-IQ-export`
3. **Branch:** `main` (or your feature branch while testing)
4. **Main file path:** `creator_boosting_dash.py` or `boosting_app.py` (identical)
   - Do **not** use `streamlit_app.py` — that deploys the full activation dashboard
5. **App URL (suggested):** rename the app to something like `creator-boosting-dash` so it pairs with `creator-activity-dash`
6. **Settings → General → Python version:** **3.12** (not 3.14)
7. **Secrets:**

```toml
CREATORIQ_DASHBOARD_MODE = "live"
CREATORIQ_API_KEY = "your-key"
CREATORIQ_BASE_URL = "https://api.creatoriq.com/api"
```

8. **Deploy** and wait for the build to finish.

**Demo mode:** omit secrets (or set `CREATORIQ_DASHBOARD_MODE = "demo"`) and use **Load sample data** in the sidebar.

## If deploy fails (`ModuleNotFoundError: yaml` or `plotly`)

1. Confirm **Python 3.12** in app Settings → General.
2. **Manage app → Clear cache and reboot**.
3. Do not add `-e .` to `requirements.txt`.

## Sync data (live mode)

On first load the app **auto-syncs** boosting content from CreatorIQ when the cache is empty or stale (see `config/settings.yaml` → `boosting.auto_sync_on_load`).

You can also:

1. Click **Refresh from CreatorIQ** in the sidebar
2. Upload a monthly CSV supplement on **Data Source** (paid-media fields not in the API)

## Two apps, two URLs

| App | Main file | Audience / scope |
|-----|-----------|------------------|
| Activation Command Center | `streamlit_app.py` | Whole creator program (activity, email, outreach) |
| **Boosting Program** | **`creator_boosting_dash.py`** or **`boosting_app.py`** | **Boosting partnership scorecard only** |

## Run locally

```bash
bash start_boosting_dashboard.sh
# or:
streamlit run app/boosting_standalone/streamlit_app.py
```
