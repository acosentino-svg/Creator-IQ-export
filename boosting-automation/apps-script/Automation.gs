/**
 * Automation.gs
 * Menu + the five process steps from the walkthrough, translated into code.
 * Run these from the "Boosting Automation" menu that appears when the
 * spreadsheet opens (see onOpen below).
 */

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Boosting Automation')
    .addItem('1. Start new month (Step 0)', 'startNewMonth')
    .addSeparator()
    .addItem('2. Sync new content -> gift card tracker + message sheets (Steps 2 & 4)', 'syncBoostingTracker')
    .addSeparator()
    .addItem('3a. Draft messages: New Creators sheet', 'draftNewCreatorMessages')
    .addItem('3b. Draft messages: Follow-Up sheet', 'draftFollowUpMessages')
    .addSeparator()
    .addItem('4. End-of-month export + completeness check (Step 5)', 'exportEndOfMonth')
    .addSeparator()
    .addItem('Run sync + draft now and email me a summary', 'runScheduledSync')
    .addItem('Turn ON automatic hourly sync (replaces "checking daily")', 'enableAutoSync')
    .addItem('Turn OFF automatic sync', 'disableAutoSync')
    .addSeparator()
    .addItem('Setup: Set Gemini API key (optional, polish only)', 'setGeminiApiKey_')
    .addItem('Setup: Set CreatorIQ API key', 'setCreatorIQApiKey_')
    .addToUi();
}

// ---------------------------------------------------------------------------
// Replaces "I check that sheet daily": an hourly trigger runs the sync +
// draft steps automatically and emails a short summary, so new content sits
// pre-processed (queued in the gift card tracker + drafted messages ready)
// whether or not Josh happens to open the sheet that day. He still reviews
// and sends the drafts himself — nothing here sends anything to a creator.
// ---------------------------------------------------------------------------
const AUTO_SYNC_HANDLER = 'runScheduledSync';

function enableAutoSync() {
  disableAutoSync(); // avoid duplicate triggers if run twice
  ScriptApp.newTrigger(AUTO_SYNC_HANDLER).timeBased().everyHours(1).create();
  SpreadsheetApp.getUi().alert('Automatic hourly sync is ON. You\'ll get an email summary whenever there\'s something new to review.');
}

function disableAutoSync() {
  ScriptApp.getProjectTriggers()
    .filter((t) => t.getHandlerFunction() === AUTO_SYNC_HANDLER)
    .forEach((t) => ScriptApp.deleteTrigger(t));
}

function runScheduledSync() {
  const before = { newRows: 0, followUpRows: 0 };
  const summary = syncBoostingTracker(true);
  draftMessagesForSheet_(SHEET_NAMES.NEW_CREATORS_MSG, NEW_CREATOR_PROMPT);
  draftMessagesForSheet_(SHEET_NAMES.FOLLOWUP_MSG, FOLLOWUP_PROMPT);

  if (!summary || (summary.queued === 0 && summary.dupesFixed === 0)) return; // nothing new -> no email noise

  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const body =
    'Boosting Tracker sync just ran automatically:\n\n' +
    '- ' + summary.newCreators + ' brand-new creator(s) queued (New Boosted Creators sheet)\n' +
    '- ' + summary.followUps + ' follow-up piece(s) queued (Follow-Up sheet)\n' +
    '- ' + summary.dupesFixed + ' dupe(s) auto-filled from the original entry (worth a quick Ctrl+F spot-check)\n\n' +
    'Messages have been drafted in both message sheets — review and send from CreatorIQ, ' +
    'then check "Sent?" on each row.\n\n' +
    'Open the tracker: ' + ss.getUrl();

  MailApp.sendEmail(Session.getActiveUser().getEmail(), 'Boosting Tracker: new content ready to review', body);
}

// ---------------------------------------------------------------------------
// Step 0: start a new month in the Monthly Gift Card Cost Tracker
// ---------------------------------------------------------------------------
const ROWS_TO_PROVISION = 400; // how many blank formula rows to seed for the new month

