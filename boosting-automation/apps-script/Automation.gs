/**
 * Automation.gs
 * Menu + boosting workflow. New content flows:
 *   Boosting Tracker -> Outreach Queue (draft emails) -> CreatorIQ send ->
 *   confirmed email entered -> Gift Card month tab.
 */

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Boosting Automation')
    .addItem('Monday check (queue + draft emails)', 'mondayCheck')
    .addItem('Promote confirmed emails to Gift Card Tracker', 'promoteConfirmedNewCreators_')
    .addSeparator()
    .addItem('1. Start new month (gift card tab)', 'startNewMonth')
    .addItem('2. End-of-month export (Step 5)', 'exportEndOfMonth')
    .addSeparator()
    .addItem('Redraft outreach queue', 'draftOutreachMessages')
    .addItem('Turn ON automatic weekly sync', 'enableAutoSync')
    .addItem('Turn OFF automatic sync', 'disableAutoSync')
    .addSeparator()
    .addItem('Setup: Test Names lookup (diagnostic)', 'testNameLookup_')
    .addItem('Setup: Test draft readiness (diagnostic)', 'testDraftReadiness_')
    .addItem('Setup: Fill missing names from "Names" tab', 'fillMissingNamesFromLookup')
    .addItem('Setup: Choose active gift card month', 'chooseActiveGiftCardMonth_')
    .addToUi();
}

/** One click: scan tracker, fill Outreach Queue, draft all emails, open that tab. */
function mondayCheck() {
  toast_('Monday check: scanning Boosting Tracker...');
  const summary = syncBoostingTracker(true);
  toast_('Monday check: drafting outreach emails...');
  const draftResult = draftOutreachMessages(true);
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const queue = ss.getSheetByName(SHEET_NAMES.OUTREACH_QUEUE);
  if (queue) ss.setActiveSheet(queue);
  if (!summary) return;

  let msg = 'Monday check done: ' + summary.queued + ' video(s) from tracker';
  if (summary.skippedDupes) msg += ' (' + summary.skippedDupes + ' dupes skipped)';
  msg += ' -> ' + summary.emailRows + ' email row(s). Drafted ' + draftResult.drafted;
  if (summary.queued > summary.emailRows) {
    msg += ' (grouped by creator — multiple videos = one email)';
  }
  if (draftResult.skipped) {
    msg += '. ' + draftResult.skipped + ' row(s) still need a name or link';
    writeDraftReadinessDebug_(true);
    msg += ' — see "Draft Readiness Debug" tab';
  }
  msg += '.';
  toast_(msg);
}

const AUTO_SYNC_HANDLER = 'runScheduledSync';

function enableAutoSync() {
  disableAutoSync();
  ScriptApp.newTrigger(AUTO_SYNC_HANDLER).timeBased().onWeekDay(ScriptApp.WeekDay.MONDAY).atHour(8).create();
  SpreadsheetApp.getUi().alert('Automatic Monday 8am sync is ON. Run Monday check from the menu anytime.');
}

function disableAutoSync() {
  ScriptApp.getProjectTriggers()
    .filter((t) => t.getHandlerFunction() === AUTO_SYNC_HANDLER)
    .forEach((t) => ScriptApp.deleteTrigger(t));
}

function runScheduledSync() {
  mondayCheck();
}

