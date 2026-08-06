# Standalone Creator Geography app (separate Streamlit deployment)

This is **not** the activation dashboard. It only shows:

- US state map (home)
- Top states & cities
- Load data (GitHub API sync upload, CSV, optional in-app sync)

## Deploy on Streamlit Cloud (second app)

1. Go to https://share.streamlit.io → **Create app**
2. Repository: `acosentino-svg/Creator-IQ-export`
3. Branch: `main`
4. **Main file path:** `app/geography_standalone/streamlit_app.py`
   - Do **not** use `streamlit_app.py` (that is the activation dashboard)
5. Python version: **3.12**
6. Secrets (same as activation app):

```toml
CREATORIQ_DASHBOARD_MODE = "live"
CREATORIQ_API_KEY = "your-key"
CREATORIQ_BASE_URL = "https://api.creatoriq.com/api"
```

7. Deploy → you get a **new URL** (e.g. `creator-geography-xxxxx.streamlit.app`)

## Load 43k+ creators (no Mac Terminal)

1. GitHub → Settings → Secrets → Actions → add `CREATORIQ_API_KEY` and `CREATORIQ_BASE_URL`
2. GitHub → Actions → **Sync enrolled creators (API geography)** → **Run workflow**
3. Wait until the **whole workflow** shows a green checkmark (many sequential chunks; can take 30–90+ minutes total)
4. Download **warehouse-db** artifact → `warehouse.db`
5. Open geography app → **Load Data** → upload `warehouse.db`

If a run **cancels around 15 minutes**, your GitHub org may cap job length — the workflow now splits sync into short chunks automatically after you merge the latest `main`. Do **not** use Streamlit **Quick sync** (also 15 minutes) for the full program.

## Two apps, same repo

| App | Main file | Purpose |
|-----|-----------|---------|
| Activation dashboard | `streamlit_app.py` | Funnel, chat, went dark, etc. |
| Creator geography | `app/geography_standalone/streamlit_app.py` | Map + rankings only |
