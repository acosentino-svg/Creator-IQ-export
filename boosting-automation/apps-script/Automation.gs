/**
 * Automation.gs
 * Menu + the five process steps from the walkthrough, translated into code.
 * Run these from the "Boosting Automation" menu that appears when the
 * spreadsheet opens (see onOpen below).
 *
 * How a brand-new creator's info flows through the sheets:
 *   1. First time seen -> a row appears in the New Boosted Creators sheet
 *      (Handle, Name if CreatorIQ has it, Pieces, Amount, blank Email, Links).
 *      Nothing is written to the Gift Card Tracker yet.
 *   2. More content from the same still-unconfirmed creator, before you have
 *      an email -> that SAME row's pieces/amount/links get updated in place
 *      (no duplicate row), and its draft message is cleared so it gets
 *      redrafted with the new numbers.
 *   3. You type their confirmed email into that row's Email Address cell.
 *   4. Next sync (or the next automatic hourly run) notices the email,
 *      copies that row into the Gift Card Tracker as a real, final row, and
 *      marks it "Added to Tracker?" so it's never copied twice.
 *   5. Any further content from that creator this month is now a normal
 *      follow-up, updating their real tracker row directly.
 */

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Boosting Automation')
    .addItem('1. Start new month (Step 0)', 'startNewMonth')
    .addSeparator()
    .addItem('2. Sync new content -> gift card tracker + message sheets (Steps 2 & 4)', 'syncBoostingTracker')
    .addItem('2b. Promote confirmed emails to Gift Card Tracker', 'promoteConfirmedNewCreators_')
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
    .addItem('Setup: Test CreatorIQ connection (diagnostic)', 'testCreatorIQConnection_')
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

  if (!summary) return;
  const nothingHappened = summary.queued === 0 && summary.dupesFixed === 0 && summary.promoted === 0;
  if (nothingHappened) return;

  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const body =
    'Boosting Tracker sync just ran automatically:\n\n' +
    '- ' + summary.newCreators + ' brand-new/updated creator row(s) in the New Boosted Creators sheet\n' +
    '- ' + summary.followUps + ' follow-up piece(s) queued (Follow-Up sheet)\n' +
    '- ' + summary.promoted + ' creator(s) moved into the Gift Card Tracker (their email was confirmed)\n' +
    '- ' + summary.dupesFixed + ' dupe(s) auto-filled from the original entry (worth a quick Ctrl+F spot-check)\n\n' +
    'Messages have been drafted in both message sheets - review and send from CreatorIQ, ' +
    'then check "Sent?" on each row.\n\n' +
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
 * Looks at the New Boosted Creators sheet for any row that now has an email
 * address but hasn't been copied into the Gift Card Tracker yet, and copies
 * it over as a real, final row there. This is the ONLY thing that ever adds
 * a brand-new creator to the tracker - it happens because a human filled in
 * an email, never just because new content showed up.
 */
