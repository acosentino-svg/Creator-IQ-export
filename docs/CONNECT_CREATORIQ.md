# Connect real CreatorIQ data (plain English)

The dashboard does **not** call CreatorIQ on every click. It:

1. **Pulls** data from CreatorIQ on a schedule (or when you click refresh)
2. **Stores** it in a local cache
3. **Shows** that cache in the dashboard

So it is **accurate as of the last sync**, not live second-by-second. For a program your size, **hourly or nightly** refresh is normal.

---

## Step 1 — Get your CreatorIQ API key

Ask your **CreatorIQ account manager** or admin for:

- **API key** (bearer token)
- **Base URL** (usually `https://api.creatoriq.com/api`)
- **Org ID** (only if they say you need it)

---

## Step 2 — Add secrets in Streamlit Cloud

1. Open your app on **share.streamlit.io**
2. Click **Manage app**
3. Open **Settings**
4. Click the **Secrets** tab (left sidebar — not General)
5. Paste this and replace `your-key-here`:

```toml
CREATORIQ_API_KEY = "your-key-here"
CREATORIQ_BASE_URL = "https://api.creatoriq.com/api"
CREATORIQ_DASHBOARD_MODE = "live"
```

6. Click **Save**

Also on **General** tab: set **Python version** to **3.12** (not 3.14).

Reboot the app after saving secrets.

---

## Step 3 — Pull data from CreatorIQ (first time)

After reboot:

1. Open your dashboard URL
2. Go to **Data & Settings** in the sidebar
3. Confirm it says mode **`live`** (not demo)
4. Click **Run refresh now**

**First refresh can take several minutes.** The sidebar should eventually show real sync timestamps.

If refresh fails, check **Manage app → Logs** for red errors.

---

## Step 4 — Confirm it’s real data

On **Activation Command Center**:

- **Total enrolled** should be much larger than ~220
- Sidebar should say **Live mode**, not Demo mode
- **Data & Settings** shows real `last_synced_at` times (not `demo`)

---

## How “real time” works in practice

| What you want | What to do |
|---------------|------------|
| **Fresh enough for daily work** | Click **Run refresh now** each morning, or set up a daily auto-sync (needs IT) |
| **Fresh enough for weekly reviews** | Refresh once per week |
| **True real-time** | Not built in — CreatorIQ API isn’t designed for per-click queries at 42k scale |

**Recommendation:** refresh **once per day** (manual button or scheduled job).

---

## Getting all ~42,000 creators (not just a sample)

The first sync is **capped on purpose** so it doesn’t overwhelm the API:

- Default: **10 campaigns**, **300 email lookups**

To see more of the program, someone technical needs to raise limits in `config/settings.yaml`:

- `max_campaigns` — set higher or `null` for all campaigns
- `max_email_lookups` — raise for more email sent/open/click data
- `campaign_status_filter` — `[]` to include all campaign statuses

At 42k creators this may take **hours** and many API calls — plan with CreatorIQ / engineering.

---

## Email fields (last sent, last clicked)

These come from CreatorIQ **message** data per creator.

**Caveats:**

- CreatorIQ **in-app “read”** flags often don’t match real email opens
- **Clicks** may be missing if email runs through Klaviyo/Mailchimp/etc.
- For best email accuracy, eventually pipe **ESP open/click data** into the same dashboard (future work)

---

## Streamlit Cloud note

When the app **reboots**, the cache may be **empty** until you run **Refresh** again. That’s normal on free Streamlit hosting.

For always-on cached data without re-clicking refresh, you need either:

- A **scheduled sync** (GitHub Actions, cron on a server), or
- **Self-hosted** dashboard on a machine that keeps the database

Ask IT if you need that.

---

## Quick checklist

- [ ] API key from CreatorIQ
- [ ] Secrets added in Streamlit (**Secrets** tab)
- [ ] Python **3.12** in General settings
- [ ] Reboot app
- [ ] **Data & Settings → Run refresh now**
- [ ] Total creators ≠ 220
