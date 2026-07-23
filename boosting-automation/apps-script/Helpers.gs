/**
 * Helpers.gs
 * Generic utilities shared by Automation.gs: header lookup, gift card month-tab
 * helpers (one tab per month, e.g. "July 2026 Gift Card Cost Tracker"), and
 * handle normalization. Legacy horizontal "Monthly Gift Card Cost Tracker" is
 * still supported as a fallback.
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

function isAppLovinPlatform_(platform) {
  return String(platform || '').trim().toLowerCase().indexOf('applovin') !== -1;
}

/** True when at least one synced platform is not AppLovin (or platform is unknown). */
function needsProductLinksForPlatforms_(platforms) {
  const list = Array.isArray(platforms) ? platforms : String(platforms || '').split(/[,;]/);
  const cleaned = list.map((p) => String(p || '').trim()).filter(Boolean);
  if (!cleaned.length) return true;
  return cleaned.some((p) => !isAppLovinPlatform_(p));
}

function mergePlatformLabels_(existing, incoming) {
  const set = {};
  String(existing || '').split(/[,;]/).concat(String(incoming || '').split(/[,;]/)).forEach((p) => {
    const label = String(p || '').trim();
    if (label) set[label] = true;
  });
  return Object.keys(set).join(', ');
}

/** 1 piece = $100, each additional piece = +$50. */
function calculateGiftCardAmount_(pieces) {
  const n = Number(pieces) || 0;
  if (n <= 0) return 0;
  return GIFT_CARD_BASE_AMOUNT + GIFT_CARD_INCREMENT_AMOUNT * (n - 1);
}

function formatAmount_(value) {
  const num = typeof value === 'string' ? parseFloat(String(value).replace(/[^0-9.]/g, '')) : Number(value);
  if (isNaN(num)) return '';
  return '$' + (num % 1 === 0 ? String(num) : num.toFixed(2));
}

function formatPiecesLabel_(pieces) {
  const n = Number(pieces) || 0;
  if (n === 1) return '1 piece';
  return n + ' pieces';
}

function formatMorePiecesLabel_(pieces) {
  const n = Number(pieces) || 0;
  if (n === 1) return '1 more piece';
  return n + ' more pieces';
}

function capitalizeFirst_(text) {
  const t = String(text || '').trim();
  if (!t) return t;
  if (t !== t.toLowerCase() && t !== t.toUpperCase()) return t;
  return t.charAt(0).toUpperCase() + t.slice(1).toLowerCase();
}

function splitLinks_(linksText) {
  return String(linksText || '').split(/[\n,]+/).map((s) => s.trim()).filter(Boolean);
}

function formatSelectedVideosPhrase_(linkCount) {
  return linkCount === 1 ? 'just this selected video' : 'just these selected videos';
}

/** True if this creator already received an initial boost this month. */
function isAlreadyBoostedThisMonth_(handle) {
  const handleKey = normalizeHandle_(handle);
  if (!handleKey) return false;

  try {
    const ctx = getGiftCardContext_();
    const rows = readGiftCardRows_(ctx);
    if (rows.some((r) => normalizeHandle_(r[ctx.nameKey]) === handleKey && String(r[ctx.nameKey] || '').trim() !== '')) {
      return true;
    }
  } catch (e) { /* optional */ }

  try {
    const msgSheet = getSheet_(SHEET_NAMES.NEW_CREATORS_MSG);
    const read = readFlatSheetRows_(msgSheet, HEADER_ROW.NEW_CREATORS_MSG);
    const sentKey = normalizeHeader_(SENT_CHECKBOX_HEADER);
    if (read.rows.some((r) => normalizeHandle_(r['creator handle']) === handleKey && r[sentKey])) {
      return true;
    }
  } catch (e) { /* optional */ }

  return false;
}

/**
 * Picks the right template and fills it. New-creator vs incremental is based on
 * the sheet (Follow-Up = incremental) or whether they were already boosted.
 */
