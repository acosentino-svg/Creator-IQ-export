# Boosting “creator activity” dashboard (your own Streamlit app)

You want something **like [creator-activity-dash.streamlit.app/#active-creator-report](https://creator-activity-dash.streamlit.app/#active-creator-report)**:

- **Activation** tab with **Active creator report** table
- Filters: **Must have posts**, **Must have links**, **Must have transactions**, **Search creator**
- Sidebar: **Refresh window (days)**, **Activity window** (from/to dates), **Refresh from CreatorIQ**
- **Retention** tab (boosting monthly retention)

**Only for the Boosting program** (WBP or campaign 2206666). You **do not** need edit access to that existing app.

This repo has a **second deployment** that reuses the same pages and metrics code, with data scoped to:

- Creators tagged **WBP** in CreatorIQ, and/or
- Creators on the **2206666** campaign roster (**Wayfair Creators Boosting Partnership**)

Run **Refresh from CreatorIQ** on the boosting scorecard app (or a boosting sync) once so the `boosting_roster` cache is populated for roster-only creators with no posts yet.

(Not the separate **scorecard** app — that one is `boosting_app.py` / ROAS and content funnel. Use **this** entry point for the activation-style experience.)

## Deploy (Streamlit Community Cloud)

1. Sign in at https://share.streamlit.io with **your** GitHub account.
2. **Create app** (new app — do not touch the team activation app).
3. **Repository:** `acosentino-svg/Creator-IQ-export` (fork first if you can’t deploy from this repo).
4. **Branch:** `main` (after merge) or the PR branch while testing.
5. **Main file path:** `creator_boosting_activity_dash.py`
6. **Python:** **3.12**
7. **Secrets** (same as activation, if you have them):

```toml
CREATORIQ_DASHBOARD_MODE = "live"
CREATORIQ_API_KEY = "your-key"
CREATORIQ_BASE_URL = "https://api.creatoriq.com/api"
```

8. Deploy → bookmark **your** new `.streamlit.app` URL.

**Demo:** leave mode as `demo` (default) to explore without API keys.

## Local

```bash
streamlit run creator_boosting_activity_dash.py
```

## If you can’t deploy from this repo

1. **Fork** `acosentino-svg/Creator-IQ-export` to your GitHub user.
2. Create the Streamlit app from **your fork**.
3. Point teammates at your new URL, or ask an admin to deploy from `main` with main file `creator_boosting_activity_dash.py`.

## Three related apps (don’t mix main files)

| Goal | Main file |
|------|-----------|
| Whole program (existing team app) | `streamlit_app.py` |
| **Activation UI, boosting cohort only** | **`creator_boosting_activity_dash.py`** |
| Boosting scorecard (ROAS, funnel, retention) | `boosting_app.py` or `creator_boosting_dash.py` |
