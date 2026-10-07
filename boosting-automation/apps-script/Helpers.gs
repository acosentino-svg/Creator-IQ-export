/**
 * Helpers.gs
 * Generic utilities shared by Automation.gs: header lookup, month-block
 * detection in the Monthly Gift Card Cost Tracker, and handle normalization.
 */

function getSheet_(name) {
  if (name === SHEET_NAMES.NEW_CREATORS_MSG && EXTERNAL_SHEET_IDS.NEW_CREATORS_MSG) {
    return getExternalSheet_(EXTERNAL_SHEET_IDS.NEW_CREATORS_MSG);
  }
  if (name === SHEET_NAMES.FOLLOWUP_MSG && EXTERNAL_SHEET_IDS.FOLLOWUP_MSG) {
    return getExternalSheet_(EXTERNAL_SHEET_IDS.FOLLOWUP_MSG);
  }
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(name);
  if (!sheet) throw new Error('Tab not found: "' + name + '". Check SHEET_NAMES / EXTERNAL_SHEET_IDS in Config.gs.');
  return sheet;
}

/** Opens a different Google Sheets file by URL or bare ID and returns its first tab. */
function getExternalSheet_(urlOrId) {
  const id = extractSpreadsheetId_(urlOrId);
  const ss = SpreadsheetApp.openById(id);
  return ss.getSheetByName('Sheet1') || ss.getSheets()[0];
}

function extractSpreadsheetId_(urlOrId) {
  const match = String(urlOrId).match(/[-\w]{25,}/);
  if (!match) throw new Error('Could not find a spreadsheet ID inside "' + urlOrId + '". Paste the full URL or just the long ID from it.');
  return match[0];
}

/**
 * The Names lookup tab lives alongside wherever the New Boosted Creators
 * sheet lives (same file, different tab) - so reuse EXTERNAL_SHEET_IDS if
 * that sheet is external, or fall back to the currently active spreadsheet
 * if it's just a tab in this same file. Returns null (never throws) if the
 * tab doesn't exist yet, so name-lookup is always optional/best-effort.
 */
function getNamesLookupSheet_() {
  try {
    let ss;
    if (EXTERNAL_SHEET_IDS.NEW_CREATORS_MSG) {
      ss = SpreadsheetApp.openById(extractSpreadsheetId_(EXTERNAL_SHEET_IDS.NEW_CREATORS_MSG));
    } else {
      ss = SpreadsheetApp.getActiveSpreadsheet();
    }
    return ss.getSheetByName(NAMES_LOOKUP_SHEET_NAME) || null;
  } catch (e) {
    console.warn('getNamesLookupSheet_ failed: ' + e);
    return null;
  }
}

/** "Alexis Pratt" -> { firstName: "Alexis", lastName: "Pratt" }. Single-word names get a blank last name. */
function splitFullName_(fullName) {
  const parts = String(fullName || '').trim().split(/\s+/).filter(Boolean);
  return { firstName: parts[0] || '', lastName: parts.slice(1).join(' ') };
}

/**
 * Reads the Names lookup tab (publisher_name + one-or-more *_account_name
 * columns) into { normalizedHandle -> { firstName, lastName } }, matching a
 * handle against ANY platform column found (Instagram, TikTok, etc.) so it
 * doesn't matter which platform the Boosting Tracker's handle came from.
 * Returns {} (never throws) if the tab is missing or empty.
 */
function buildNameLookup_() {
  const lookup = {};
  const sheet = getNamesLookupSheet_();
  if (!sheet) return lookup;

  const lastRow = sheet.getLastRow();
  const lastCol = sheet.getLastColumn();
  if (lastRow < 2 || lastCol < 1) return lookup;

  const headerIndex = buildHeaderIndex_(sheet.getRange(1, 1, 1, lastCol).getValues()[0]);
  const nameCol = ['publisher_name', 'full name', 'name', 'creator name']
    .map((k) => headerIndex[k]).find((v) => v != null);
  const handleCols = Object.keys(headerIndex)
    .filter((k) => k.indexOf('account_name') !== -1 || k.indexOf('handle') !== -1)
    .map((k) => headerIndex[k]);
  if (nameCol == null || !handleCols.length) return lookup;

  const values = sheet.getRange(2, 1, lastRow - 1, lastCol).getValues();
  values.forEach((row) => {
    const fullName = String(row[nameCol] || '').trim();
    if (!fullName) return;
    const parsed = splitFullName_(fullName);
    handleCols.forEach((col) => {
      const handle = normalizeHandle_(row[col]);
      if (handle) lookup[handle] = parsed;
    });
  });
  return lookup;
}

/** Trims + lowercases so header lookups survive stray spaces ("  Fav's List..."). */
function normalizeHeader_(h) {
  return String(h || '').trim().toLowerCase();
}

function normalizeHandle_(h) {
  return String(h || '').trim().toLowerCase().replace(/^@/, '');
}

/**
 * Builds { headerName -> 0-based column offset } for a single header row.
 * @param {Array} headerRowValues Row values (e.g. sheet.getRange(row,1,1,numCols).getValues()[0])
 */