function startNewMonth() {
  const ui = SpreadsheetApp.getUi();
  const sheet = getSheet_(SHEET_NAMES.GIFT_CARD_TRACKER);
  const lastBlock = getCurrentMonthBlock_(sheet);

  const resp = ui.prompt(
    'Start new month',
    'Label for the new month block (e.g. "August" or "August - August Posting Competition"):',
    ui.ButtonSet.OK_CANCEL
  );
  if (resp.getSelectedButton() !== ui.Button.OK) return;
  const label = resp.getResponseText().trim();
  if (!label) return;

  const newStartCol0 = lastBlock.endCol + 1; // 0-based
  const width = lastBlock.width;

  // Label + header row (copies formatting, incl. the yellow "subject to change" highlight).
  sheet.getRange(1, newStartCol0 + 1).setValue(label);
  sheet.getRange(HEADER_ROW.GIFT_CARD_TRACKER_FIELD_ROW, lastBlock.startCol + 1, 1, width)
    .copyTo(sheet.getRange(HEADER_ROW.GIFT_CARD_TRACKER_FIELD_ROW, newStartCol0 + 1, 1, width));

  // Carry the Gift Card Amount formula down for ROWS_TO_PROVISION rows. This is a straight
  // copy/paste (copyTo), so a relative reference like "one cell to the left" shifts correctly
  // into the new block's own "New Pieces of Content Used" column, exactly like doing it by hand.
  const amountOffset = colIndex_(lastBlock.headerIndex, 'Gift Card Amount', true);
  const oldAmountCol = lastBlock.startCol + amountOffset + 1;
  const newAmountCol = newStartCol0 + amountOffset + 1;
  const firstDataRow = HEADER_ROW.GIFT_CARD_TRACKER_FIELD_ROW + 1;
  sheet.getRange(firstDataRow, oldAmountCol, ROWS_TO_PROVISION, 1)
    .copyTo(sheet.getRange(firstDataRow, newAmountCol, ROWS_TO_PROVISION, 1));

  ui.alert(
    'New month "' + label + '" created with ' + width + ' columns (copied from "' + lastBlock.label + '").\n\n' +
    'IMPORTANT: If this month has a different comp/activation (Cranberry Cashout, June Jackpot, etc.), ' +
    'now is the time to manually overwrite the Gift Card Amount formula for that block with the ' +
    'comp-specific version before anyone starts entering creators.'
  );
}