function startNewMonth() {
  const ui = SpreadsheetApp.getUi();
  const resp = ui.prompt(
    'Start new month',
    'Month and year for the new gift card tab (e.g. "July 2026"):',
    ui.ButtonSet.OK_CANCEL
  );
  if (resp.getSelectedButton() !== ui.Button.OK) return;
  const input = resp.getResponseText().trim();
  if (!input) return;

  const match = input.match(/^(\w+)\s+(\d{4})$/);
  if (!match) {
    ui.alert('Please enter month and year like "July 2026".');
    return;
  }

  const tabName = formatGiftCardMonthTabName_(match[1], match[2]);
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  if (ss.getSheetByName(tabName)) {
    setActiveGiftCardSheet_(tabName);
    ui.alert('Tab "' + tabName + '" already exists — it is now the active gift card month.');
    return;
  }

  const previousName = getActiveGiftCardSheetName_();
  const newSheet = createGiftCardMonthTab_(tabName);

  if (previousName !== tabName && isGiftCardMonthTabName_(previousName)) {
    const hideResp = ui.alert(
      'Hide previous month?',
      'Hide "' + previousName + '"? (You can unhide it anytime from the tab menu.)',
      ui.ButtonSet.YES_NO
    );
    if (hideResp === ui.Button.YES) {
      const prev = ss.getSheetByName(previousName);
      if (prev) prev.hideSheet();
    }
  }

  ui.alert(
    'Created "' + tabName + '" and set it as the active gift card month.\n\n' +
    'IMPORTANT: If this month has a different comp/activation (Cranberry Cashout, June Jackpot, etc.), ' +
    'update the Gift Card Amount formula on this tab before entering creators.'
  );
  ss.setActiveSheet(newSheet);
}

/** Lets you point automation at a specific month tab (e.g. after unhiding an older month). */
function chooseActiveGiftCardMonth_() {
  const ui = SpreadsheetApp.getUi();
  const tabs = listGiftCardMonthTabs_();
  const legacy = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAMES.GIFT_CARD_LEGACY);
  let prompt = 'Enter the exact tab name for the active gift card month.\n\n';
  if (tabs.length) {
    prompt += 'Per-month tabs found:\n' + tabs.map((t) => '- ' + t.tabName).join('\n') + '\n\n';
  }
  if (legacy) prompt += 'Legacy fallback: ' + SHEET_NAMES.GIFT_CARD_LEGACY + '\n\n';
  prompt += 'Current active: ' + getActiveGiftCardSheetName_();

  const resp = ui.prompt('Choose active gift card month', prompt, ui.ButtonSet.OK_CANCEL);
  if (resp.getSelectedButton() !== ui.Button.OK) return;
  const name = resp.getResponseText().trim();
  if (!name) return;
  if (!SpreadsheetApp.getActiveSpreadsheet().getSheetByName(name)) {
    ui.alert('No tab named "' + name + '" was found.');
    return;
  }
  setActiveGiftCardSheet_(name);
  toast_('Active gift card month set to "' + name + '".');
}

/**
 * Copies Outreach Queue rows (Type = New) with a confirmed email into the
 * active gift card month tab. This is the only way a brand-new creator lands
 * on the gift card tracker.
 */
function promoteConfirmedNewCreators_(showToast) {
  if (showToast === undefined) showToast = true;
  const queueSheet = getOutreachQueueSheet_();
  const promotedKey = normalizeHeader_(PROMOTED_COLUMN_HEADER);
  const typeKey = normalizeHeader_(TYPE_COLUMN_HEADER);
  const read = readFlatSheetRows_(queueSheet, HEADER_ROW.OUTREACH_QUEUE);

  const toPromote = read.rows.filter((r) =>
    String(r[typeKey] || '').trim() === OUTREACH_TYPE_NEW &&
    String(r['email address'] || '').trim() !== '' &&
    !r[promotedKey]
  );
  if (!toPromote.length) {
    if (showToast) toast_('No newly-confirmed emails to promote yet.');
    return { promoted: 0 };
  }

  const ctx = getGiftCardContext_();
  const giftSheet = ctx.sheet;
  const nameKey = ctx.nameKey;
  const nameHeaderLabel = (nameKey === 'creator handle') ? 'Creator Handle' : 'Creator Name';
  const firstNameCol = giftCardCol1_(ctx, 'First Name', false);
  const lastNameCol = giftCardCol1_(ctx, 'Last Name', false);
  const emailCol = giftCardCol1_(ctx, 'Email Address', false);
  const newPiecesCol = giftCardCol1_(ctx, 'New Pieces of Content Used', true);

  const blockRows = readGiftCardRows_(ctx);
  const existingHandles = {};
  blockRows.forEach((r) => {
    const h = normalizeHandle_(r[nameKey]);
    if (h) existingHandles[h] = true;
  });
  let nextEmptyRow = findNextEmptyGiftCardRow_(ctx, blockRows);

  let promotedCount = 0;
  toPromote.forEach((r) => {
    const handleKey = normalizeHandle_(r['creator handle']);
    if (existingHandles[handleKey]) {
      queueSheet.getRange(r._sheetRow, read.headerIndex[promotedKey] + 1).setValue(true);
      return;
    }
    const targetRow = nextEmptyRow++;
    setGiftCardCell_(ctx, targetRow, nameHeaderLabel, r['creator handle']);
    if (firstNameCol !== -1) giftSheet.getRange(targetRow, firstNameCol).setValue(r['first name'] || '');
    if (lastNameCol !== -1) giftSheet.getRange(targetRow, lastNameCol).setValue(r['last name'] || '');
    giftSheet.getRange(targetRow, newPiecesCol).setValue(r['new pieces of content used']);
    if (emailCol !== -1) giftSheet.getRange(targetRow, emailCol).setValue(r['email address']);
    existingHandles[handleKey] = true;
    queueSheet.getRange(r._sheetRow, read.headerIndex[promotedKey] + 1).setValue(true);
    promotedCount++;
  });

  if (showToast) {
    toast_(promotedCount + ' creator(s) moved into the Gift Card Tracker (email now confirmed).');
  }
  return { promoted: promotedCount };
}

