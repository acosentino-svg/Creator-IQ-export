# Standalone Boosting Program Scorecard (separate Streamlit app)

This is **not** the Activation Command Center. It is **only** the Boosting program scorecard with four tabs:

- **Content Raw**
- **Creator Monthly**
- **Program Monthly**
- **Dashboard**

## Deploy on Streamlit Cloud (Boosting-only app)

1. Go to https://share.streamlit.io → **Create app**
2. Repository: `acosentino-svg/Creator-IQ-export`
3. Branch: `main`
4. **Main file path:** `boosting_app.py`
   - Do **not** use `streamlit_app.py` — that is the whole-program activation dashboard
5. Python version: **3.12**
6. Secrets:

```toml
CREATORIQ_DASHBOARD_MODE = "live"
CREATORIQ_API_KEY = "your-key"
CREATORIQ_BASE_URL = "https://api.creatoriq.com/api"
```

7. Deploy → you get a **new URL** (e.g. `boosting-scorecard-xxxxx.streamlit.app`)

When you open that URL, you land directly on the Boosting scorecard with the four tabs at the top.

## Sync data

1. In the app, expand **Data sources & sync**
2. Click **Sync Boosting from CreatorIQ API**
3. Or upload a monthly CSV on the **Content Raw** tab

## Two apps, two URLs

| App | Main file | What you see |
|-----|-----------|--------------|
| Activation dashboard | `streamlit_app.py` | Whole creator program (Activation Command Center, etc.) |
| **Boosting scorecard** | **`boosting_app.py`** | **Boosting program only — 4 tabs** |