// ---------------------------------------------------------------------------
// Steps 2 & 4: scan Boosting Tracker, classify each unhandled row, and either
// (a) route brand-new creators to the New Creators message sheet, or
// (b) route already-boosted-this-month creators to the Follow-Up sheet, or
// (c) auto-fill dupes from the original entry and skip messaging entirely.
// ---------------------------------------------------------------------------
function syncBoostingTracker(silent) {
  const trackerSheet = getSheet_(SHEET_NAMES.BOOSTING_TRACKER);
  const lastRow = trackerSheet.getLastRow();
  const lastCol = trackerSheet.getLastColumn();
  const headers = trackerSheet.getRange(HEADER_ROW.BOOSTING_TRACKER, 1, 1, lastCol).getValues()[0];
  const headerIndex = buildHeaderIndex_(headers);
  ['creator name', 'content used', 'creator notified', 'unique identifier'].forEach((h) => colIndex_(headerIndex, h, true));

  const firstDataRow = HEADER_ROW.BOOSTING_TRACKER + 1;
  const numRows = lastRow - HEADER_ROW.BOOSTING_TRACKER;
  if (numRows <= 0) { toast_('No rows in ' + SHEET_NAMES.BOOSTING_TRACKER); return; }
  const values = trackerSheet.getRange(firstDataRow, 1, numRows, lastCol).getValues();

  const giftSheet = getSheet_(SHEET_NAMES.GIFT_CARD_TRACKER);
  const block = getCurrentMonthBlock_(giftSheet);
  colIndex_(block.headerIndex, 'New Pieces of Content Used', true);
  colIndex_(block.headerIndex, 'Gift Card Amount', true);

  const newRows = [];
  const followUpRows = [];
  let dupesFixed = 0, queued = 0;

  for (let i = 0; i < values.length; i++) {
    const row = values[i];
    const sheetRow = firstDataRow + i;
    const creatorName = row[headerIndex['creator name']];
    const contentUsed = row[headerIndex['content used']];
    const notified = row[headerIndex['creator notified']];

    if (!creatorName || normalizeHandle_(creatorName) === 'example entry') continue;
    if (!contentUsed || String(contentUsed).trim() === '') continue;

    const notifiedNorm = normalizeHeader_(notified);
    if (ALREADY_HANDLED_VALUES.indexOf(notifiedNorm) !== -1) continue;
    if (notifiedNorm === normalizeHeader_(QUEUED_MARKER)) continue;

    const isDupe = DUPE_MARKERS.some((m) => notifiedNorm.indexOf(m) !== -1);
    if (isDupe) {
      if (fillDupeLinks_(trackerSheet, headerIndex, values, i, sheetRow)) dupesFixed++;
      continue;
    }

    const handle = String(creatorName).trim();
    const linksIdx = headerIndex['storefront links provided'];
    const favLinksIdx = headerIndex["fav's list + affiliate links provided"];
    const links = (linksIdx != null && row[linksIdx]) || (favLinksIdx != null && row[favLinksIdx]) || contentUsed;

    const existing = findRowByHandleInBlock_(giftSheet, block, handle);
    if (existing) {
      const currentPieces = Number(existing['new pieces of content used']) || 0;
      const newTotal = currentPieces + 1;
      const newPiecesCol = block.startCol + colIndex_(block.headerIndex, 'New Pieces of Content Used', true) + 1;
      giftSheet.getRange(existing._sheetRow, newPiecesCol).setValue(newTotal);
      SpreadsheetApp.flush();
      const amountCol = block.startCol + colIndex_(block.headerIndex, 'Gift Card Amount', true) + 1;
      const newAmount = giftSheet.getRange(existing._sheetRow, amountCol).getValue();
      followUpRows.push({
        handle: handle,
        firstName: existing['first name'] || '',
        lastName: existing['last name'] || '',
        newPieces: 1, // "new pieces, not total" per the walkthrough
        amount: newAmount,
        email: existing['email address'] || '',
        links: links,
      });
    } else {
      // Try CreatorIQ first so a brand-new creator can skip straight to "confirmed" if
      // their name/email are already on file — falls back to blank (old "ask them" flow)
      // if the lookup fails or isn't configured yet. See CreatorIQ.gs.
      const profile = ciqFindPublisherByHandle_(handle);
      const targetRow = findFirstEmptyRowInBlock_(giftSheet, block);
      writeNewBlockRow_(giftSheet, block, targetRow, {
        handle: handle,
        newPieces: 1,
        firstName: profile ? profile.firstName : '',
        lastName: profile ? profile.lastName : '',
        email: profile ? profile.email : '',
      });
      SpreadsheetApp.flush();
      const amountCol = block.startCol + colIndex_(block.headerIndex, 'Gift Card Amount', true) + 1;
      const newAmount = giftSheet.getRange(targetRow, amountCol).getValue();
      newRows.push({
        handle: handle,
        firstName: profile ? profile.firstName : '',
        lastName: profile ? profile.lastName : '',
        newPieces: 1,
        amount: newAmount,
        email: '', // never pre-filled — see the note left on the gift card tracker cell; wait for their confirmed reply
        links: links,
      });
    }

    trackerSheet.getRange(sheetRow, headerIndex['creator notified'] + 1).setValue(QUEUED_MARKER);
    queued++;
  }

  appendToMessageSheet_(SHEET_NAMES.NEW_CREATORS_MSG, newRows);
  appendToMessageSheet_(SHEET_NAMES.FOLLOWUP_MSG, followUpRows);

  if (!silent) {
    toast_(
      'Queued ' + queued + ' row(s) [' + newRows.length + ' new creator, ' + followUpRows.length + ' follow-up], ' +
      'auto-filled ' + dupesFixed + ' dupe(s). Now run step 3a/3b to draft messages.'
    );
  }

  return { queued: queued, newCreators: newRows.length, followUps: followUpRows.length, dupesFixed: dupesFixed };
}

