# Put the dashboard online (get a link you can show)

**No terminal. No localhost.** You get a normal website link like  
`https://your-app.streamlit.app` that you can open in meetings and share with your team.

**Internal only** — creators don't see it unless you send them the link.

---

## What you need

- A **GitHub account** with access to `acosentino-svg/Creator-IQ-export`
- About **10 minutes**
- **Streamlit Community Cloud** (free): https://share.streamlit.io

---

## Step-by-step

### 1. Open Streamlit Cloud

Go to: **https://share.streamlit.io**

Click **Sign in** → sign in with **GitHub** (same account that can see the repo).

---

### 2. Create a new app

1. Click **Create app** (or **New app**).
2. **Repository:** `acosentino-svg/Creator-IQ-export`
3. **Branch:** `main` (recommended) or `cursor/internal-activation-dashboard-4859`
4. **Main file path:** `streamlit_app.py` (repo root) **or** `app/streamlit_app.py` — both work
5. Click **Deploy**.

Wait 2–5 minutes while it builds.

**Important:** In app **Settings → General**, set **Python version** to **3.12** (not 3.14). Wrong Python versions can cause `ModuleNotFoundError: plotly` on deploy.

---

### 3. You get a link

When it's done, Streamlit shows a URL like:

`https://creator-iq-export-xxxxx.streamlit.app`

**Bookmark that.** That's your dashboard. Open it in Chrome/Safari anytime — same as any website.

---

## First time: demo data (no API key)

By default it runs with **sample data** so you can show every page immediately:

- Activation funnel
- Creator Activity (with Last Email Sent, Last Email Clicked, etc.)
- Chat Assistant
- Outreach Queue

Fine for **demos and walkthroughs** with your team.

---

## Later: plug in real CreatorIQ data

In Streamlit Cloud → your app → **Settings** → **Secrets**, paste:

```toml
CREATORIQ_API_KEY = "your-key-here"
CREATORIQ_BASE_URL = "https://api.creatoriq.com/api"
CREATORIQ_DASHBOARD_MODE = "live"
```

Then set up a scheduled job to refresh data (ask someone technical, or we can add GitHub Actions later).

---

## Who can see it?

| Audience | Can see it? |
|----------|-------------|
| You + teammates you share the link with | Yes |
| Creators in the program | **No** (unless you send them the URL) |
| Public internet | Only if the repo/app is public; keep link private for internal use |

---

## If deploy fails or a page spins forever

1. Confirm branch is **`main`** (after PR #8 merge).
2. Confirm main file is **`streamlit_app.py`** (repo root) or **`app/streamlit_app.py`**.
3. **Settings → General → Python version = 3.12** (not 3.14 — fixes many `ModuleNotFoundError` including plotly).
4. **Manage app → Reboot app** (or **Clear cache and reboot**).
5. **Settings → General → Python version = 3.12** (not 3.14).
6. **Manage app → Reboot app** after every merge that touches `requirements.txt`.
7. If you see **`ModuleNotFoundError: plotly`**, confirm `requirements.txt` on `main` lists `plotly==5.24.1` (no `-e .` line) and reboot again.