function buildDraftMessage_(opts) {
  const firstName = capitalizeFirst_(opts.firstName || '');
  const pieces = Number(opts.pieces) || 1;
  const newPieces = Number(opts.newPieces) || pieces;
  const links = String(opts.links || '').trim();
  const linkList = splitLinks_(links);
  const linkCount = linkList.length || (links ? 1 : 0);
  const needsLinks = opts.needsLinks !== false;
  const isFollowUp = !!opts.isFollowUp || isAlreadyBoostedThisMonth_(opts.handle);

  let amount = opts.amount;
  if (!amount) {
    amount = formatAmount_(isFollowUp && newPieces < pieces
      ? calculateGiftCardAmount_(pieces)
      : calculateGiftCardAmount_(isFollowUp ? newPieces : pieces));
  } else if (String(amount).indexOf('$') === -1) {
    amount = formatAmount_(amount);
  }

  const values = {
    FIRST_NAME: firstName,
    PIECES_LABEL: formatPiecesLabel_(pieces),
    NEW_PIECES_LABEL: formatMorePiecesLabel_(newPieces),
    AMOUNT: amount,
    INCREMENT_AMOUNT: formatAmount_(GIFT_CARD_INCREMENT_AMOUNT * newPieces),
    SELECTED_VIDEOS_PHRASE: formatSelectedVideosPhrase_(linkCount),
    LINKS: links,
  };

  let template;
  if (isFollowUp) {
    if (newPieces === 1) {
      template = needsLinks ? INCREMENTAL_SINGLE_PROMPT : INCREMENTAL_SINGLE_PROMPT_NO_LINKS;
    } else {
      template = needsLinks ? INCREMENTAL_MULTI_PROMPT : INCREMENTAL_MULTI_PROMPT_NO_LINKS;
    }
  } else {
    template = needsLinks ? NEW_CREATOR_PROMPT : NEW_CREATOR_PROMPT_NO_LINKS;
  }

  return fillTemplate_(template, values);
}

/** Fallback for message rows synced before Platform (auto) existed. */
function lookupPlatformsForHandleFromTracker_(handle) {
  const trackerSheet = getSheet_(SHEET_NAMES.BOOSTING_TRACKER);
  const lastRow = trackerSheet.getLastRow();
  const lastCol = trackerSheet.getLastColumn();
  if (lastRow < HEADER_ROW.BOOSTING_TRACKER + 1) return '';

  const headers = trackerSheet.getRange(HEADER_ROW.BOOSTING_TRACKER, 1, 1, lastCol).getValues()[0];
  const headerIndex = buildHeaderIndex_(headers);
  const nameIdx = colIndex_(headerIndex, 'creator name', false);
  const platformIdx = colIndex_(headerIndex, 'platform(s) for usage', false);
  if (nameIdx === -1 || platformIdx === -1) return '';

  const handleKey = normalizeHandle_(handle);
  const values = trackerSheet.getRange(HEADER_ROW.BOOSTING_TRACKER + 1, 1, lastRow - HEADER_ROW.BOOSTING_TRACKER, lastCol).getValues();
  const platforms = [];
  values.forEach((row) => {
    if (normalizeHandle_(row[nameIdx]) !== handleKey) return;
    const platform = String(row[platformIdx] || '').trim();
    if (platform) platforms.push(platform);
  });
  return mergePlatformLabels_('', platforms.join(', '));
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

// --- Per-month gift card tabs (e.g. "July 2026 Gift Card Cost Tracker") ---

const GIFT_CARD_MONTH_NAMES_ = [
  'january', 'february', 'march', 'april', 'may', 'june',
  'july', 'august', 'september', 'october', 'november', 'december',
];

/** Builds the tab name: "July 2026 Gift Card Cost Tracker". */
function formatGiftCardMonthTabName_(monthName, year) {
  const month = String(monthName || '').trim();
  const y = Number(year);
  if (!month || !y) throw new Error('Month and year are required (e.g. July 2026).');
  return month + ' ' + y + ' ' + GIFT_CARD_MONTH_TAB_SUFFIX;
}

/** Parses "July 2026 Gift Card Cost Tracker" -> { month, year, monthIndex, sortKey }. */
function parseGiftCardMonthTabName_(tabName) {
  const suffix = ' ' + GIFT_CARD_MONTH_TAB_SUFFIX;
  const name = String(tabName || '').trim();
  if (!name.endsWith(suffix)) return null;
  const prefix = name.slice(0, -suffix.length).trim();
  const match = prefix.match(/^(\w+)\s+(\d{4})$/);
  if (!match) return null;
  const monthIndex = GIFT_CARD_MONTH_NAMES_.indexOf(match[1].toLowerCase());
  if (monthIndex === -1) return null;
  const year = parseInt(match[2], 10);
  return {
    month: match[1],
    year: year,
    monthIndex: monthIndex,
    sortKey: year * 12 + monthIndex,
    tabName: name,
  };
}

function isGiftCardMonthTabName_(tabName) {
  return parseGiftCardMonthTabName_(tabName) != null;
}

function isLegacyGiftCardSheet_(sheet) {
  return sheet.getName() === SHEET_NAMES.GIFT_CARD_LEGACY;
}

function listGiftCardMonthTabs_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  return ss.getSheets()
    .map((s) => parseGiftCardMonthTabName_(s.getName()))
    .filter(Boolean)
    .sort((a, b) => a.sortKey - b.sortKey);
}

