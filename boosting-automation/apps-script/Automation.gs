/**
 * Automation.gs
 * Menu + boosting workflow:
 *   Boosting Tracker -> Google Doc (emails) -> CreatorIQ send ->
 *   email pasted on tracker -> Gift Card month tab (auto).
 */

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Boosting Automation')
    .addItem('Monday check (scan tracker + write emails to Doc)', 'mondayCheck')
    .addItem('Open today\'s outreach drafts doc', 'openOutreachDraftsDoc_')
    .addSeparator()
    .addItem('1. Start new month (gift card tab)', 'startNewMonth')
    .addItem('2. End-of-month export (Step 5)', 'exportEndOfMonth')
    .addSeparator()
    .addItem('Regenerate outreach drafts doc', 'draftOutreachMessages')
    .addItem('Turn ON automatic weekly sync', 'enableAutoSync')
    .addItem('Turn OFF automatic sync', 'disableAutoSync')
    .addSeparator()
    .addItem('Setup: Test Names lookup (diagnostic)', 'testNameLookup_')
    .addItem('Setup: Choose active gift card month', 'chooseActiveGiftCardMonth_')
    .addToUi();
}

/** One click: read tracker dates, create month gift card tab, write emails to Google Doc. */
function mondayCheck() {
  toast_('Monday check: reading dates in column D...');
  const monthResult = ensureGiftCardMonthTabForTracker_();
  if (monthResult.created) {
    toast_('Created gift card tab: ' + monthResult.tabName);
  } else if (monthResult.inferred) {
    toast_('Using gift card tab: ' + monthResult.tabName + ' (from column D on pending rows)');
  }

  toast_('Monday check: scanning Boosting Tracker (skipping dupes)...');
  const draftResult = draftOutreachMessages(true);

  let msg = 'Monday check done: ' + draftResult.queued + ' video(s) queued';
  if (draftResult.skippedDupes) msg += ', ' + draftResult.skippedDupes + ' dupe(s) skipped';
  if (draftResult.skippedRepeatLinks) msg += ', ' + draftResult.skippedRepeatLinks + ' repeat link(s) ignored';
  msg += '. Wrote ' + draftResult.drafted + ' email(s) to Google Doc';
  if (draftResult.skippedCount) {
    msg += '. ' + draftResult.skippedCount + ' creator(s) need a name or link (see bottom of doc)';
  }
  msg += '. Gift card tab: ' + getActiveGiftCardSheetName_() + '.';
  toast_(msg);
}

const AUTO_SYNC_HANDLER = 'runScheduledSync';

function enableAutoSync() {
  disableAutoSync();
  ScriptApp.newTrigger(AUTO_SYNC_HANDLER).timeBased().onWeekDay(ScriptApp.WeekDay.MONDAY).atHour(8).create();
  SpreadsheetApp.getUi().alert('Automatic Monday 8am sync is ON.');
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
  const inferred = inferGiftCardMonthFromTracker_();
  const detected = inferred ? inferred.monthName : '';
  let prompt = 'Month for the new gift card tab (e.g. "August").';
  if (detected) {
    prompt += '\n\nDetected from Boosting Tracker column D: ' + detected +
      '\nLeave blank and click OK to use that month.';
  }

  const resp = ui.prompt('Start new month', prompt, ui.ButtonSet.OK_CANCEL);
  if (resp.getSelectedButton() !== ui.Button.OK) return;
  let input = resp.getResponseText().trim();
  if (!input && detected) input = detected;
  if (!input) return;

  let monthName = normalizeMonthName_(input);
  if (!monthName) {
    const parsed = parseMonthYearInput_(input);
    if (parsed) monthName = parsed.monthName;
  }
  if (!monthName) {
    ui.alert('Please enter a month name like "August".');
    return;
  }

  const tabName = formatGiftCardMonthTabName_(monthName);
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  if (ss.getSheetByName(tabName)) {
    setActiveGiftCardSheet_(tabName);
    ui.alert('Tab "' + tabName + '" already exists — it is now the active gift card month.');
    ss.setActiveSheet(ss.getSheetByName(tabName));
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
    'Created "' + tabName + '".\n\n' +
    'Update the Gift Card Amount formula on this tab if this month uses a special comp/activation.'
  );
  ss.setActiveSheet(newSheet);
}

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

function testNameLookup_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const existing = ss.getSheetByName('Names Lookup Debug');
  if (existing) ss.deleteSheet(existing);
  const debugSheet = ss.insertSheet('Names Lookup Debug');

  const rows = [['Check', 'Result']];
  rows.push(['NAMES_LOOKUP_SHEET_NAME configured as', NAMES_LOOKUP_SHEET_NAME]);
  rows.push(['EXTERNAL_NAMES_SHEET_ID set?', EXTERNAL_NAMES_SHEET_ID ? 'yes' : 'no']);

  const namesSheet = getNamesLookupSheet_();
  rows.push(['Names tab found?', namesSheet ? 'YES' : 'NO']);

  const lookup = buildNameLookup_();
  const keys = Object.keys(lookup);
  rows.push(['Total handles matched', keys.length]);
  rows.push(['Sample matches (up to 5)', keys.slice(0, 5).map((k) => k + ' -> ' + lookup[k].firstName + ' ' + lookup[k].lastName).join('  |  ')]);

  debugSheet.getRange(1, 1, rows.length, 2).setValues(rows);
  debugSheet.autoResizeColumns(1, 2);
  SpreadsheetApp.getUi().alert('Done. Check the "Names Lookup Debug" tab.');
}

/** Scans Boosting Tracker and writes outreach emails to today's Google Doc. */
function draftOutreachMessages(silent) {
  const collectResult = scanBoostingTrackerForMonday_();
  const docResult = writeOutreachDraftsGoogleDoc_(collectResult);
  const result = {
    drafted: collectResult.drafted,
    skippedCount: collectResult.skippedCount,
    skippedNoName: collectResult.skippedNoName,
    skippedNoLinks: collectResult.skippedNoLinks,
    queued: collectResult.queued,
    skippedDupes: collectResult.skippedDupes,
    skippedRepeatLinks: collectResult.skippedRepeatLinks,
    emailRows: collectResult.emailRows,
    docUrl: docResult.url,
    docId: docResult.id,
  };

  if (!silent) {
    let msg = 'Wrote ' + result.drafted + ' email(s) to Google Doc.';
    if (result.skippedCount) msg += ' ' + result.skippedCount + ' need fixes (see doc).';
    toast_(msg);
  }
  return result;
}

/**
 * Fills a dupe row's link/SKU-type fields from the original row sharing the
 * same Unique Identifier. Only fills blank cells.
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
          'Auto-filled from matching Unique Identifier "' + uid + '". Spot-check with Ctrl+F before trusting.'
        );
      }
      return filledAny;
    }
  }
  return false;
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