/**
 * Scans Boosting Tracker for new videos, skips dupes, queues emails on
 * Outreach Queue, and updates gift card rows for confirmed creators.
 */
function syncBoostingTracker(silent) {
  const promotion = promoteConfirmedNewCreators_(false);

  const trackerSheet = getSheet_(SHEET_NAMES.BOOSTING_TRACKER);
  const lastRow = trackerSheet.getLastRow();
  const lastCol = trackerSheet.getLastColumn();
  const headers = trackerSheet.getRange(HEADER_ROW.BOOSTING_TRACKER, 1, 1, lastCol).getValues()[0];
  const headerIndex = buildHeaderIndex_(headers);
  ['creator name', 'content used', 'creator notified', 'unique identifier'].forEach((h) => colIndex_(headerIndex, h, true));
  const platformIdx = colIndex_(headerIndex, 'platform(s) for usage', false);

  const firstDataRow = HEADER_ROW.BOOSTING_TRACKER + 1;
  const numRows = lastRow - HEADER_ROW.BOOSTING_TRACKER;
  if (numRows <= 0) { if (!silent) toast_('No rows in ' + SHEET_NAMES.BOOSTING_TRACKER); return; }
  const values = trackerSheet.getRange(firstDataRow, 1, numRows, lastCol).getValues();

  const ctx = getGiftCardContext_();
  const giftSheet = ctx.sheet;
  const nameKey = ctx.nameKey;
  const newPiecesCol = giftCardCol1_(ctx, 'New Pieces of Content Used', true);

  const blockRows = readGiftCardRows_(ctx);
  const handleToBlockRow = {};
  blockRows.forEach((r) => {
    const h = normalizeHandle_(r[nameKey]);
    if (h) handleToBlockRow[h] = r;
  });

  const queueSheet = getOutreachQueueSheet_();
  const promotedKey = normalizeHeader_(PROMOTED_COLUMN_HEADER);
  const sentKey = normalizeHeader_(SENT_CHECKBOX_HEADER);
  const draftKey = normalizeHeader_(DRAFT_COLUMN_HEADER);
  const typeKey = normalizeHeader_(TYPE_COLUMN_HEADER);
  const queueRead = readFlatSheetRows_(queueSheet, HEADER_ROW.OUTREACH_QUEUE);
  const nameLookup = buildNameLookup_();
  const pendingNewByHandle = {};
  queueRead.rows.forEach((r) => {
    if (String(r[typeKey] || '').trim() !== OUTREACH_TYPE_NEW) return;
    const email = String(r['email address'] || '').trim();
    if (email !== '' || r[promotedKey] || r[sentKey]) return;
    const hk = normalizeHandle_(r['creator handle']);
    if (hk) pendingNewByHandle[hk] = r;
  });

  const followUpByHandle = {};
  const piecesUpdates = [];
  const trackerMarkerUpdates = [];
  const virtualNewCreators = {};
  let dupesFixed = 0, queued = 0, outreachRows = 0, skippedDupes = 0;

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
      skippedDupes++;
      if (fillDupeLinks_(trackerSheet, headerIndex, values, i, sheetRow)) dupesFixed++;
      continue;
    }

    const handle = String(creatorName).trim();
    const handleKey = normalizeHandle_(handle);
    const platform = platformIdx != null ? String(row[platformIdx] || '').trim() : '';
    const linksIdx = headerIndex['storefront links provided'];
    const favLinksIdx = headerIndex["fav's list + affiliate links provided"];
    const links = (linksIdx != null && row[linksIdx]) || (favLinksIdx != null && row[favLinksIdx]) || contentUsed;

    const existing = handleToBlockRow[handleKey];
    if (existing) {
      const currentPieces = (Number(existing['new pieces of content used']) || 0) + (existing._pendingDelta || 0);
      const newTotal = currentPieces + 1;
      existing._pendingDelta = (existing._pendingDelta || 0) + 1;
      piecesUpdates.push({ row: existing._sheetRow, value: newTotal });

      let followUp = followUpByHandle[handleKey];
      if (!followUp) {
        followUp = followUpByHandle[handleKey] = {
          handle: handle,
          firstName: existing['first name'] || '',
          lastName: existing['last name'] || '',
          newPieces: 0,
          totalPieces: newTotal,
          email: existing['email address'] || '',
          links: [],
          platforms: [],
        };
      }
      followUp.newPieces++;
      followUp.totalPieces = newTotal;
      followUp.links.push(links);
      if (platform) followUp.platforms.push(platform);
    } else if (pendingNewByHandle[handleKey]) {
      const p = pendingNewByHandle[handleKey];
      p._pendingDelta = (p._pendingDelta || 0) + 1;
      p._newLinks = p._newLinks || [];
      p._newLinks.push(links);
      if (platform) p._platforms = (p._platforms || []).concat([platform]);
    } else if (virtualNewCreators[handleKey]) {
      const v = virtualNewCreators[handleKey];
      v.totalPieces++;
      v.links.push(links);
      if (platform) v.platforms = (v.platforms || []).concat([platform]);
    } else {
      virtualNewCreators[handleKey] = {
        handle: handle, totalPieces: 1, links: [links], platforms: platform ? [platform] : [],
        profile: nameLookup[handleKey] || (CREATORIQ_LOOKUP_ENABLED ? ciqFindPublisherByHandle_(handle) : null),
      };
    }

    trackerMarkerUpdates.push({ row: sheetRow, value: QUEUED_MARKER });
    queued++;
  }

  batchSetColumnValues_(giftSheet, newPiecesCol, piecesUpdates);
  batchSetColumnValues_(trackerSheet, headerIndex['creator notified'] + 1, trackerMarkerUpdates);
  if (piecesUpdates.length) SpreadsheetApp.flush();

  const followUpRows = Object.keys(followUpByHandle).map((handleKey) => {
    const r = followUpByHandle[handleKey];
    return {
      handle: r.handle,
      firstName: r.firstName,
      lastName: r.lastName,
      newPieces: r.newPieces,
      totalPieces: r.totalPieces,
      email: r.email,
      links: r.links.filter((l) => String(l || '').trim()).join(', '),
      platform: mergePlatformLabels_('', r.platforms.join(', ')),
      amount: formatAmount_(calculateGiftCardAmount_(r.totalPieces)),
    };
  });

  const pendingList = Object.keys(pendingNewByHandle).map((k) => pendingNewByHandle[k]).filter((p) => p._pendingDelta);
  const virtualList = Object.keys(virtualNewCreators).map((k) => virtualNewCreators[k]);

  pendingList.forEach((p) => {
    p._newTotalPieces = (Number(p['new pieces of content used']) || 0) + p._pendingDelta;
    p._newAmount = formatAmount_(calculateGiftCardAmount_(p._newTotalPieces));
  });
  virtualList.forEach((v) => {
    v.amount = formatAmount_(calculateGiftCardAmount_(v.totalPieces));
  });

  if (pendingList.length) {
    const queueStartRow = HEADER_ROW.OUTREACH_QUEUE + 1;
    const queueLastRow = queueSheet.getLastRow();
    const queueLastCol = queueSheet.getLastColumn();
    const queueValues = queueSheet.getRange(queueStartRow, 1, queueLastRow - queueStartRow + 1, queueLastCol).getValues();
    const platformKey = normalizeHeader_(PLATFORM_COLUMN_HEADER);
    const piecesIdx = queueRead.headerIndex['new pieces of content used'];
    const amountIdx = queueRead.headerIndex['gift card amount'];
    const linksIdx = queueRead.headerIndex['links'];
    const draftIdx = queueRead.headerIndex[draftKey];
    const platformIdx = queueRead.headerIndex[platformKey];
    const firstNameIdx = queueRead.headerIndex['first name'];
    const lastNameIdx = queueRead.headerIndex['last name'];

    pendingList.forEach((p) => {
      const rowIdx = p._sheetRow - queueStartRow;
      const rowVals = queueValues[rowIdx];
      rowVals[piecesIdx] = p._newTotalPieces;
      rowVals[amountIdx] = p._newAmount;
      rowVals[linksIdx] = (String(p['links'] || '').trim() ? p['links'] + ', ' : '') + p._newLinks.join(', ');
      if (platformIdx != null && p._platforms && p._platforms.length) {
        rowVals[platformIdx] = mergePlatformLabels_(String(p[platformKey] || '').trim(), p._platforms.join(', '));
      }
      rowVals[draftIdx] = '';

      if (!String(p['first name'] || '').trim()) {
        const found = nameLookup[normalizeHandle_(p['creator handle'])];
        if (found) {
          rowVals[firstNameIdx] = found.firstName;
          if (lastNameIdx != null) rowVals[lastNameIdx] = found.lastName;
        }
      }
    });
    queueSheet.getRange(queueStartRow, 1, queueLastRow - queueStartRow + 1, queueLastCol).setValues(queueValues);
  }

  const newRows = virtualList.map((v) => ({
    handle: v.handle,
    firstName: v.profile ? v.profile.firstName : '',
    lastName: v.profile ? v.profile.lastName : '',
    newPieces: v.totalPieces,
    amount: v.amount,
    email: '',
    links: v.links.join(', '),
    platform: (v.platforms || []).filter(Boolean).join(', '),
  }));

  outreachRows += appendToOutreachQueue_(OUTREACH_TYPE_NEW, newRows);
  outreachRows += appendToOutreachQueue_(OUTREACH_TYPE_FOLLOWUP, followUpRows);
  outreachRows += pendingList.length;

  const emailRows = newRows.length + followUpRows.length + pendingList.length;

  if (!silent) {
    toast_(
      'Queued ' + queued + ' video(s) -> ' + emailRows + ' email row(s) on Outreach Queue, ' +
      'promoted ' + promotion.promoted + ' to gift card tracker.'
    );
  }

  return {
    queued: queued,
    outreachRows: outreachRows,
    emailRows: emailRows,
    newCreators: newRows.length + pendingList.length,
    followUps: followUpRows.length,
    dupesFixed: dupesFixed,
    skippedDupes: skippedDupes,
    promoted: promotion.promoted,
  };
}

