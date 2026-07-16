# Automating the Boosting Partnership Process

Short answer: **yes, most of this is automatable** — probably 60-70% of the manual
clicking/copy-pasting goes away. A few pieces (deciding *which* content is worth
boosting, and actually hitting "send" in CreatorIQ) should stay human for now. This
folder contains a working starter kit ([`apps-script/`](apps-script/)) plus the
reasoning below.

## Feasibility, mapped to your walkthrough

| Step | Automatable? | How |
|---|---|---|
| **0. New month setup** | ✅ Fully | `startNewMonth()` copies the current month's block (headers + the Gift Card Amount formula, including formatting/highlights) into a new block, sized and positioned automatically. You still manually swap in a comp-specific formula for special months (Cranberry Cashout, June Jackpot, etc.) — that decision needs a human, but the *mechanics* of copying are automated. |
| **1. Sourcing content into the Boosting Tracker** | ⚠️ Partial | Deciding *which* content is good enough to boost is a creative/judgment call — not automated. What *can* be automated: CreatorIQ's own filtered "Reporting → Posts" view already does the sourcing filter; the only gap is someone manually re-typing rows into the tracker. If CreatorIQ has an export/API (see **Limitations** below), a scheduled job could pre-populate candidate rows for a human to approve/reject rather than hand-type. |
| **2. Notify creators + build the message sheet** | ✅ Mostly | `syncBoostingTracker()` scans the Boosting Tracker for un-notified rows, decides "new creator this month" vs. "already boosted this month" by looking up the current month block, writes the row into the right sheet (New Creators vs. Follow-Up), and updates the Gift Card Amount formula automatically. `draftNewCreatorMessages()` / `draftFollowUpMessages()` then fill in your exact message templates — see the Gemini note below. |
| **3. Collecting emails/links from replies** | ⚠️ Partial (biggest open question) | This is the one place true LLM extraction would help most: parsing a free-text reply for an email address + product links. It's very doable in Apps Script (read Gmail via `GmailApp`, or poll CreatorIQ if it has an API) + a Gemini call to extract structured fields — but I didn't wire it up because I don't know whether CreatorIQ exposes an API/webhook for inbound creator messages, or whether replies land in your inbox. See **Limitations**. |
| **4. Ongoing month: new vs. follow-up vs. dupe** | ✅ Mostly | Same `syncBoostingTracker()` run handles all three cases every time you run it. For dupes, it auto-fills the *blank* link/SKU/landing-page/creative-ID fields from the original (first) row sharing the same Unique Identifier — and **never overwrites** a cell that already has something in it. It leaves a note flagging the auto-fill so you can still do your Ctrl+F sanity check, since you mentioned the dupe formulas have broken before and caused real pain — I intentionally kept a human checkpoint here rather than trusting it blindly. |
| **5. EOM close-out** | ✅ Fully | `exportEndOfMonth()` builds a clean tab with every complete creator record (ready for the bulk gift card sheet / campaign import), a running total gift card spend, and a call-out list of anyone still missing an email so you can chase them before month-end. |

## The Gemini step: you probably don't need the LLM at all

Looking closely at your prompt, Gemini isn't doing any "understanding" — it's
doing a **mail merge**: filling `[First Name]`, `[New Pieces of Content Used]`,
`[Gift Card Amount]`, and `[Links]` into a fixed template. That's exactly the
kind of thing that's *more* reliable as plain string substitution than as an LLM
call, because:

- No risk of the model mis-reading a row, skipping a creator, or subtly
  rephrasing a dollar amount.
- No API key, no cost, no latency, no chance of a truncated/garbled batch
  output that you'd have to manually double check anyway (which was part of
  the pain of the "attach sheet → paste prompt → get XX messages" flow).

So the starter kit does the merge with plain templating (`fillTemplate_` in
`Gemini.gs`) by default. I still wired up an actual Gemini API call
(`callGemini_`) in case you want an *optional* "polish" pass for tone — see
`personalizeWithGemini_()` — but it's off by default and not required for the
core workflow to work.

## What I deliberately did NOT automate

- **Deciding what content is worth boosting.** Creative judgment, not a
  computable rule.
