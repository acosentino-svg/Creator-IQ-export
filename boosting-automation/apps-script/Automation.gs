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

const AUTO_SYNC_HANDLER = 'runScheduledSync';

function enableAutoSync() {
  disableAutoSync();
  ScriptApp.newTrigger(AUTO_SYNC_HANDLER).timeBased().everyHours(1).create();
  SpreadsheetApp.getUi().alert('Automatic hourly sync is ON. You will get an email summary whenever there is something new to review.');
}

function disableAutoSync() {
  ScriptApp.getProjectTriggers()
    .filter((t) => t.getHandlerFunction() === AUTO_SYNC_HANDLER)
    .forEach((t) => ScriptApp.deleteTrigger(t));
}

function runScheduledSync() {
  const summary = syncBoostingTracker(true);
  draftMessagesForSheet_(SHEET_NAMES.NEW_CREATORS_MSG, NEW_CREATOR_PROMPT);
  draftMessagesForSheet_(SHEET_NAMES.FOLLOWUP_MSG, FOLLOWUP_PROMPT);

  if (!summary || (summary.queued === 0 && summary.dupesFixed === 0)) return;

  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const body =
    'Boosting Tracker sync just ran automatically:\n\n' +
    '- ' + summary.newCreators + ' brand-new creator(s) queued (New Boosted Creators sheet)\n' +
    '- ' + summary.followUps + ' follow-up piece(s) queued (Follow-Up sheet)\n' +
    '- ' + summary.dupesFixed + ' dupe(s) auto-filled from the original entry (worth a quick Ctrl+F spot-check)\n\n' +
    'Messages have been drafted in both message sheets - review and send from CreatorIQ, ' +
    'then check "Sent?" on each row. New creators are NOT yet in the Gift Card Tracker - add them ' +
    'there yourself once you have their confirmed email.\n\n' +
    'Open the tracker: ' + ss.getUrl();

  MailApp.sendEmail(Session.getActiveUser().getEmail(), 'Boosting Tracker: new content ready to review', body);
}

const ROWS_TO_PROVISION = 400;

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

  const newStartCol0 = lastBlock.endCol + 1;
  const width = lastBlock.width;

  sheet.getRange(1, newStartCol0 + 1).setValue(label);
  sheet.getRange(HEADER_ROW.GIFT_CARD_TRACKER_FIELD_ROW, lastBlock.startCol + 1, 1, width)
    .copyTo(sheet.getRange(HEADER_ROW.GIFT_CARD_TRACKER_FIELD_ROW, newStartCol0 + 1, 1, width));

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

