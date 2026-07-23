# Automating the Boosting Partnership Process

Short answer: **yes, most of this is automatable** — probably 70-80% of the manual
clicking/copy-pasting goes away, now that CreatorIQ API access is in the picture too.
A few pieces (deciding *which* content is worth boosting, and actually hitting "send"
in CreatorIQ) should stay human for now. This folder contains a working starter kit
([`apps-script/`](apps-script/)) plus the reasoning below.

## Feasibility, mapped to your walkthrough

| Step | Automatable? | How |
|---|---|---|
| **0. New month setup** | ✅ Fully | `startNewMonth()` creates a new tab named like **"July 2026 Gift Card Cost Tracker"** (copies headers + Gift Card Amount formula from the template or prior month), sets it as the active month, and optionally hides the previous month's tab. You still manually swap in a comp-specific formula for special months (Cranberry Cashout, June Jackpot, etc.) — that decision needs a human, but the *mechanics* of copying are automated. |
| **1. Sourcing content into the Boosting Tracker** | ⚠️ Partial (not yours to automate) | Since another team decides + adds the content, this step stays theirs. What *is* solved here: you said you "check that sheet daily" to catch what they've tagged — see **"Replacing the daily check"** below, which removes the need to remember to look. |
| **2. Notify creators + build the message sheet** | ✅ Mostly | `syncBoostingTracker()` scans the Boosting Tracker for un-notified rows, decides "new creator this month" vs. "already boosted this month" by looking up the active gift card month tab, writes the row into the right sheet (New Creators vs. Follow-Up), and updates piece counts on the tracker. It also fills First/Last Name from the **Names** tab. `draftNewCreatorMessages()` / `draftFollowUpMessages()` then fill in your exact message templates — see the Gemini note below. |
| **3. Collecting emails/links from replies** | ⚠️ Links: strong candidate once endpoints confirmed. Email: still needs the creator's confirmation, by design | CreatorIQ's "email on file" is the creator's account/login email, not necessarily where they want a gift card sent — your message explicitly asks them to confirm that separately, so the automation deliberately does **not** auto-fill the Email Address column from CreatorIQ (it only leaves a cell note as a hint). What's still worth automating: `ciqListInboundMessagesSince_()` + `extractEmailAndLinksFromReply_()` in `CreatorIQ.gs` could poll for inbound replies and use Gemini to pull the *confirmed* email + links out of the free text — this is a case where the LLM genuinely earns its keep, unlike the outbound mail-merge. Not wired into the automatic sync yet — see **Next step: confirm your CreatorIQ endpoints** below. |
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

## Replacing the daily check

You mentioned you check the sheet daily (or wait to get tagged) since another
team adds content but doesn't tell you it's ready. Rather than build a
Drive-comment watcher (possible, but heavier: needs broader Drive OAuth
scopes for not much extra benefit), the starter kit solves the actual problem
— *making sure nothing sits unprocessed* — with a hands-off trigger:

- **Boosting Automation → "Turn ON automatic hourly sync"** installs a
  time-driven trigger that runs `syncBoostingTracker()` +
  drafts the messages **every hour**, whether or not you have the sheet open.
- If (and only if) it found something new, it emails you a one-paragraph
  summary (counts of new creators / follow-ups / auto-fixed dupes) with a
  link straight to the sheet.
- You still review and actually send each drafted message — this just
  removes the "did I miss something today" anxiety and the need to
  re-open the sheet speculatively. Turn it off any time from the same menu.

## What I deliberately did NOT automate

- **Deciding what content is worth boosting.** Creative judgment, not a
  computable rule.
- **Actually sending the message in CreatorIQ.** `ciqSendMessage_()` exists
  as a placeholder, but it's not wired into the automatic sync — "final human
  review before it goes to a real creator" seems like a good line to keep for
  now, even once the endpoint is confirmed. Easy to flip on later if you'd
  rather it be fully hands-off.
- **Trusting the dupe auto-fill blindly.** It fills blanks and flags itself
  with a note — you still get the final look before it becomes a payment
  decision.
- **Auto-filling the Email Address column from CreatorIQ.** Their email on
  file is an account/login email, not necessarily where they want a gift card
  sent — the outreach message asks them to confirm that on purpose. The
  lookup only leaves a note as a hint; the actual column stays empty until a
  creator's confirmed reply goes in, exactly like today.
- **Silently marking a creator as "notified."** The script uses a distinct
  marker (`Queued (auto)`) instead of writing `Yes` straight away, so "Yes"
  still only ever means a human actually confirmed the message went out. You
  can wire up `onEditMarkSent` (see `Automation.gs`) so checking a "Sent?" box
  on the message sheet flips it to `Yes` for you automatically — that part's
  optional and off by default.

## Important: three separate files, not one