function getActiveGiftCardSheetName_() {
  const stored = PropertiesService.getScriptProperties().getProperty(ACTIVE_GIFT_CARD_SHEET_PROPERTY);
  if (stored) {
    const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(stored);
    if (sheet) return stored;
  }
  const tabs = listGiftCardMonthTabs_();
  if (tabs.length) return tabs[tabs.length - 1].tabName;
  return SHEET_NAMES.GIFT_CARD_LEGACY;
}

function getActiveGiftCardSheet_() {
  const name = getActiveGiftCardSheetName_();
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(name);
  if (!sheet) {
    throw new Error(
      'Gift card tracker tab not found: "' + name + '". Run "Start new month" or create a tab like "July 2026 Gift Card Cost Tracker".'
    );
  }
  return sheet;
}

function setActiveGiftCardSheet_(tabName) {
  PropertiesService.getScriptProperties().setProperty(ACTIVE_GIFT_CARD_SHEET_PROPERTY, tabName);
}

function getGiftCardHeaderRow_(sheet) {
  if (isLegacyGiftCardSheet_(sheet)) return HEADER_ROW.GIFT_CARD_TRACKER_FIELD_ROW;
  if (isGiftCardMonthTabName_(sheet.getName())) return HEADER_ROW.GIFT_CARD_TRACKER;
  const lastCol = Math.max(sheet.getLastColumn(), 1);
  const row1 = buildHeaderIndex_(sheet.getRange(1, 1, 1, lastCol).getValues()[0]);
  if ('creator handle' in row1 || 'creator name' in row1) return HEADER_ROW.GIFT_CARD_TRACKER;
  return HEADER_ROW.GIFT_CARD_TRACKER_FIELD_ROW;
}

/**
 * Returns everything needed to read/write the active gift card month.
 * Supports per-month tabs and the legacy horizontal layout.
 */
function getGiftCardContext_() {
  const sheet = getActiveGiftCardSheet_();
  const isLegacy = isLegacyGiftCardSheet_(sheet);
  if (isLegacy) {
    const block = getCurrentMonthBlock_(sheet);
    return {
      sheet: sheet,
      isLegacy: true,
      headerRow: HEADER_ROW.GIFT_CARD_TRACKER_FIELD_ROW,
      headerIndex: block.headerIndex,
      block: block,
      nameKey: ('creator handle' in block.headerIndex) ? 'creator handle' : 'creator name',
    };
  }
  const headerRow = getGiftCardHeaderRow_(sheet);
  const lastCol = sheet.getLastColumn();
  const headerIndex = buildHeaderIndex_(sheet.getRange(headerRow, 1, 1, lastCol).getValues()[0]);
  return {
    sheet: sheet,
    isLegacy: false,
    headerRow: headerRow,
    headerIndex: headerIndex,
    block: null,
    nameKey: ('creator handle' in headerIndex) ? 'creator handle' : 'creator name',
  };
}

/** 1-based column number for a header on the active gift card sheet. */
function giftCardCol1_(ctx, headerName, required) {
  const offset = colIndex_(ctx.headerIndex, headerName, required !== false);
  if (offset === -1) return -1;
  return ctx.isLegacy ? ctx.block.startCol + offset + 1 : offset + 1;
}

function readGiftCardRows_(ctx) {
  if (ctx.isLegacy) return readBlockRows_(ctx.sheet, ctx.block);
  const read = readFlatSheetRows_(ctx.sheet, ctx.headerRow);
  return read.rows;
}