function writeNewBlockRow_(sheet, block, targetRow, data) {
  const nameKey = ('creator handle' in block.headerIndex) ? 'Creator Handle' : 'Creator Name';
  setBlockCell_(sheet, block, targetRow, nameKey, data.handle);
  if ('first name' in block.headerIndex) setBlockCell_(sheet, block, targetRow, 'First Name', data.firstName || '');
  if ('last name' in block.headerIndex) setBlockCell_(sheet, block, targetRow, 'Last Name', data.lastName || '');
  setBlockCell_(sheet, block, targetRow, 'New Pieces of Content Used', data.newPieces);

  // IMPORTANT: never auto-fill Email Address itself. The creator confirms which
  // email they want the gift card sent to in the outreach message — CreatorIQ's
  // email on file (account/login email) is not guaranteed to be the same one.
  // Leave a note as a hint only, so this column still accurately reflects
  // "confirmed by the creator" and Step 5's missing-email check stays honest.
  if (data.email && 'email address' in block.headerIndex) {
    const offset = colIndex_(block.headerIndex, 'Email Address', true);
    sheet.getRange(targetRow, block.startCol + offset + 1).setNote(
      'CreatorIQ has "' + data.email + '" on file for this handle (their account/login email). ' +
      'Do not treat this as final — the outreach message asks them to confirm which email they ' +
      'want the gift card sent to. Only paste an email into this cell once they\'ve confirmed it.'
    );
  }
}

function setBlockCell_(sheet, block, row, headerName, value) {
  const offset = colIndex_(block.headerIndex, headerName, true);
  sheet.getRange(row, block.startCol + offset + 1).setValue(value);
}

/**
 * Fills a dupe row's link/SKU-type fields from the original (first) row that
 * shares the same Unique Identifier, but ONLY into cells that are currently
 * blank — never overwrites anything a human already entered. Leaves a note
 * flagging it as auto-filled so Josh can still spot-check per the existing
 * "Ctrl+F the identifier" safety habit described in the walkthrough.
 */
function fillDupeLinks_(sheet, headerIndex, values, i, sheetRow) {
  const uidIdx = headerIndex['unique identifier'];
  const uid = values[i][uidIdx];
  if (!uid || String(uid).trim() === '' || String(uid).trim() === '#N/A') return false;

  for (let j = 0; j < i; j++) {
    if (String(values[j][uidIdx]).trim() === String(uid).trim()) {
      const fieldsToCopy = [
        'storefront links provided', "fav's list + affiliate links provided",
        'sku', 'landing page', 'creative asset id', 'string (to be appended to urls)',
      ];
      let filledAny = false;
      fieldsToCopy.forEach((f) => {
        const idx = headerIndex[f];
        if (idx == null) return;
        const destCell = sheet.getRange(sheetRow, idx + 1);
        const destEmpty = String(destCell.getValue() || '').trim() === '';
        const srcVal = values[j][idx];
        if (destEmpty && String(srcVal || '').trim() !== '') {
          destCell.setValue(srcVal);
          filledAny = true;
        }
      });
      if (filledAny) {
        sheet.getRange(sheetRow, headerIndex['creator notified'] + 1).setNote(
          'Auto-filled from row ' + (HEADER_ROW.BOOSTING_TRACKER + 1 + j) + ' (matching Unique Identifier "' + uid + '"). ' +
          'Please spot-check with Ctrl+F before trusting — dupe-detection formulas have broken before.'
        );
      }
      return filledAny;
    }
  }
  return false;
}