The walkthrough lists **Boosting Program Tracker**, **New Boosted Creators
Automated Message**, and **Follow-Up Boosted Creators Automated Message** as
separate items — they're actually three separate Google Sheets files, not
tabs inside one spreadsheet. The script is attached to (bound to) the
Tracker, so to reach the other two it needs to be told their exact address —
that's what `EXTERNAL_SHEET_IDS` in `Config.gs` is for. Paste each file's URL
in there once and the rest of the project doesn't need to know the
difference between "a tab in this file" and "a tab in a different file."

One consequence: because the script now reaches into other files by
address, Google's permission screen asks for full "access your Google
Sheets" rather than the narrower "just this one file" version — there isn't
an official permission level that means "just these three specific files."

## Setup (Google Sheets → Apps Script, ~10 minutes)

1. Open the **Boosting Program Tracker** spreadsheet.
2. **Extensions → Apps Script**.
3. Delete the default `Code.gs` stub, then create five files matching the
   names in [`apps-script/`](apps-script/) (`Config.gs`, `Helpers.gs`,
   `Gemini.gs`, `CreatorIQ.gs`, `Automation.gs`) and paste in the matching
   contents. Also open **Project Settings → check "Show `appsscript.json`
   manifest file in editor"** and replace its contents with
   [`apps-script/appsscript.json`](apps-script/appsscript.json) — it declares
   the extra permissions (send email, call external APIs) the automatic sync
   needs.
4. Save, then reload the spreadsheet. A **"Boosting Automation"** menu will
   appear next to Extensions.
5. **Boosting Automation → Setup → Set CreatorIQ API key** (your key — never
   paste it directly into the script files, use this prompt so it's stored in
   Script Properties instead).
6. (Optional, only needed for the Gemini polish/extraction steps) **Boosting
   Automation → Setup → Set Gemini API key**, using a key from
   [aistudio.google.com/apikey](https://aistudio.google.com/apikey).
7. Try it on a **copy** of the sheet first (File → Make a copy) before running
   it against the live tracker, since it does write back into your sheet.

### Monthly rhythm with the new menu

1. **Boosting Automation → 1. Start new month** (once, at the top of the
   month).
2. **Turn ON automatic hourly sync** once, and leave it on — this replaces
   the daily manual check. It runs Steps 2/4 + drafts messages every hour and
   only emails you when there's actually something new to review.
3. Review the drafted messages in the New Creators / Follow-Up sheets, copy
   into CreatorIQ, send, then check the row's "Sent?" box.
4. Once you've collected any still-missing links/emails, paste them into the
   tracker as you do today.
5. **4. End-of-month export** when you're closing out the month.

## Next step: confirm your CreatorIQ endpoints

You mentioned you already have CreatorIQ API access — that's the single
biggest lever left, since it can shrink Step 3 down to almost nothing. I
wired the integration point (`CreatorIQ.gs`) so the rest of the project
already calls it, but the actual endpoint paths in `CIQ_CONFIG` are
best-guess placeholders (CreatorIQ's public docs at apidocs.creatoriq.com are
behind a login I don't have). To finish wiring it up, whichever of these you
can share would let me fill in the real thing instead of guesses:

1. **Base URL + auth scheme** — e.g. is it a `Bearer` token, a custom header
   like `X-API-Key`, something else? (Share the pattern, not the actual key —
   put the key itself in Cursor's Secrets or the Script Properties prompt.)
2. **A "get creator/publisher by handle" endpoint** — response shape,
   especially whether it includes an email on file. This is what lets Step 2
   pre-fill First/Last Name + Email without waiting on a reply.
3. **Whether there's a messages/conversations endpoint** — specifically (a)
   one to list inbound replies since a timestamp, and (b) one to send a
   message — so "notify" and "collect the reply" could both move off manual
   copy/paste in CreatorIQ's UI.
4. If you have a Postman collection, OpenAPI/Swagger export, or even a couple
   of example `curl` requests you've already gotten working, that's the
   fastest way for me to match the real shape exactly.

Once I have that, `ciqFindPublisherByHandle_` and the two message functions
in `CreatorIQ.gs` become real instead of placeholders, and I can wire
`ciqListInboundMessagesSince_` + `extractEmailAndLinksFromReply_` into the
hourly sync so replies start flowing into the tracker automatically too.

## Other limitations

1. **This starter kit assumes today's column layout.** The Monthly Gift Card
   Cost Tracker's per-month schema has changed over time (some months have
   `Creator Name` only, later ones add `Creator Handle`/`First Name`/`Last
   Name`/`Publisher Name`/`URL`). The script reads headers by name rather than
   fixed column letters specifically so it survives that kind of drift, but a
   completely new column being added mid-month may still need a one-line
   tweak in `Config.gs`.
2. **Security note, unrelated to automation:** the Boosting Partnership 101
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