/**
 * Diagnostic only - since buildNameLookup_() fails silently by design (so a
 * missing/misnamed Names tab never breaks the real sync), this writes out
 * exactly what it found (or didn't find) into a "Names Lookup Debug" tab so
 * we can see why names aren't matching, instead of guessing.
 */
function testNameLookup_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const existing = ss.getSheetByName('Names Lookup Debug');
  if (existing) ss.deleteSheet(existing);
  const debugSheet = ss.insertSheet('Names Lookup Debug');

  const rows = [['Check', 'Result']];
  rows.push(['NAMES_LOOKUP_SHEET_NAME configured as', NAMES_LOOKUP_SHEET_NAME]);
  rows.push(['EXTERNAL_NAMES_SHEET_ID set?', EXTERNAL_NAMES_SHEET_ID ? 'yes - also checking that file' : 'no - looking in this active spreadsheet only']);

  let namesSheet = null;
  try {
    namesSheet = getNamesLookupSheet_();
  } catch (e) {
    rows.push(['Error while looking for the Names tab', String(e)]);
  }

  if (!namesSheet) {
    rows.push(['Names tab found?', 'NO - no tab named "' + NAMES_LOOKUP_SHEET_NAME + '" was found in this spreadsheet' + (EXTERNAL_NAMES_SHEET_ID ? ' or the external Names file' : '') + '.']);
  } else {
    rows.push(['Names tab found?', 'YES']);
    rows.push(['Names tab actual name', namesSheet.getName()]);
    rows.push(['Names tab last row / last column', namesSheet.getLastRow() + ' / ' + namesSheet.getLastColumn()]);
    const lastCol = namesSheet.getLastColumn();
    const headerRow = lastCol > 0 ? namesSheet.getRange(1, 1, 1, lastCol).getValues()[0] : [];
    rows.push(['Header row exactly as read', headerRow.join(' | ')]);
  }

  const lookup = buildNameLookup_();
  const keys = Object.keys(lookup);
  rows.push(['Total handles matched', keys.length]);
  rows.push(['Sample matches (up to 5)', keys.slice(0, 5).map((k) => k + ' -> ' + lookup[k].firstName + ' ' + lookup[k].lastName).join('  |  ')]);

  debugSheet.getRange(1, 1, rows.length, 2).setValues(rows);
  debugSheet.autoResizeColumns(1, 2);
  SpreadsheetApp.getUi().alert('Done. Check the "Names Lookup Debug" tab, then copy/paste its contents back to me.');
}