function appendToMessageSheet_(sheetName, rows) {
  if (!rows.length) return;
  const sheet = getSheet_(sheetName);
  const headerRow = HEADER_ROW[sheetName === SHEET_NAMES.NEW_CREATORS_MSG ? 'NEW_CREATORS_MSG' : 'FOLLOWUP_MSG'];
  const lastCol = sheet.getLastColumn();
  const headers = sheet.getRange(headerRow, 1, 1, lastCol).getValues()[0];
  const headerIndex = buildHeaderIndex_(headers);
  ['creator handle', 'first name', 'new pieces of content used', 'gift card amount', 'email address', 'links'].forEach((h) => colIndex_(headerIndex, h, true));

  const startRow = sheet.getLastRow() + 1;
  const out = rows.map((r) => {
    const arr = new Array(lastCol).fill('');
    arr[headerIndex['creator handle']] = r.handle;
    arr[headerIndex['first name']] = r.firstName || '';
    if ('last name' in headerIndex) arr[headerIndex['last name']] = r.lastName || '';
    arr[headerIndex['new pieces of content used']] = r.newPieces;
    arr[headerIndex['gift card amount']] = r.amount;
    arr[headerIndex['email address']] = r.email || '';
    arr[headerIndex['links']] = r.links || '';
    return arr;
  });
  sheet.getRange(startRow, 1, out.length, lastCol).setValues(out);
}

// ---------------------------------------------------------------------------
// Step 2/4 messaging: deterministic mail-merge (no LLM needed — see README).
// Gemini is only used, optionally, to lightly polish tone (Gemini.gs).
// ---------------------------------------------------------------------------
function draftNewCreatorMessages() { draftMessagesForSheet_(SHEET_NAMES.NEW_CREATORS_MSG, NEW_CREATOR_PROMPT); }
function draftFollowUpMessages() { draftMessagesForSheet_(SHEET_NAMES.FOLLOWUP_MSG, FOLLOWUP_PROMPT); }

function draftMessagesForSheet_(sheetName, template) {
  const sheet = getSheet_(sheetName);
  ensureColumn_(sheet, 1, DRAFT_COLUMN_HEADER);
  ensureColumn_(sheet, 1, SENT_CHECKBOX_HEADER);
  const lastRow = sheet.getLastRow();
  const lastCol = sheet.getLastColumn();
  const numRows = lastRow - 1;
  if (numRows <= 0) { toast_('No rows in ' + sheetName); return; }

  const headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0];
  const headerIndex = buildHeaderIndex_(headers);
  const values = sheet.getRange(2, 1, numRows, lastCol).getValues();
  const draftIdx = headerIndex[normalizeHeader_(DRAFT_COLUMN_HEADER)];
  const sentIdx = headerIndex[normalizeHeader_(SENT_CHECKBOX_HEADER)];

  let drafted = 0, skipped = 0;
  values.forEach((row, i) => {
    if (row[draftIdx] || row[sentIdx]) return;
    const firstName = row[headerIndex['first name']];
    const pieces = row[headerIndex['new pieces of content used']];
    const amount = row[headerIndex['gift card amount']];
    const links = row[headerIndex['links']];
    if (!firstName || !pieces || !amount || !links) { skipped++; return; }
    const filled = fillTemplate_(template, { FIRST_NAME: firstName, PIECES: pieces, NEW_PIECES: pieces, AMOUNT: amount, LINKS: links });
    sheet.getRange(2 + i, draftIdx + 1).setValue(filled);
    drafted++;
  });

  toast_('Drafted ' + drafted + ' message(s) in "' + sheetName + '".' + (skipped ? ' ' + skipped + ' skipped (missing name/pieces/amount/links).' : ''));
}

/**
 * Optional: when Josh checks "Sent?" on a message row, flip the matching
 * Boosting Tracker rows for that creator from QUEUED_MARKER to "Yes" so the
 * tracker reflects that the creator was actually notified (not just queued).
 * Wire this up as an installable "On edit" trigger if desired.
 */
