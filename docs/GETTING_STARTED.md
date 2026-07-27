# Getting Started (plain English)

This guide is for running the **internal Creator Activation Dashboard** on your
computer. You do not need to know Git or Python deeply — follow the steps in
order.

## What this dashboard does

It is a **private website on your computer** (not creator-facing) that helps you
answer:

- How many creators are active vs. inactive?
- Who linked but never posted? (good email list)
- Who posted but never linked? (missing commission)
- Who went quiet and needs a follow-up?
- Who is posting more than usual this week?

It works **right away with fake sample data** so you can click around before
connecting CreatorIQ.

## Step 1 — Open a terminal in this project folder

In Cursor: **Terminal → New Terminal**. Make sure the path ends in
`Creator-IQ-export` (or whatever you named this folder).

## Step 2 — Install Python packages (one time)

Copy and paste these lines, pressing Enter after each block:

```bash
pip install -r requirements.txt
pip install -e .
```

If `pip` is not found, try `pip3` instead.

## Step 3 — Start the dashboard

```bash
streamlit run app/streamlit_app.py
```

Your browser should open to something like `http://localhost:8501`.

If it does not open automatically, click the link Streamlit prints in the
terminal.

**To stop the dashboard:** go back to the terminal and press `Ctrl+C`.

## Step 4 — Click around (demo mode)

With no API key, the app uses **realistic fake data** (~220 creators). Try these
pages in the left sidebar:

| Page | What to look for |
|------|------------------|
| **Dashboard Overview** | Total / active / never activated counts |
| **New Activations** | First-time posters and linkers; "linked but never posted" |
| **Email Engagement** | Your three outreach segments in one place |
| **Went Dark** | Who to re-engage, with a suggested next step |
| **Creator Activity** | Full table — use **Download CSV** for email lists |

Use the **sidebar** to change the date range and what counts as "Active" or
"Went Dark."

## Step 5 — Connect real CreatorIQ data (when ready)

1. Ask your CreatorIQ contact for an **API key**.
2. Copy `.env.example` to a new file named `.env` (same folder).
3. Open `.env` and replace `replace-me` with your real API key.
4. Change `CREATORIQ_DASHBOARD_MODE=demo` to `CREATORIQ_DASHBOARD_MODE=live`.
5. Pull data into the local cache:

   ```bash
   python scripts/refresh_data.py
   ```

6. Restart Streamlit (Step 3).

**Important:** The first live sync is capped to 10 campaigns by default (see
`config/settings.yaml`). That keeps the first test small. Raise `max_campaigns`
once you confirm it works.

**Schedule refreshes:** Run `python scripts/refresh_data.py` on a timer (e.g.
every night) so the dashboard always shows fresh data without slowing down page
loads.

## Step 6 — Share with your team (optional)

- **Easiest:** [Streamlit Community Cloud](https://streamlit.io/cloud) — connect
  this GitHub repo, add your API key as a "secret," deploy.
- **On a company server:** use the `Dockerfile` in this repo (ask IT if needed).

## Common issues

| Problem | Fix |
|---------|-----|
| `streamlit: command not found` | Run `pip install streamlit` or use `python -m streamlit run app/streamlit_app.py` |
| Page is empty after switching to live | Run `python scripts/refresh_data.py` first |
| Link counts look wrong on live data | CreatorIQ may not expose link-creation events — see README "data-quality caveats" |
| Email opens all show zero | CreatorIQ in-app "read" flags are often empty — import opens from your email tool later |

## Where to get help

- Full technical README: [`README.md`](../README.md)
- How the pieces fit together: [`ARCHITECTURE.md`](ARCHITECTURE.md)