/**
 * Diagnostic: shows per-row why outreach would draft or skip each creator.
 * @param {boolean} silent When true, writes the tab without a popup (used by Monday check).
 */
function writeDraftReadinessDebug_(silent) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const tabName = 'Draft Readiness Debug';
  const existing = ss.getSheetByName(tabName);
  if (existing) ss.deleteSheet(existing);
  const debugSheet = ss.insertSheet(tabName);

  const sheet = getOutreachQueueSheet_();
  const read = readFlatSheetRows_(sheet, HEADER_ROW.OUTREACH_QUEUE);
  const draftKey = normalizeHeader_(DRAFT_COLUMN_HEADER);
  const sentKey = normalizeHeader_(SENT_CHECKBOX_HEADER);
  const platformLookup = buildPlatformLookupFromTracker_();
  const linksLookup = buildLinksLookupFromTracker_();

  const out = [['Row', 'Type', 'Creator Handle', 'First Name', 'Platform', 'Needs links?', 'Links found?', 'Pieces', 'Amount', 'Ready?', 'Why skipped']];
  read.rows.forEach((row) => {
    const handle = String(row['creator handle'] || '').trim();
    const rowType = String(row[normalizeHeader_(TYPE_COLUMN_HEADER)] || '').trim();
    const firstName = String(row['first name'] || '').trim();
    const displayName = firstName || (handle ? handle.replace(/^@/, '').split(/[._]/)[0] : '');
    const platform = String(row[normalizeHeader_(PLATFORM_COLUMN_HEADER)] || row['platform (auto)'] || row['platform'] || '').trim()
      || lookupPlatformsForHandleFromTracker_(handle, platformLookup);
    const needsLinks = needsProductLinksForPlatforms_(platform);
    const linksFromRow = resolveOutreachLinks_(row, handle, linksLookup);

    let pieces = Number(String(row['new pieces of content used'] || '').trim());
    if (!pieces || pieces < 1) pieces = 1;
    const piecesNote = String(row['new pieces of content used'] || '').trim() || '(default 1)';

    let amount = String(row['gift card amount'] || '').trim();
    const amountNote = amount || formatAmount_(calculateGiftCardAmount_(pieces));

    const alreadyDrafted = !!row[draftKey];
    const alreadySent = !!row[sentKey];
    const ready = !alreadyDrafted && !alreadySent && !!displayName && (!needsLinks || !!linksFromRow);
    const why = [];
    if (alreadyDrafted) why.push('already has draft');
    if (alreadySent) why.push('already sent');
    if (!displayName) why.push('missing name');
    if (needsLinks && !linksFromRow) why.push('missing link');

    out.push([
      row._sheetRow,
      rowType || '(blank)',
      handle,
      firstName || '(blank)',
      platform || '(blank)',
      needsLinks ? 'yes' : 'no (AppLovin)',
      linksFromRow ? 'yes' : 'NO',
      piecesNote,
      amountNote,
      ready ? 'YES' : 'no',
      why.join('; ') || '—',
    ]);
  });

  debugSheet.getRange(1, 1, out.length, out[0].length).setValues(out);
  debugSheet.getRange(1, 1, 1, out[0].length).setFontWeight('bold');
  debugSheet.autoResizeColumns(1, out[0].length);
  if (!silent) {
    SpreadsheetApp.getUi().alert('Done. Open the "Draft Readiness Debug" tab to see which rows are missing a name or link.');
  }
}

