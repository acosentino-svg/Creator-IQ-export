/**
 * Helpers.gs
 * Generic utilities shared by Automation.gs: header lookup, gift card month-tab
 * helpers (one tab per month, e.g. "July 2026 Gift Card Cost Tracker"), and
 * handle normalization. Legacy horizontal "Monthly Gift Card Cost Tracker" is
 * still supported as a fallback.
 */

function getSheet_(name) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(name);
  if (!sheet) throw new Error('Tab not found: "' + name + '". Check SHEET_NAMES in Config.gs.');
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
  if (!match) throw new Error('Could not find a spreadsheet ID in: ' + urlOrId);
  return match[0];
}

/**
 * The Names tab lives in this spreadsheet, or in EXTERNAL_NAMES_SHEET_ID if set.
 * Returns null (never throws) if the tab does not exist yet.
 */
function getNamesLookupSheet_() {
  try {
    let ss = SpreadsheetApp.getActiveSpreadsheet();
    const local = ss.getSheetByName(NAMES_LOOKUP_SHEET_NAME);
    if (local) return local;
    if (EXTERNAL_NAMES_SHEET_ID) {
      const namesFileId = extractSpreadsheetId_(EXTERNAL_NAMES_SHEET_ID);
      ss = SpreadsheetApp.openById(namesFileId);
      return ss.getSheetByName(NAMES_LOOKUP_SHEET_NAME) || null;
    }
    return null;
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

function formatPiecesSlashLabel_(pieces) {
  const n = Number(pieces) || 0;
  return n + ' piece/s';
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

/** ashali123_ -> Ashali when Names tab has no match. */
function firstNameFromHandle_(handle) {
  const raw = String(handle || '').replace(/^@/, '').trim();
  if (!raw) return '';
  const segment = raw.split(/[._]/)[0] || raw;
  const letters = segment.replace(/[0-9]+/g, '');
  return capitalizeFirst_(letters || segment);
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
    const msgSheet = getSheet_(SHEET_NAMES.BOOSTING_TRACKER);
    const read = readFlatSheetRows_(msgSheet, HEADER_ROW.BOOSTING_TRACKER);
    const sentKey = normalizeHeader_('creator notified');
    if (read.rows.some((r) =>
      normalizeHandle_(r['creator name']) === handleKey &&
      normalizeHeader_(r[sentKey]) === normalizeHeader_('yes')
    )) {
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
  const contentPieces = Number(opts.contentPieces) || pieces;
  const needsLinks = opts.needsLinks !== false;
  const productLinksText = String(opts.productLinks || '').trim();
  const linksForEmail = splitLinks_(productLinksText).join('\n');
  const isFollowUp = opts.isFollowUp != null
    ? !!opts.isFollowUp
    : isAlreadyBoostedThisMonth_(opts.handle);

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
    PIECES_SLASH_LABEL: formatPiecesSlashLabel_(pieces),
    NEW_PIECES_LABEL: formatMorePiecesLabel_(newPieces),
    AMOUNT: amount,
    INCREMENT_AMOUNT: formatAmount_(GIFT_CARD_INCREMENT_AMOUNT * newPieces),
    SELECTED_VIDEOS_PHRASE: formatSelectedVideosPhrase_(contentPieces),
    LINKS: linksForEmail,
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

function mergeLinkLabels_(existing, incoming) {
  const set = {};
  splitLinks_(existing).concat(splitLinks_(incoming)).forEach((link) => {
    const label = String(link || '').trim();
    if (label) set[label] = true;
  });
  return Object.keys(set).join(', ');
}

/** Reads Boosting Tracker once and returns handle -> merged link/video URLs. */
function buildLinksLookupFromTracker_() {
  const trackerSheet = getSheet_(SHEET_NAMES.BOOSTING_TRACKER);
  const lastRow = trackerSheet.getLastRow();
  const lastCol = trackerSheet.getLastColumn();
  const lookup = {};
  if (lastRow < HEADER_ROW.BOOSTING_TRACKER + 1) return lookup;

  const headers = trackerSheet.getRange(HEADER_ROW.BOOSTING_TRACKER, 1, 1, lastCol).getValues()[0];
  const headerIndex = buildHeaderIndex_(headers);
  const nameIdx = colIndex_(headerIndex, 'creator name', false);
  const contentIdx = colIndex_(headerIndex, 'content used', false);
  const linksIdx = colIndex_(headerIndex, 'storefront links provided', false);
  const favLinksIdx = colIndex_(headerIndex, "fav's list + affiliate links provided", false);
  if (nameIdx === -1) return lookup;

  const values = trackerSheet.getRange(HEADER_ROW.BOOSTING_TRACKER + 1, 1, lastRow - HEADER_ROW.BOOSTING_TRACKER, lastCol).getValues();
  values.forEach((row) => {
    const handleKey = normalizeHandle_(row[nameIdx]);
    if (!handleKey) return;
    const parts = [];
    if (linksIdx !== -1 && row[linksIdx]) parts.push(String(row[linksIdx]).trim());
    if (favLinksIdx !== -1 && row[favLinksIdx]) parts.push(String(row[favLinksIdx]).trim());
    if (contentIdx !== -1 && row[contentIdx]) parts.push(String(row[contentIdx]).trim());
    if (!parts.length) return;
    lookup[handleKey] = mergeLinkLabels_(lookup[handleKey] || '', parts.join(', '));
  });
  return lookup;
}

/** Uses queue Links column first, then falls back to Boosting Tracker URLs for that handle. */
function resolveOutreachLinks_(row, handle, linksLookup) {
  const fromRow = ['links', 'link', 'video link', 'video links', 'content link', 'content links', 'content used']
    .map((k) => String(row[k] || '').trim())
    .find((v) => v);
  if (fromRow) return fromRow;
  const handleKey = normalizeHandle_(handle);
  if (!handleKey) return '';
  if (linksLookup) return linksLookup[handleKey] || '';
  return buildLinksLookupFromTracker_()[handleKey] || '';
}

/** Reads Boosting Tracker once and returns handle -> merged platform labels. */
function buildPlatformLookupFromTracker_() {
  const trackerSheet = getSheet_(SHEET_NAMES.BOOSTING_TRACKER);
  const lastRow = trackerSheet.getLastRow();
  const lastCol = trackerSheet.getLastColumn();
  const lookup = {};
  if (lastRow < HEADER_ROW.BOOSTING_TRACKER + 1) return lookup;

  const headers = trackerSheet.getRange(HEADER_ROW.BOOSTING_TRACKER, 1, 1, lastCol).getValues()[0];
  const headerIndex = buildHeaderIndex_(headers);
  const nameIdx = colIndex_(headerIndex, 'creator name', false);
  const platformIdx = colIndex_(headerIndex, 'platform(s) for usage', false);
  if (nameIdx === -1) return lookup;
  const platformCol0 = getTrackerPlatformCol0_(headerIndex);
  if (platformCol0 === -1) return lookup;

  const values = trackerSheet.getRange(HEADER_ROW.BOOSTING_TRACKER + 1, 1, lastRow - HEADER_ROW.BOOSTING_TRACKER, lastCol).getValues();
  values.forEach((row) => {
    const handleKey = normalizeHandle_(row[nameIdx]);
    const platform = String(row[platformCol0] || '').trim();
    if (!handleKey || !platform) return;
    lookup[handleKey] = mergePlatformLabels_(lookup[handleKey] || '', platform);
  });
  return lookup;
}

/** Fallback for message rows synced before Platform (auto) existed. */
function lookupPlatformsForHandleFromTracker_(handle, platformLookup) {
  const handleKey = normalizeHandle_(handle);
  if (!handleKey) return '';
  if (platformLookup) return platformLookup[handleKey] || '';
  return (buildPlatformLookupFromTracker_()[handleKey]) || '';
}

/** Batch-writes one column from [{ row: 1-based sheet row, value }]. */
function batchSetColumnValues_(sheet, col1Based, updates) {
  if (!updates.length) return;
  const rowNums = updates.map((u) => u.row);
  const minRow = Math.min.apply(null, rowNums);
  const maxRow = Math.max.apply(null, rowNums);
  const range = sheet.getRange(minRow, col1Based, maxRow - minRow + 1, 1);
  const values = range.getValues();
  const valueByRow = {};
  updates.forEach((u) => { valueByRow[u.row] = u.value; });
  for (let r = minRow; r <= maxRow; r++) {
    if (valueByRow[r] !== undefined) values[r - minRow][0] = valueByRow[r];
  }
  range.setValues(values);
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

const GIFT_CARD_MONTH_DISPLAY_NAMES_ = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

const GIFT_CARD_MONTH_ABBR_ = {
  jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5,
  jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11,
};

/** Normalizes "aug", "August", "AUGUST" -> "August". Returns null if not a month. */
function normalizeMonthName_(input) {
  const raw = String(input || '').trim().toLowerCase();
  if (!raw) return null;
  let index = GIFT_CARD_MONTH_NAMES_.indexOf(raw);
  if (index === -1 && raw.length >= 3) {
    index = GIFT_CARD_MONTH_ABBR_[raw.slice(0, 3)];
  }
  if (index == null || index < 0) return null;
  return GIFT_CARD_MONTH_DISPLAY_NAMES_[index];
}

function monthYearSortKey_(year, monthIndex) {
  return Number(year) * 12 + Number(monthIndex);
}

function isReasonableGiftCardYear_(year) {
  const y = Number(year);
  return y >= GIFT_CARD_YEAR_MIN && y <= GIFT_CARD_YEAR_MAX;
}

function sheetsSerialToDate_(serial) {
  const n = Number(serial);
  if (isNaN(n) || n <= 0) return null;
  // Google Sheets epoch: Dec 30, 1899
  const ms = Math.round((n - 25569) * 86400 * 1000);
  const d = new Date(ms);
  return isNaN(d.getTime()) ? null : d;
}

/** Parses a tracker cell, Date object, or "August 2026" string into month metadata. */
function parseMonthYearFromCell_(value) {
  if (typeof value === 'number') {
    const fromSerial = sheetsSerialToDate_(value);
    if (fromSerial) return parseMonthYearFromCell_(fromSerial);
    return null;
  }

  if (value instanceof Date && !isNaN(value.getTime())) {
    const year = value.getFullYear();
    if (!isReasonableGiftCardYear_(year)) return null;
    const monthIndex = value.getMonth();
    return {
      monthName: GIFT_CARD_MONTH_DISPLAY_NAMES_[monthIndex],
      year: year,
      monthIndex: monthIndex,
      sortKey: monthYearSortKey_(year, monthIndex),
      date: value,
    };
  }

  const str = String(value || '').trim();
  if (!str) return null;

  const named = str.match(/^([A-Za-z]+)\s+(\d{4})$/);
  if (named) {
    const monthName = normalizeMonthName_(named[1]);
    const year = parseInt(named[2], 10);
    if (!monthName || !isReasonableGiftCardYear_(year)) return null;
    const monthIndex = GIFT_CARD_MONTH_DISPLAY_NAMES_.indexOf(monthName);
    return {
      monthName: monthName,
      year: year,
      monthIndex: monthIndex,
      sortKey: monthYearSortKey_(year, monthIndex),
      date: new Date(year, monthIndex, 1),
    };
  }

  const slash = str.match(/^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})$/);
  if (slash) {
    let year = parseInt(slash[3], 10);
    if (slash[3].length === 2) year = 2000 + year;
    if (!isReasonableGiftCardYear_(year)) return null;
    const monthIndex = parseInt(slash[1], 10) - 1;
    if (monthIndex >= 0 && monthIndex < 12) {
      return {
        monthName: GIFT_CARD_MONTH_DISPLAY_NAMES_[monthIndex],
        year: year,
        monthIndex: monthIndex,
        sortKey: monthYearSortKey_(year, monthIndex),
        date: new Date(year, monthIndex, parseInt(slash[2], 10)),
      };
    }
  }

  const monthDay = str.match(/^(\d{1,2})[\/\-](\d{1,2})$/);
  if (monthDay) {
    const monthIndex = parseInt(monthDay[1], 10) - 1;
    const day = parseInt(monthDay[2], 10);
    if (monthIndex >= 0 && monthIndex < 12 && day >= 1 && day <= 31) {
      const now = new Date();
      let year = now.getFullYear();
      let candidate = new Date(year, monthIndex, day);
      if (candidate.getTime() - now.getTime() > 7 * 86400000) year -= 1;
      candidate = new Date(year, monthIndex, day);
      if (!isReasonableGiftCardYear_(year)) return null;
      return {
        monthName: GIFT_CARD_MONTH_DISPLAY_NAMES_[monthIndex],
        year: year,
        monthIndex: monthIndex,
        sortKey: monthYearSortKey_(year, monthIndex),
        date: candidate,
      };
    }
  }

  const parsed = new Date(str);
  if (!isNaN(parsed.getTime())) return parseMonthYearFromCell_(parsed);

  return null;
}

/** Parses prompt input like "August 2026", "Aug 2026", or "8/2026". */
function parseMonthYearInput_(text) {
  const input = String(text || '').trim();
  if (!input) return null;

  const named = input.match(/^([A-Za-z]+)\s+(\d{4})$/);
  if (named) {
    const monthName = normalizeMonthName_(named[1]);
    if (!monthName) return null;
    return { monthName: monthName, year: parseInt(named[2], 10) };
  }

  const monthSlashYear = input.match(/^(\d{1,2})[\/\-](\d{4})$/);
  if (monthSlashYear) {
    const monthIndex = parseInt(monthSlashYear[1], 10) - 1;
    if (monthIndex < 0 || monthIndex > 11) return null;
    return {
      monthName: GIFT_CARD_MONTH_DISPLAY_NAMES_[monthIndex],
      year: parseInt(monthSlashYear[2], 10),
    };
  }

  const fromDate = parseMonthYearFromCell_(input);
  if (fromDate) return { monthName: fromDate.monthName, year: fromDate.year };
  return null;
}

function getBoostingTrackerDateCol0_(headerIndex) {
  for (let i = 0; i < BOOSTING_TRACKER_DATE_HEADERS.length; i++) {
    const key = BOOSTING_TRACKER_DATE_HEADERS[i];
    if (headerIndex[key] != null) return headerIndex[key];
  }
  return BOOSTING_TRACKER_DATE_COL - 1;
}

function getTrackerPlatformCol0_(headerIndex) {
  for (let i = 0; i < BOOSTING_TRACKER_PLATFORM_HEADERS.length; i++) {
    const key = BOOSTING_TRACKER_PLATFORM_HEADERS[i];
    if (headerIndex[key] != null) return headerIndex[key];
  }
  return -1;
}

/** Storefront / affiliate product links only (columns F/G) — not video URLs. */
function resolveTrackerProductLinks_(row, headerIndex) {
  const linksIdx = headerIndex['storefront links provided'];
  const favLinksIdx = headerIndex["fav's list + affiliate links provided"];
  const fromF = linksIdx != null ? String(row[linksIdx] || '').trim() : '';
  const fromG = favLinksIdx != null ? String(row[favLinksIdx] || '').trim() : '';
  return mergeLinkLabels_(fromF, fromG);
}

function getTrackerStorefrontLinkCol0_(headerIndex) {
  const key = normalizeHeader_('storefront links provided');
  return key in headerIndex ? headerIndex[key] : -1;
}

function getTrackerFavLinksCol0_(headerIndex) {
  const key = normalizeHeader_("fav's list + affiliate links provided");
  return key in headerIndex ? headerIndex[key] : -1;
}

function looksLikeProductLink_(value) {
  const s = String(value || '').trim().toLowerCase();
  if (!s || s.length < 8) return false;
  return s.indexOf('http') === 0 || s.indexOf('www.') === 0 || s.indexOf('creatorlink.') !== -1;
}

function getTrackerRowDateParsed_(row, headerIndex) {
  const dateCol0 = getBoostingTrackerDateCol0_(headerIndex);
  return parseMonthYearFromCell_(row[dateCol0]);
}

/** Row column D is in the active batch month (e.g. any August date while running in August). */
function isTrackerRowInDraftMonth_(row, headerIndex, batchMonth) {
  if (!batchMonth) return true;
  const parsed = getTrackerRowDateParsed_(row, headerIndex);
  if (!parsed) return false;
  return parsed.monthIndex === batchMonth.monthIndex;
}

/** Always the current calendar month — August rows while it's August. Not the old stored tab name. */
function getActiveBatchMonth_() {
  return currentCalendarMonth_();
}

function inferGiftCardMonthFromTracker_() {
  return getActiveBatchMonth_();
}

/** Clears legacy Queued (auto) cells left by older script versions. */
function clearLegacyQueuedMarkersOnTracker_(trackerSheet, headerIndex) {
  const lastRow = trackerSheet.getLastRow();
  const firstDataRow = HEADER_ROW.BOOSTING_TRACKER + 1;
  const numRows = lastRow - firstDataRow + 1;
  if (numRows <= 0) return 0;

  const lastCol = trackerSheet.getLastColumn();
  const values = trackerSheet.getRange(firstDataRow, 1, numRows, lastCol).getValues();
  const notifiedCol = headerIndex['creator notified'] + 1;
  const updates = [];

  values.forEach((row, i) => {
    if (normalizeHeader_(row[headerIndex['creator notified']]) === LEGACY_QUEUED_MARKER) {
      updates.push({ row: firstDataRow + i, value: '' });
    }
  });
  batchSetColumnValues_(trackerSheet, notifiedCol, updates);
  return updates.length;
}

/** Dupe if Creator Notified or Unique Identifier says dupe (column K formula). */
function isTrackerDupeRow_(row, headerIndex) {
  const notifiedNorm = normalizeHeader_(row[headerIndex['creator notified']]);
  if (DUPE_MARKERS.some((m) => notifiedNorm.indexOf(m) !== -1)) return true;
  const uidIdx = colIndex_(headerIndex, 'unique identifier', false);
  if (uidIdx !== -1) {
    const uidNorm = normalizeHeader_(row[uidIdx]);
    if (DUPE_MARKERS.some((m) => uidNorm.indexOf(m) !== -1)) return true;
  }
  return false;
}

/** True for tracker rows still in this month's workflow (not done, not dupe). */
function isTrackerRowEligibleForMonthInference_(row, headerIndex) {
  const creatorName = row[headerIndex['creator name']];
  const contentUsed = row[headerIndex['content used']];
  const notified = row[headerIndex['creator notified']];
  if (!creatorName || normalizeHandle_(creatorName) === 'example entry') return false;
  if (!contentUsed || String(contentUsed).trim() === '') return false;
  const notifiedNorm = normalizeHeader_(notified);
  if (ALREADY_HANDLED_VALUES.indexOf(notifiedNorm) !== -1) return false;
  if (isTrackerDupeRow_(row, headerIndex)) return false;
  return true;
}

function currentCalendarMonth_() {
  const now = new Date();
  const monthIndex = now.getMonth();
  const year = now.getFullYear();
  return {
    monthName: GIFT_CARD_MONTH_DISPLAY_NAMES_[monthIndex],
    year: year,
    monthIndex: monthIndex,
    sortKey: monthYearSortKey_(year, monthIndex),
    date: now,
  };
}

/** Creates/selects the gift card tab for the active batch month. */
function ensureGiftCardMonthTabForTracker_() {
  const inferred = inferGiftCardMonthFromTracker_();
  if (!inferred) {
    return { tabName: getActiveGiftCardSheetName_(), created: false, inferred: null };
  }

  const tabName = formatGiftCardMonthTabName_(inferred.monthName, inferred.year);
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let created = false;
  if (!ss.getSheetByName(tabName)) {
    createGiftCardMonthTab_(tabName);
    created = true;
  }
  setActiveGiftCardSheet_(tabName);
  return { tabName: tabName, created: created, inferred: inferred };
}

/** Latest tracker date in column D for a creator handle (for gift card column D). */
function lookupLatestTrackerDateForHandle_(handle) {
  const handleKey = normalizeHandle_(handle);
  if (!handleKey) return null;

  const trackerSheet = getSheet_(SHEET_NAMES.BOOSTING_TRACKER);
  const lastRow = trackerSheet.getLastRow();
  if (lastRow <= HEADER_ROW.BOOSTING_TRACKER) return null;

  const lastCol = trackerSheet.getLastColumn();
  const headers = trackerSheet.getRange(HEADER_ROW.BOOSTING_TRACKER, 1, 1, lastCol).getValues()[0];
  const headerIndex = buildHeaderIndex_(headers);
  const nameIdx = colIndex_(headerIndex, 'creator name', false);
  const dateCol0 = getBoostingTrackerDateCol0_(headerIndex);
  if (nameIdx === -1) return null;

  const numRows = lastRow - firstDataRow + 1;
  const values = trackerSheet.getRange(firstDataRow, 1, numRows, lastCol).getValues();
  let latest = null;
  values.forEach((row) => {
    if (normalizeHandle_(row[nameIdx]) !== handleKey) return;
    const parsed = parseMonthYearFromCell_(row[dateCol0]);
    if (!parsed) return;
    if (!latest || parsed.sortKey > latest.sortKey) latest = parsed;
  });
  return latest ? latest.date : null;
}

function getGiftCardDateCol1_(ctx) {
  for (let i = 0; i < GIFT_CARD_DATE_HEADERS.length; i++) {
    const col = giftCardCol1_(ctx, GIFT_CARD_DATE_HEADERS[i], false);
    if (col !== -1) return col;
  }
  return -1;
}

/** True when a gift card First Name cell holds a tracker date (8/17, 8/3/2026, etc.). */
function cellLooksLikeTrackerDate_(value) {
  return !!parseMonthYearFromCell_(value);
}

function resolveGiftCardFirstName_(handle, profile) {
  if (profile && String(profile.firstName || '').trim()) return profile.firstName;
  return firstNameFromHandle_(handle);
}

function applyTrackerDateToGiftCardRow_(ctx, row, handle) {
  const trackerDate = lookupLatestTrackerDateForHandle_(handle);
  if (!trackerDate) return;
  const dateCol = getGiftCardDateCol1_(ctx);
  if (dateCol === -1) return;
  ctx.sheet.getRange(row, dateCol).setValue(trackerDate);
}

/** Clears tracker dates wrongly written to First Name; fills names from Names tab or handle. */
function repairGiftCardMisplacedDates_() {
  const ctx = getGiftCardContext_();
  const rows = readGiftCardRows_(ctx);
  const lookup = buildNameLookup_();
  const firstNameCol = giftCardCol1_(ctx, 'First Name', false);
  const lastNameCol = giftCardCol1_(ctx, 'Last Name', false);
  if (firstNameCol === -1) {
    throw new Error('Gift card tab must have a First Name column.');
  }

  let repaired = 0;
  rows.forEach((row) => {
    const handle = String(row[ctx.nameKey] || '').trim();
    const handleKey = normalizeHandle_(handle);
    if (!handleKey) return;

    const currentFirst = row['first name'];
    const needsRepair = cellLooksLikeTrackerDate_(currentFirst) || String(currentFirst || '').trim() === '';
    if (!needsRepair) return;

    const profile = lookup[handleKey];
    const firstName = resolveGiftCardFirstName_(handle, profile);
    if (!firstName) return;

    ctx.sheet.getRange(row._sheetRow, firstNameCol).setValue(firstName);
    if (lastNameCol !== -1 && profile && profile.lastName) {
      ctx.sheet.getRange(row._sheetRow, lastNameCol).setValue(profile.lastName);
    }
    repaired++;
  });

  toast_('Repaired ' + repaired + ' First Name cell(s) on ' + ctx.sheet.getName() + '.');
  return repaired;
}

/** Builds the tab name: "August Gift Card Cost Tracker". */
function formatGiftCardMonthTabName_(monthName, year) {
  const month = normalizeMonthName_(monthName);
  if (!month) throw new Error('Month is required (e.g. August).');
  return month + ' ' + GIFT_CARD_MONTH_TAB_SUFFIX;
}

/** Parses "August Gift Card Cost Tracker" or legacy "August 2026 Gift Card Cost Tracker". */
function parseGiftCardMonthTabName_(tabName) {
  const suffix = ' ' + GIFT_CARD_MONTH_TAB_SUFFIX;
  const name = String(tabName || '').trim();
  if (!name.endsWith(suffix)) return null;
  const prefix = name.slice(0, -suffix.length).trim();

  const withYear = prefix.match(/^(\w+)\s+(\d{4})$/);
  if (withYear) {
    const monthName = normalizeMonthName_(withYear[1]);
    const year = parseInt(withYear[2], 10);
    if (!monthName || !isReasonableGiftCardYear_(year)) return null;
    const monthIndex = GIFT_CARD_MONTH_DISPLAY_NAMES_.indexOf(monthName);
    return {
      month: monthName,
      year: year,
      monthIndex: monthIndex,
      sortKey: monthYearSortKey_(year, monthIndex),
      tabName: name,
    };
  }

  const monthName = normalizeMonthName_(prefix);
  if (!monthName) return null;
  const monthIndex = GIFT_CARD_MONTH_DISPLAY_NAMES_.indexOf(monthName);
  return {
    month: monthName,
    year: null,
    monthIndex: monthIndex,
    sortKey: monthIndex,
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
  const batch = currentCalendarMonth_();
  const currentTab = formatGiftCardMonthTabName_(batch.monthName, batch.year);
  if (SpreadsheetApp.getActiveSpreadsheet().getSheetByName(currentTab)) {
    return currentTab;
  }

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
