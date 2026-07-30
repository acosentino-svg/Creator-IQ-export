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

1. Confirm branch is **`cursor/internal-activation-dashboard-4859`** (or **`main`** after PR #7 is merged).
2. Confirm main file is **`app/streamlit_app.py`** exactly.
3. **Reboot the app:** Streamlit Cloud → lower-right **Manage app** → **Reboot app** (clears a stuck sync).
4. On **Data & Settings**, use **Quick sync** first — **not** Full sync. A full ~42k pull can run for **many hours** and looks like the page is frozen.
5. Check the build log on Streamlit for red errors — send a screenshot to your technical contact or this chat.

---

## Optional: merge the PR first

If you **merge PR #7** on GitHub into `main`, you can deploy from branch **`main`** instead so you don't need the long branch name.

PR: https://github.com/acosentino-svg/Creator-IQ-export/pull/7