/**
 * Steps 2 & 4: scan the Boosting Tracker once, classify each unhandled row.
 *
 * IMPORTANT: the Monthly Gift Card Cost Tracker is treated as the FINAL,
 * confirmed record - the script never writes a brand-new creator into it.
 * Only creators who already have a real row there (added by a human once
 * their email was confirmed in an earlier sync this month) get their
 * "New Pieces of Content Used" incremented directly. Brand-new creators are
 * tracked only in memory for this run, so their message can be drafted with
 * the correct amount, without ever touching the tracker sheet itself.
 */
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
  const nameKey = ('creator handle' in block.headerIndex) ? 'creator handle' : 'creator name';
  const newPiecesOffset = colIndex_(block.headerIndex, 'New Pieces of Content Used', true);
  const amountOffset = colIndex_(block.headerIndex, 'Gift Card Amount', true);

  const blockRows = readBlockRows_(giftSheet, block);
  const handleToBlockRow = {};
  let nextEmptyRow = HEADER_ROW.GIFT_CARD_TRACKER_FIELD_ROW + 1;
  let foundGap = false;
  blockRows.forEach((r) => {
    const h = normalizeHandle_(r[nameKey]);
    if (h) handleToBlockRow[h] = r;
    else if (!foundGap) { nextEmptyRow = r._sheetRow; foundGap = true; }
  });
  if (!foundGap) nextEmptyRow = (blockRows.length ? blockRows[blockRows.length - 1]._sheetRow : HEADER_ROW.GIFT_CARD_TRACKER_FIELD_ROW) + 1;

  const newRows = [];
  const followUpRows = [];
  const piecesUpdates = []; // real, already-confirmed rows only: { row, value }
  const trackerMarkerUpdates = []; // { row, value }
  const virtualNewCreators = {}; // handleKey -> { handle, totalPieces, links: [], profile } - NOT written to the tracker
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
    const handleKey = normalizeHandle_(handle);
    const linksIdx = headerIndex['storefront links provided'];
    const favLinksIdx = headerIndex["fav's list + affiliate links provided"];
    const links = (linksIdx != null && row[linksIdx]) || (favLinksIdx != null && row[favLinksIdx]) || contentUsed;

    const existing = handleToBlockRow[handleKey];
    if (existing) {
      const currentPieces = (Number(existing['new pieces of content used']) || 0) + (existing._pendingDelta || 0);
      const newTotal = currentPieces + 1;
      existing._pendingDelta = (existing._pendingDelta || 0) + 1;
      piecesUpdates.push({ row: existing._sheetRow, value: newTotal });
      followUpRows.push({
        handle: handle, blockRow: existing._sheetRow,
        firstName: existing['first name'] || '', lastName: existing['last name'] || '',
        newPieces: 1, email: existing['email address'] || '', links: links,
      });
    } else if (virtualNewCreators[handleKey]) {
      const v = virtualNewCreators[handleKey];
      v.totalPieces++;
      v.links.push(links);
    } else {
      virtualNewCreators[handleKey] = {
        handle: handle, totalPieces: 1, links: [links],
        profile: ciqFindPublisherByHandle_(handle),
      };
    }

    trackerMarkerUpdates.push({ row: sheetRow, value: QUEUED_MARKER });
    queued++;
  }

  piecesUpdates.forEach((u) => {
    giftSheet.getRange(u.row, block.startCol + newPiecesOffset + 1).setValue(u.value);
  });
  trackerMarkerUpdates.forEach((u) => {
    trackerSheet.getRange(u.row, headerIndex['creator notified'] + 1).setValue(u.value);
  });
  if (piecesUpdates.length) SpreadsheetApp.flush();

  if (piecesUpdates.length) {
    const rows = piecesUpdates.map((u) => u.row);
    const minRow = Math.min.apply(null, rows);
    const maxRow = Math.max.apply(null, rows);
    const amountCol = block.startCol + amountOffset + 1;
    const amounts = giftSheet.getRange(minRow, amountCol, maxRow - minRow + 1, 1).getValues();
    const amountByRow = {};
    amounts.forEach((r, idx) => { amountByRow[minRow + idx] = r[0]; });
    followUpRows.forEach((r) => { r.amount = amountByRow[r.blockRow]; });
  }

  // Compute the right Gift Card Amount for brand-new creators by briefly borrowing a few
  // already-provisioned (but unused) formula rows further down this same block - write the
  // piece count, read back what the real formula computes this month, then clear it right
  // away. The tracker itself never gains a row for an unconfirmed creator.
  const virtualList = Object.keys(virtualNewCreators).map((k) => virtualNewCreators[k]);
  if (virtualList.length) {
    const amountCol = block.startCol + amountOffset + 1;
    const piecesCol = block.startCol + newPiecesOffset + 1;
    virtualList.forEach((v, idx) => { v._scratchRow = nextEmptyRow + idx; });
    virtualList.forEach((v) => { giftSheet.getRange(v._scratchRow, piecesCol).setValue(v.totalPieces); });
    SpreadsheetApp.flush();
    const amounts = giftSheet.getRange(nextEmptyRow, amountCol, virtualList.length, 1).getValues();
    virtualList.forEach((v, idx) => { v.amount = amounts[idx][0]; });
    giftSheet.getRange(nextEmptyRow, piecesCol, virtualList.length, 1).clearContent();
  }
  virtualList.forEach((v) => {
    newRows.push({
      handle: v.handle,
      firstName: v.profile ? v.profile.firstName : '',
      lastName: v.profile ? v.profile.lastName : '',
      newPieces: v.totalPieces,
      amount: v.amount,
      email: '',
      links: v.links.join(', '),
    });
  });

  appendToMessageSheet_(SHEET_NAMES.NEW_CREATORS_MSG, newRows);
  appendToMessageSheet_(SHEET_NAMES.FOLLOWUP_MSG, followUpRows);

  if (!silent) {
    toast_(
      'Queued ' + queued + ' row(s) [' + newRows.length + ' new creator, ' + followUpRows.length + ' follow-up], ' +
      'auto-filled ' + dupesFixed + ' dupe(s). New creators were NOT added to the Gift Card Tracker - ' +
      'add them yourself once you have a confirmed email. Now run step 3a/3b to draft messages.'
    );
  }

  return { queued: queued, newCreators: newRows.length, followUps: followUpRows.length, dupesFixed: dupesFixed };
}

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
          'Please spot-check with Ctrl+F before trusting - dupe-detection formulas have broken before.'
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
    exportSheet.getRange(summaryRow + 3, 1).setValue('MISSING EMAIL - chase before EOM close:').setFontColor('#c00');
    missingEmail.forEach((h, i) => exportSheet.getRange(summaryRow + 4 + i, 1).setValue(h));
  }

  toast_(
    complete.length + ' creator(s) ready to export, ' + missingEmail.length + ' still missing an email. ' +
    'See the "' + SHEET_NAMES.EOM_EXPORT + '" tab.'
  );
}