function buildHeaderIndex_(headerRowValues) {
  const index = {};
  headerRowValues.forEach((h, i) => {
    const key = normalizeHeader_(h);
    if (key) index[key] = i;
  });
  return index;
}

function colIndex_(headerIndex, name, required) {
  const key = normalizeHeader_(name);
  if (!(key in headerIndex)) {
    if (required) throw new Error('Expected column "' + name + '" not found. Headers seen: ' + Object.keys(headerIndex).join(', '));
    return -1;
  }
  return headerIndex[key];
}

/**
 * The Monthly Gift Card Cost Tracker lays months out side-by-side:
 * row 1 has a label (e.g. "July") only in the first column of each block,
 * row 2 has that block's real field headers. Block width = distance to the
 * next labeled column (or sheet edge). The right-most labeled block is
 * always the current month, since Step 0 appends new months to the right.
 */
function getMonthBlocks_(sheet) {
  const lastCol = sheet.getLastColumn();
  const labelRow = sheet.getRange(HEADER_ROW.GIFT_CARD_TRACKER_MONTH_LABEL_ROW, 1, 1, lastCol).getValues()[0];
  const starts = [];
  labelRow.forEach((v, i) => {
    if (String(v || '').trim() !== '') starts.push(i); // 0-based col offset
  });
  if (starts.length === 0) throw new Error('No month labels found in row ' + HEADER_ROW.GIFT_CARD_TRACKER_MONTH_LABEL_ROW + ' of "' + SHEET_NAMES.GIFT_CARD_TRACKER + '".');

  const fieldRow = sheet.getRange(HEADER_ROW.GIFT_CARD_TRACKER_FIELD_ROW, 1, 1, lastCol).getValues()[0];
  return starts.map((startCol, i) => {
    const endCol = i + 1 < starts.length ? starts[i + 1] - 1 : lastCol - 1; // 0-based, inclusive
    const headers = fieldRow.slice(startCol, endCol + 1);
    return {
      label: String(labelRow[startCol]).trim(),
      startCol: startCol, // 0-based
      endCol: endCol, // 0-based inclusive
      width: endCol - startCol + 1,
      headerIndex: buildHeaderIndex_(headers),
    };
  });
}

function getCurrentMonthBlock_(sheet) {
  const blocks = getMonthBlocks_(sheet);
  return blocks[blocks.length - 1];
}

/** Reads the current month block as an array of row objects keyed by header name. */
function readBlockRows_(sheet, block) {
  const lastRow = sheet.getLastRow();
  const startDataRow = HEADER_ROW.GIFT_CARD_TRACKER_FIELD_ROW + 1; // 1-based
  if (lastRow < startDataRow) return [];
  const range = sheet.getRange(startDataRow, block.startCol + 1, lastRow - startDataRow + 1, block.width);
  const values = range.getValues();
  const rows = [];
  values.forEach((rowVals, i) => {
    const obj = { _sheetRow: startDataRow + i, _range: range };
    Object.keys(block.headerIndex).forEach((key) => {
      obj[key] = rowVals[block.headerIndex[key]];
    });
    rows.push(obj);
  });
  return rows;
}

/**
 * Reads a simple, single-header-row sheet (the message sheets, not the
 * multi-block Gift Card Tracker) into an array of row objects keyed by
 * normalized header name, each carrying its own _sheetRow.
 */
function readFlatSheetRows_(sheet, headerRowNum) {
  const lastRow = sheet.getLastRow();
  const lastCol = sheet.getLastColumn();
  const startDataRow = headerRowNum + 1;
  if (lastRow < startDataRow) return { headerIndex: buildHeaderIndex_(sheet.getRange(headerRowNum, 1, 1, lastCol).getValues()[0]), rows: [] };
  const headerIndex = buildHeaderIndex_(sheet.getRange(headerRowNum, 1, 1, lastCol).getValues()[0]);
  const values = sheet.getRange(startDataRow, 1, lastRow - startDataRow + 1, lastCol).getValues();
  const rows = values.map((rowVals, i) => {
    const obj = { _sheetRow: startDataRow + i };
    Object.keys(headerIndex).forEach((key) => { obj[key] = rowVals[headerIndex[key]]; });
    return obj;
  });
  return { headerIndex: headerIndex, rows: rows };
}

function ensureColumn_(sheet, headerRowNum, headerText) {
  const lastCol = sheet.getLastColumn();
  const headers = sheet.getRange(headerRowNum, 1, 1, lastCol).getValues()[0];
  const idx = headers.findIndex((h) => normalizeHeader_(h) === normalizeHeader_(headerText));
  if (idx !== -1) return idx + 1; // 1-based
  const newCol = lastCol + 1;
  sheet.getRange(headerRowNum, newCol).setValue(headerText);
  return newCol;
}

function toast_(msg) {
  SpreadsheetApp.getActiveSpreadsheet().toast(msg, 'Boosting Automation');
}