- **Actually sending the message in CreatorIQ.** I don't know if CreatorIQ has
  a send API; even if it does, "final human review before it goes to a real
  creator" seems like a good line to keep for now.
- **Trusting the dupe auto-fill blindly.** It fills blanks and flags itself
  with a note — you still get the final look before it becomes a payment
  decision.
- **Silently marking a creator as "notified."** The script uses a distinct
  marker (`Queued (auto)`) instead of writing `Yes` straight away, so "Yes"
  still only ever means a human actually confirmed the message went out. You
  can wire up `onEditMarkSent` (see `Automation.gs`) so checking a "Sent?" box
  on the message sheet flips it to `Yes` for you automatically — that part's
  optional and off by default.

## Setup (Google Sheets → Apps Script, ~10 minutes)

1. Open the **Boosting Program Tracker** spreadsheet.
2. **Extensions → Apps Script**.
3. Delete the default `Code.gs` stub, then create four files matching the
   names in [`apps-script/`](apps-script/) (`Config.gs`, `Helpers.gs`,
   `Gemini.gs`, `Automation.gs`) and paste in the matching contents.
4. Save, then reload the spreadsheet. A **"Boosting Automation"** menu will
   appear next to Extensions.
5. (Optional, only needed for the Gemini polish step) **Boosting Automation →
   Setup → Set Gemini API key**, using a key from
   [aistudio.google.com/apikey](https://aistudio.google.com/apikey).
6. Try it on a **copy** of the sheet first (File → Make a copy) before running
   it against the live tracker, since it does write back into your sheet.

### Monthly rhythm with the new menu

1. **Boosting Automation → 1. Start new month** (once, at the top of the
   month).
2. Whenever new content gets tagged in the Boosting Tracker: **2. Sync new
   content**. Run this as often as you like — it only touches rows it hasn't
   already queued or that aren't already marked `Yes`.
3. **3a / 3b. Draft messages** for whichever sheet has new queued rows.
   Copy/paste the drafted column into CreatorIQ (or wire up automatic Gmail
   drafts — happy to add that if useful).
4. Once you've collected emails/links, paste them into the tracker as you do
   today (this part still needs a human unless we solve #3 below).
5. **4. End-of-month export** when you're closing out the month.

## Limitations / open questions before going further

1. **CreatorIQ API access is the single biggest lever left.** If CreatorIQ
   exposes any API or webhook for (a) pulling qualifying posts by campaign/hashtag,
   or (b) reading inbound creator replies, or (c) sending messages, most of
   Steps 1, 2, and 3 could become close to hands-off. Worth a quick check with
   whoever administers your CreatorIQ instance/Wayfair IT.
2. **Where creator replies land.** If they mostly land in an email inbox
   (rather than CreatorIQ DMs), a Gmail-based Apps Script trigger + a small
   Gemini extraction call (pull email + links out of free text) is very
   buildable with no new infrastructure. If they land in CreatorIQ, it depends
   on point 1.
3. **This starter kit assumes today's column layout.** The Monthly Gift Card
   Cost Tracker's per-month schema has changed over time (some months have
   `Creator Name` only, later ones add `Creator Handle`/`First Name`/`Last
   Name`/`Publisher Name`/`URL`). The script reads headers by name rather than
   fixed column letters specifically so it survives that kind of drift, but a
   completely new column being added mid-month may still need a one-line
   tweak in `Config.gs`.
4. **Security note, unrelated to automation:** the Boosting Partnership 101
   doc has a plaintext CreatorIQ username/password in it. Worth moving that to
   a password manager / shared vault rather than a doc, especially if this doc
   gets shared with new creators/partners as the walkthrough describes.

## If you want to go further: n8n

Since there's already an n8n instance available internally, a lot of this same
logic (plus the CreatorIQ + Gmail polling pieces once #1/#2 above are answered)
could live there instead of Apps Script — n8n gives you a visual workflow,
run history/retries, and easier credential management than Script Properties.
Apps Script is the faster path to "working today" since it needs zero new
infra; n8n is the better path if this grows into something with more moving
parts (API polling, retries, Slack notifications, etc.). Happy to build the
n8n version if you'd rather start there.