function onEditMarkSent(e) {
  if (!e || !e.range) return;
  const sheet = e.range.getSheet();
  const sheetName = sheet.getName();
  if (sheetName !== SHEET_NAMES.NEW_CREATORS_MSG && sheetName !== SHEET_NAMES.FOLLOWUP_MSG) return;

  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const headerIndex = buildHeaderIndex_(headers);
  const sentCol = headerIndex[normalizeHeader_(SENT_CHECKBOX_HEADER)];
  if (sentCol == null || e.range.getColumn() !== sentCol + 1) return;
  if (e.value !== 'TRUE') return;

  const row = sheet.getRange(e.range.getRow(), 1, 1, sheet.getLastColumn()).getValues()[0];
  const handle = row[headerIndex['creator handle']];
  if (!handle) return;

  const trackerSheet = getSheet_(SHEET_NAMES.BOOSTING_TRACKER);
  const lastRow = trackerSheet.getLastRow();
  const lastCol = trackerSheet.getLastColumn();
  const tHeaders = trackerSheet.getRange(HEADER_ROW.BOOSTING_TRACKER, 1, 1, lastCol).getValues()[0];
  const tHeaderIndex = buildHeaderIndex_(tHeaders);
  const firstDataRow = HEADER_ROW.BOOSTING_TRACKER + 1;
  const values = trackerSheet.getRange(firstDataRow, 1, lastRow - HEADER_ROW.BOOSTING_TRACKER, lastCol).getValues();

  values.forEach((r, i) => {
    const name = r[tHeaderIndex['creator name']];
    const notified = r[tHeaderIndex['creator notified']];
    if (normalizeHandle_(name) === normalizeHandle_(handle) && normalizeHeader_(notified) === normalizeHeader_(QUEUED_MARKER)) {
      trackerSheet.getRange(firstDataRow + i, tHeaderIndex['creator notified'] + 1).setValue('Yes');
    }
  });
}

// ---------------------------------------------------------------------------
// Step 5: end-of-month completeness check + clean export for the bulk gift
// card upload / campaign import.
// ---------------------------------------------------------------------------
function exportEndOfMonth() {
  const giftSheet = getSheet_(SHEET_NAMES.GIFT_CARD_TRACKER);
  const block = getCurrentMonthBlock_(giftSheet);
  const nameKey = ('creator handle' in block.headerIndex) ? 'creator handle' : 'creator name';
  const rows = readBlockRows_(giftSheet, block).filter((r) => String(r[nameKey] || '').trim() !== '');

  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const existing = ss.getSheetByName(SHEET_NAMES.EOM_EXPORT);
  if (existing) ss.deleteSheet(existing);
  const exportSheet = ss.insertSheet(SHEET_NAMES.EOM_EXPORT);

  const exportCols = ['creator handle', 'first name', 'last name', 'new pieces of content used', 'gift card amount', 'email address']
    .filter((c) => c in block.headerIndex || c === nameKey);
  const prettyHeaders = exportCols.map((c) => c.replace(/\b\w/g, (ch) => ch.toUpperCase()));
  exportSheet.getRange(1, 1, 1, prettyHeaders.length).setValues([prettyHeaders]).setFontWeight('bold');

  const complete = [];
  const missingEmail = [];
  rows.forEach((r) => {
    if (String(r['email address'] || '').trim() === '') missingEmail.push(r[nameKey]);
    else complete.push(exportCols.map((c) => r[c]));
  });

  if (complete.length) exportSheet.getRange(2, 1, complete.length, exportCols.length).setValues(complete);

  const amountIdx = exportCols.indexOf('gift card amount');
  const total = complete.reduce((sum, r) => sum + (parseFloat(String(r[amountIdx]).replace(/[^0-9.]/g, '')) || 0), 0);
  const summaryRow = complete.length + 3;
  exportSheet.getRange(summaryRow, 1).setValue('Complete creators:');
  exportSheet.getRange(summaryRow, 2).setValue(complete.length);
  exportSheet.getRange(summaryRow + 1, 1).setValue('Total gift card spend:');
  exportSheet.getRange(summaryRow + 1, 2).setValue('$' + total.toFixed(2));

  if (missingEmail.length) {
    exportSheet.getRange(summaryRow + 3, 1).setValue('MISSING EMAIL — chase before EOM close:').setFontColor('#c00');
    missingEmail.forEach((h, i) => exportSheet.getRange(summaryRow + 4 + i, 1).setValue(h));
  }

  toast_(
    complete.length + ' creator(s) ready to export, ' + missingEmail.length + ' still missing an email. ' +
    'See the "' + SHEET_NAMES.EOM_EXPORT + '" tab.'
  );
}