function promoteConfirmedNewCreators_(showToast) {
  if (showToast === undefined) showToast = true; // default true when run from the menu directly
  const msgSheet = getSheet_(SHEET_NAMES.NEW_CREATORS_MSG);
  ensureColumn_(msgSheet, HEADER_ROW.NEW_CREATORS_MSG, PROMOTED_COLUMN_HEADER);
  const promotedKey = normalizeHeader_(PROMOTED_COLUMN_HEADER);
  const read = readFlatSheetRows_(msgSheet, HEADER_ROW.NEW_CREATORS_MSG);

  const toPromote = read.rows.filter((r) => String(r['email address'] || '').trim() !== '' && !r[promotedKey]);
  if (!toPromote.length) {
    if (showToast) toast_('No newly-confirmed emails to promote yet.');
    return { promoted: 0 };
  }

  const giftSheet = getSheet_(SHEET_NAMES.GIFT_CARD_TRACKER);
  const block = getCurrentMonthBlock_(giftSheet);
  const nameKey = ('creator handle' in block.headerIndex) ? 'creator handle' : 'creator name';
  const nameHeaderLabel = (nameKey === 'creator handle') ? 'Creator Handle' : 'Creator Name';
  const newPiecesOffset = colIndex_(block.headerIndex, 'New Pieces of Content Used', true);
  const firstNameOffset = colIndex_(block.headerIndex, 'First Name', false);
  const lastNameOffset = colIndex_(block.headerIndex, 'Last Name', false);
  const emailOffset = colIndex_(block.headerIndex, 'Email Address', false);

  const blockRows = readBlockRows_(giftSheet, block);
  const existingHandles = {};
  let nextEmptyRow = HEADER_ROW.GIFT_CARD_TRACKER_FIELD_ROW + 1;
  let foundGap = false;
  blockRows.forEach((r) => {
    const h = normalizeHandle_(r[nameKey]);
    if (h) existingHandles[h] = true;
    else if (!foundGap) { nextEmptyRow = r._sheetRow; foundGap = true; }
  });
  if (!foundGap) nextEmptyRow = (blockRows.length ? blockRows[blockRows.length - 1]._sheetRow : HEADER_ROW.GIFT_CARD_TRACKER_FIELD_ROW) + 1;

  let promotedCount = 0;
  toPromote.forEach((r) => {
    const handleKey = normalizeHandle_(r['creator handle']);
    if (existingHandles[handleKey]) {
      // Already has a real row somehow (e.g. added by hand) - don't duplicate, just mark it done.
      msgSheet.getRange(r._sheetRow, read.headerIndex[promotedKey] + 1).setValue(true);
      return;
    }
    const targetRow = nextEmptyRow++;
    setBlockCell_(giftSheet, block, targetRow, nameHeaderLabel, r['creator handle']);
    if (firstNameOffset !== -1) giftSheet.getRange(targetRow, block.startCol + firstNameOffset + 1).setValue(r['first name'] || '');
    if (lastNameOffset !== -1) giftSheet.getRange(targetRow, block.startCol + lastNameOffset + 1).setValue(r['last name'] || '');
    giftSheet.getRange(targetRow, block.startCol + newPiecesOffset + 1).setValue(r['new pieces of content used']);
    if (emailOffset !== -1) giftSheet.getRange(targetRow, block.startCol + emailOffset + 1).setValue(r['email address']);
    existingHandles[handleKey] = true;
    msgSheet.getRange(r._sheetRow, read.headerIndex[promotedKey] + 1).setValue(true);
    promotedCount++;
  });

  if (showToast) {
    toast_(promotedCount + ' creator(s) moved into the Gift Card Tracker (email now confirmed).');
  }
  return { promoted: promotedCount };
}

/**
 * Steps 2 & 4: scan the Boosting Tracker once, classify each unhandled row.
 * The Gift Card Tracker is the FINAL, confirmed record - the only way a
 * creator ends up there is through promoteConfirmedNewCreators_ above, once
 * a human has typed in their email. Everything about a brand-new,
 * not-yet-confirmed creator lives in the New Boosted Creators sheet instead.
 */