function testDraftReadiness_() {
  writeDraftReadinessDebug_(false);
}

/**
 * Fills a dupe row's link/SKU-type fields from the original (first) row that
 * shares the same Unique Identifier, but ONLY into cells that are currently
 * blank - never overwrites anything a human already entered. Leaves a note
 * flagging it as auto-filled so Adriana can still spot-check per the existing
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
        const destEmpty = String(values[i][idx] || '').trim() === '';
        const srcVal = values[j][idx];
        if (destEmpty && String(srcVal || '').trim() !== '') {
          values[i][idx] = srcVal;
          filledAny = true;
        }
      });
      if (filledAny) {
        const lastCol = sheet.getLastColumn();
        sheet.getRange(sheetRow, 1, 1, lastCol).setValues([values[i]]);
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

function appendToOutreachQueue_(type, rows) {
  if (!rows.length) return 0;
  const sheet = getOutreachQueueSheet_();
  const headerRowNum = HEADER_ROW.OUTREACH_QUEUE;
  const lastCol = sheet.getLastColumn();
  const headers = sheet.getRange(headerRowNum, 1, 1, lastCol).getValues()[0];
  const headerIndex = buildHeaderIndex_(headers);
  const typeKey = normalizeHeader_(TYPE_COLUMN_HEADER);
  ['creator handle', 'first name', 'new pieces of content used', 'gift card amount', 'email address', 'links'].forEach((h) => colIndex_(headerIndex, h, true));
  const platformIdx = colIndex_(headerIndex, PLATFORM_COLUMN_HEADER, false);

  const startRow = sheet.getLastRow() + 1;
  const out = rows.map((r) => {
    const arr = new Array(lastCol).fill('');
    arr[headerIndex[typeKey]] = type;
    arr[headerIndex['creator handle']] = r.handle;
    arr[headerIndex['first name']] = r.firstName || '';
    if ('last name' in headerIndex) arr[headerIndex['last name']] = r.lastName || '';
    arr[headerIndex['new pieces of content used']] = r.newPieces;
    arr[headerIndex['gift card amount']] = r.amount;
    arr[headerIndex['email address']] = r.email || '';
    arr[headerIndex['links']] = r.links || '';
    if (platformIdx !== -1 && r.platform) arr[platformIdx] = r.platform;
    return arr;
  });
  sheet.getRange(startRow, 1, out.length, lastCol).setValues(out);
  return out.length;
}

/** Drafts all undrafted, unsent rows on the Outreach Queue tab. */
function draftOutreachMessages(silent) {
  const sheet = getOutreachQueueSheet_();
  const read = readFlatSheetRows_(sheet, HEADER_ROW.OUTREACH_QUEUE);
  const draftKey = normalizeHeader_(DRAFT_COLUMN_HEADER);
  const sentKey = normalizeHeader_(SENT_CHECKBOX_HEADER);
  const typeKey = normalizeHeader_(TYPE_COLUMN_HEADER);
  const draftCol = read.headerIndex[draftKey] + 1;
  const platformKey = normalizeHeader_(PLATFORM_COLUMN_HEADER);
  const platformLookup = buildPlatformLookupFromTracker_();
  const linksLookup = buildLinksLookupFromTracker_();
  const draftUpdates = [];

  let drafted = 0, skipped = 0, skippedNoName = 0, skippedNoLinks = 0;
  let alreadyDrafted = 0, alreadySent = 0;
  read.rows.forEach((row) => {
    if (row[draftKey]) { alreadyDrafted++; return; }
    if (row[sentKey]) { alreadySent++; return; }

    const firstName = String(row['first name'] || '').trim();
    const handle = String(row['creator handle'] || '').trim();
    const displayName = firstName || (handle ? capitalizeFirst_(handle.replace(/^@/, '').split(/[._]/)[0]) : '');
    const rowType = String(row[typeKey] || '').trim();
    const isFollowUp = rowType === OUTREACH_TYPE_FOLLOWUP;

    const platform = String(row[platformKey] || '').trim()
      || lookupPlatformsForHandleFromTracker_(handle, platformLookup);
    const needsLinks = needsProductLinksForPlatforms_(platform);
    const links = resolveOutreachLinks_(row, handle, linksLookup);

    if (!displayName) { skipped++; skippedNoName++; return; }
    if (needsLinks && !links) { skipped++; skippedNoLinks++; return; }

    let newPieces = Number(row['new pieces of content used']) || 1;
    if (newPieces < 1) newPieces = 1;
    let amount = String(row['gift card amount'] || '').trim();
    if (!amount) amount = formatAmount_(calculateGiftCardAmount_(newPieces));

    const filled = buildDraftMessage_({
      isFollowUp: isFollowUp,
      handle: handle,
      firstName: displayName,
      pieces: newPieces,
      newPieces: newPieces,
      amount: amount,
      links: links,
      needsLinks: needsLinks,
    });
    draftUpdates.push({ row: row._sheetRow, value: filled });
    drafted++;
  });

  batchSetColumnValues_(sheet, draftCol, draftUpdates);

  const result = { drafted: drafted, skipped: skipped, skippedNoName: skippedNoName, skippedNoLinks: skippedNoLinks, alreadyDrafted: alreadyDrafted, alreadySent: alreadySent };
  if (!silent) {
    let msg = 'Drafted ' + drafted + ' message(s) on Outreach Queue.';
    if (skipped) {
      msg += ' ' + skipped + ' skipped';
      const reasons = [];
      if (skippedNoName) reasons.push(skippedNoName + ' missing a name');
      if (skippedNoLinks) reasons.push(skippedNoLinks + ' missing a link');
      if (reasons.length) msg += ' (' + reasons.join(', ') + ')';
      msg += '. Run Setup > Test draft readiness for details.';
    }
    toast_(msg);
  }
  return result;
}