function setGiftCardCell_(ctx, row, headerName, value) {
  const col = giftCardCol1_(ctx, headerName, true);
  ctx.sheet.getRange(row, col).setValue(value);
}

function findNextEmptyGiftCardRow_(ctx, rows) {
  const startDataRow = ctx.headerRow + 1;
  let nextEmptyRow = startDataRow;
  let foundGap = false;
  rows.forEach((r) => {
    const h = normalizeHandle_(r[ctx.nameKey]);
    if (!h && !foundGap) { nextEmptyRow = r._sheetRow; foundGap = true; }
  });
  if (!foundGap) {
    nextEmptyRow = rows.length ? rows[rows.length - 1]._sheetRow + 1 : startDataRow;
  }
  return nextEmptyRow;
}

/**
 * Copies the template (or the current month tab) to start a new month tab.
 * Returns the new Sheet object.
 */
function createGiftCardMonthTab_(tabName) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  if (ss.getSheetByName(tabName)) {
    throw new Error('A tab named "' + tabName + '" already exists.');
  }

  const template = ss.getSheetByName(SHEET_NAMES.GIFT_CARD_TEMPLATE);
  if (template) {
    return copyGiftCardMonthTab_(template, tabName);
  }

  let source = null;
  try {
    source = getActiveGiftCardSheet_();
  } catch (e) {
    source = ss.getSheetByName(SHEET_NAMES.GIFT_CARD_LEGACY);
  }
  if (!source) {
    throw new Error(
      'No source tab found. Create a "' + SHEET_NAMES.GIFT_CARD_TEMPLATE + '" tab, or keep the legacy "' +
      SHEET_NAMES.GIFT_CARD_LEGACY + '" tab until you run Start new month once.'
    );
  }

  if (isLegacyGiftCardSheet_(source)) {
    return createGiftCardMonthTabFromLegacyBlock_(tabName, source);
  }
  return copyGiftCardMonthTab_(source, tabName);
}

function copyGiftCardMonthTab_(source, tabName) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const newSheet = source.copyTo(ss);
  newSheet.setName(tabName);

  const headerRow = getGiftCardHeaderRow_(newSheet);
  const lastRow = newSheet.getLastRow();
  if (lastRow > headerRow) {
    const lastCol = newSheet.getLastColumn();
    newSheet.getRange(headerRow + 1, 1, lastRow - headerRow, lastCol).clearContent();
  }

  newSheet.showSheet();
  setActiveGiftCardSheet_(tabName);
  return newSheet;
}

/** Flattens the right-most block from the legacy horizontal sheet into a new month tab. */
function createGiftCardMonthTabFromLegacyBlock_(tabName, legacySheet) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const block = getCurrentMonthBlock_(legacySheet);
  const newSheet = ss.insertSheet(tabName);
  const headerRow = HEADER_ROW.GIFT_CARD_TRACKER;
  const width = block.width;

  legacySheet.getRange(HEADER_ROW.GIFT_CARD_TRACKER_FIELD_ROW, block.startCol + 1, 1, width)
    .copyTo(newSheet.getRange(headerRow, 1, 1, width));

  const amountOffset = colIndex_(block.headerIndex, 'Gift Card Amount', false);
  if (amountOffset !== -1) {
    const firstDataRow = headerRow + 1;
    legacySheet.getRange(
      HEADER_ROW.GIFT_CARD_TRACKER_FIELD_ROW + 1,
      block.startCol + amountOffset + 1,
      GIFT_CARD_FORMULA_ROWS,
      1
    ).copyTo(newSheet.getRange(firstDataRow, amountOffset + 1, GIFT_CARD_FORMULA_ROWS, 1));
  }

  newSheet.showSheet();
  setActiveGiftCardSheet_(tabName);
  return newSheet;
}

// --- Legacy horizontal month blocks (fallback) ---

/**
 * The legacy Monthly Gift Card Cost Tracker lays months out side-by-side:
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
  if (starts.length === 0) throw new Error('No month labels found in row ' + HEADER_ROW.GIFT_CARD_TRACKER_MONTH_LABEL_ROW + ' of "' + SHEET_NAMES.GIFT_CARD_LEGACY + '".');

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