function syncBoostingTracker(silent) {
  const promotion = promoteConfirmedNewCreators_(false);

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

  // Creators already sitting in the New Boosted Creators sheet, still unconfirmed
  // (no email yet, not promoted, and not already sent - if it was already sent, treat
  // any further content as a fresh row rather than silently changing a sent message).
  const newMsgSheet = getSheet_(SHEET_NAMES.NEW_CREATORS_MSG);
  ensureColumn_(newMsgSheet, HEADER_ROW.NEW_CREATORS_MSG, DRAFT_COLUMN_HEADER);
  ensureColumn_(newMsgSheet, HEADER_ROW.NEW_CREATORS_MSG, SENT_CHECKBOX_HEADER);
  ensureColumn_(newMsgSheet, HEADER_ROW.NEW_CREATORS_MSG, PROMOTED_COLUMN_HEADER);
  const promotedKey = normalizeHeader_(PROMOTED_COLUMN_HEADER);
  const sentKey = normalizeHeader_(SENT_CHECKBOX_HEADER);
  const draftKey = normalizeHeader_(DRAFT_COLUMN_HEADER);
  const newMsgRead = readFlatSheetRows_(newMsgSheet, HEADER_ROW.NEW_CREATORS_MSG);
  const pendingByHandle = {};
  newMsgRead.rows.forEach((r) => {
    const email = String(r['email address'] || '').trim();
    if (email !== '' || r[promotedKey] || r[sentKey]) return;
    const hk = normalizeHandle_(r['creator handle']);
    if (hk) pendingByHandle[hk] = r;
  });

  const followUpRows = [];
  const piecesUpdates = []; // real, already-confirmed rows: { row, value }
  const trackerMarkerUpdates = []; // { row, value }
  const virtualNewCreators = {}; // brand-new this run, not yet in the sheet at all
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
    } else if (pendingByHandle[handleKey]) {
      const p = pendingByHandle[handleKey];
      p._pendingDelta = (p._pendingDelta || 0) + 1;
      p._newLinks = p._newLinks || [];
      p._newLinks.push(links);
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

  // Compute the correct Gift Card Amount for every pending update + brand-new creator by
  // briefly borrowing not-yet-used formula rows further down this same block, in one batch.
  const pendingList = Object.keys(pendingByHandle).map((k) => pendingByHandle[k]).filter((p) => p._pendingDelta);
  const virtualList = Object.keys(virtualNewCreators).map((k) => virtualNewCreators[k]);
  const scratchNeeded = pendingList.length + virtualList.length;
  if (scratchNeeded) {
    const amountCol = block.startCol + amountOffset + 1;
    const piecesCol = block.startCol + newPiecesOffset + 1;
    let scratchRow = nextEmptyRow;
    pendingList.forEach((p) => {
      p._scratchRow = scratchRow++;
      p._newTotalPieces = (Number(p['new pieces of content used']) || 0) + p._pendingDelta;
    });
    virtualList.forEach((v) => { v._scratchRow = scratchRow++; });

    pendingList.forEach((p) => { giftSheet.getRange(p._scratchRow, piecesCol).setValue(p._newTotalPieces); });
    virtualList.forEach((v) => { giftSheet.getRange(v._scratchRow, piecesCol).setValue(v.totalPieces); });
    SpreadsheetApp.flush();

    const amounts = giftSheet.getRange(nextEmptyRow, amountCol, scratchNeeded, 1).getValues();
    const amountByRow = {};
    amounts.forEach((r, idx) => { amountByRow[nextEmptyRow + idx] = r[0]; });
    pendingList.forEach((p) => { p._newAmount = amountByRow[p._scratchRow]; });
    virtualList.forEach((v) => { v.amount = amountByRow[v._scratchRow]; });

    giftSheet.getRange(nextEmptyRow, piecesCol, scratchNeeded, 1).clearContent();
  }

  // Apply updates to already-pending rows in the New Boosted Creators sheet in place.
  pendingList.forEach((p) => {
    const piecesCol1 = newMsgRead.headerIndex['new pieces of content used'] + 1;
    const amountCol1 = newMsgRead.headerIndex['gift card amount'] + 1;
    const linksCol1 = newMsgRead.headerIndex['links'] + 1;
    newMsgSheet.getRange(p._sheetRow, piecesCol1).setValue(p._newTotalPieces);
    newMsgSheet.getRange(p._sheetRow, amountCol1).setValue(p._newAmount);
    const combinedLinks = (String(p['links'] || '').trim() ? p['links'] + ', ' : '') + p._newLinks.join(', ');
    newMsgSheet.getRange(p._sheetRow, linksCol1).setValue(combinedLinks);
    newMsgSheet.getRange(p._sheetRow, newMsgRead.headerIndex[draftKey] + 1).clearContent(); // force a redraft with the new totals
  });

  const newRows = virtualList.map((v) => ({
    handle: v.handle,
    firstName: v.profile ? v.profile.firstName : '',
    lastName: v.profile ? v.profile.lastName : '',
    newPieces: v.totalPieces,
    amount: v.amount,
    email: '',
    links: v.links.join(', '),
  }));
  appendToMessageSheet_(SHEET_NAMES.NEW_CREATORS_MSG, newRows);
  appendToMessageSheet_(SHEET_NAMES.FOLLOWUP_MSG, followUpRows);

  const totalNewCreatorActivity = newRows.length + pendingList.length;
  if (!silent) {
    toast_(
      'Queued ' + queued + ' row(s) [' + totalNewCreatorActivity + ' new-creator update(s), ' + followUpRows.length + ' follow-up], ' +
      'auto-filled ' + dupesFixed + ' dupe(s), promoted ' + promotion.promoted + ' confirmed creator(s) to the tracker. ' +
      'Now run step 3a/3b to draft messages.'
    );
  }

  return {
    queued: queued, newCreators: totalNewCreatorActivity, followUps: followUpRows.length,
    dupesFixed: dupesFixed, promoted: promotion.promoted,
  };
}

function setBlockCell_(sheet, block, row, headerName, value) {
  const offset = colIndex_(block.headerIndex, headerName, true);
  sheet.getRange(row, block.startCol + offset + 1).setValue(value);
}

/**
 * Fills a dupe row's link/SKU-type fields from the original (first) row that
 * shares the same Unique Identifier, but ONLY into cells that are currently
 * blank - never overwrites anything a human already entered. Leaves a note
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

/**
 * Step 5: end-of-month completeness check + clean export for the bulk gift
 * card upload / campaign import.
 */
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