/**
 * Optional: when Adriana checks "Sent?" on a message row, flip the matching
 * Boosting Tracker rows for that creator from QUEUED_MARKER to "Yes" so the
 * tracker reflects that the creator was actually notified (not just queued).
 * Wire this up as an installable "On edit" trigger if desired.
 */
function onEditMarkSent(e) {
  if (!e || !e.range) return;
  const sheet = e.range.getSheet();
  const sheetName = sheet.getName();
  if (sheetName !== SHEET_NAMES.OUTREACH_QUEUE) return;

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
  const ctx = getGiftCardContext_();
  const nameKey = ctx.nameKey;
  const rows = readGiftCardRows_(ctx).filter((r) => String(r[nameKey] || '').trim() !== '');

  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const existing = ss.getSheetByName(SHEET_NAMES.EOM_EXPORT);
  if (existing) ss.deleteSheet(existing);
  const exportSheet = ss.insertSheet(SHEET_NAMES.EOM_EXPORT);

  const exportCols = ['creator handle', 'first name', 'last name', 'new pieces of content used', 'gift card amount', 'email address']
    .filter((c) => c in ctx.headerIndex || c === nameKey);
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
    complete.length + ' creator(s) ready to export from "' + ctx.sheet.getName() + '", ' +
    missingEmail.length + ' still missing an email. See the "' + SHEET_NAMES.EOM_EXPORT + '" tab.'
  );
}
