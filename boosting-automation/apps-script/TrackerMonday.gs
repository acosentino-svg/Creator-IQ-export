/**
 * TrackerMonday.gs
 * Monday workflow reads Boosting Tracker directly (no Outreach Queue):
 *   scan -> dedupe -> gift card month tab -> Google Doc emails
 * Email entered on the tracker promotes the creator into the month gift card tab.
 */

/** Scans Boosting Tracker and returns grouped email work for the Google Doc. */
function scanBoostingTrackerForMonday_() {
  const trackerSheet = getSheet_(SHEET_NAMES.BOOSTING_TRACKER);
  const lastRow = trackerSheet.getLastRow();
  const lastCol = trackerSheet.getLastColumn();
  const headers = trackerSheet.getRange(HEADER_ROW.BOOSTING_TRACKER, 1, 1, lastCol).getValues()[0];
  const headerIndex = buildHeaderIndex_(headers);
  ['creator name', 'content used', 'creator notified'].forEach((h) => colIndex_(headerIndex, h, true));

  const clearedLegacy = clearLegacyQueuedMarkersOnTracker_(trackerSheet, headerIndex);
  const draftMonth = inferGiftCardMonthFromTracker_();

  const firstDataRow = HEADER_ROW.BOOSTING_TRACKER + 1;
  const numRows = lastRow - HEADER_ROW.BOOSTING_TRACKER;
  if (numRows <= 0) {
    return emptyMondayScanResult_();
  }

  const values = trackerSheet.getRange(firstDataRow, 1, numRows, lastCol).getValues();
  const nameLookup = buildNameLookup_();
  const platformCol0 = getTrackerPlatformCol0_(headerIndex);
  const uidIdx = colIndex_(headerIndex, 'unique identifier', false);

  let ctx = null;
  let handleOnGiftCard = {};
  try {
    ctx = getGiftCardContext_();
    readGiftCardRows_(ctx).forEach((r) => {
      const hk = normalizeHandle_(r[ctx.nameKey]);
      if (hk) handleOnGiftCard[hk] = true;
    });
  } catch (e) { /* gift card tab may not exist yet */ }

  const creators = {};
  const globalContentUrls = {};
  const globalUids = {};
  let skippedDupes = 0;
  let skippedRepeatLinks = 0;
  let skippedStale = 0;
  let pending = 0;

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

    if (isTrackerDupeRow_(row, headerIndex)) {
      skippedDupes++;
      fillDupeLinks_(trackerSheet, headerIndex, values, i, sheetRow);
      continue;
    }

    if (!isTrackerRowRecentEnoughForDraft_(row, headerIndex)
        || !isTrackerRowInDraftMonth_(row, headerIndex, draftMonth)) {
      skippedStale++;
      continue;
    }

    const contentUrl = normalizeContentUrl_(contentUsed);
    if (contentUrl) {
      if (globalContentUrls[contentUrl]) {
        skippedRepeatLinks++;
        continue;
      }
      globalContentUrls[contentUrl] = true;
    }

    if (uidIdx !== -1) {
      const uid = String(row[uidIdx] || '').trim();
      if (uid && uid !== '#N/A') {
        if (globalUids[uid]) {
          skippedRepeatLinks++;
          continue;
        }
        globalUids[uid] = true;
      }
    }

    const handle = String(creatorName).trim();
    const handleKey = normalizeHandle_(handle);
    const platform = platformCol0 !== -1 ? String(row[platformCol0] || '').trim() : '';
    const contentLink = String(contentUsed || '').trim();
    const productLinksText = resolveTrackerProductLinks_(row, headerIndex);

    let creator = creators[handleKey];
    if (!creator) {
      const profile = nameLookup[handleKey];
      creator = creators[handleKey] = {
        handle: handle,
        firstName: profile ? profile.firstName : '',
        lastName: profile ? profile.lastName : '',
        contentUrlSet: {},
        contentUrls: [],
        productLinkSet: {},
        productLinks: [],
        platforms: [],
        isFollowUp: !!handleOnGiftCard[handleKey],
      };
    }

    if (contentLink) {
      const contentKey = normalizeContentUrl_(contentLink);
      if (contentKey && !creator.contentUrlSet[contentKey]) {
        creator.contentUrlSet[contentKey] = true;
        creator.contentUrls.push(contentLink);
      }
    }
    splitLinks_(productLinksText).forEach((link) => {
      const key = normalizeContentUrl_(link);
      if (!key || creator.productLinkSet[key]) return;
      creator.productLinkSet[key] = true;
      creator.productLinks.push(link);
    });
    if (platform) creator.platforms.push(platform);
    pending++;
  }

  const entries = [];
  const skipped = [];

  Object.keys(creators).forEach((handleKey) => {
    const c = creators[handleKey];
    const pieces = c.contentUrls.length || 1;
    const platform = mergePlatformLabels_('', c.platforms.join(', '));
    const contentUrls = c.contentUrls.join(', ');
    const productLinks = c.productLinks.join(', ');
    const displayName = String(c.firstName || '').trim()
      || (c.handle ? capitalizeFirst_(c.handle.replace(/^@/, '').split(/[._]/)[0]) : '');
    const needsLinks = needsProductLinksForPlatforms_(platform);
    const hasProductLinks = c.productLinks.length > 0;
    const amount = formatAmount_(calculateGiftCardAmount_(pieces));
    const rowType = c.isFollowUp ? OUTREACH_TYPE_FOLLOWUP : OUTREACH_TYPE_NEW;

    if (!displayName) {
      skipped.push({
        handle: c.handle || '(blank handle)',
        type: rowType,
        pieces: pieces,
        amount: amount,
        reasons: 'missing name',
      });
      return;
    }

    entries.push({
      handle: c.handle,
      firstName: displayName,
      type: rowType,
      isFollowUp: c.isFollowUp,
      pieces: pieces,
      amount: amount,
      contentUrls: contentUrls,
      productLinks: productLinks,
      platform: platform,
      message: buildDraftMessage_({
        isFollowUp: c.isFollowUp,
        handle: c.handle,
        firstName: displayName,
        pieces: pieces,
        contentPieces: pieces,
        newPieces: pieces,
        amount: amount,
        needsLinks: needsLinks,
        hasProductLinks: hasProductLinks,
      }),
    });
  });

  return {
    entries: entries,
    skipped: skipped,
    drafted: entries.length,
    skippedCount: skipped.length,
    skippedNoName: skipped.filter((s) => s.reasons.indexOf('missing name') !== -1).length,
    skippedNoLinks: 0,
    pending: pending,
    skippedDupes: skippedDupes,
    skippedRepeatLinks: skippedRepeatLinks,
    skippedStale: skippedStale,
    clearedLegacyQueued: clearedLegacy,
    draftMonthLabel: draftMonth ? draftMonth.monthName + ' ' + draftMonth.year : '',
    emailRows: entries.length,
  };
}

function emptyMondayScanResult_() {
  return {
    entries: [],
    skipped: [],
    drafted: 0,
    skippedCount: 0,
    skippedNoName: 0,
    skippedNoLinks: 0,
    pending: 0,
    skippedDupes: 0,
    skippedRepeatLinks: 0,
    skippedStale: 0,
    clearedLegacyQueued: 0,
    draftMonthLabel: '',
    emailRows: 0,
  };
}

function normalizeContentUrl_(value) {
  return String(value || '').trim().toLowerCase().replace(/\/+$/, '').split('?')[0].split('#')[0];
}

function getBoostingTrackerEmailCol0_(headerIndex) {
  for (let i = 0; i < BOOSTING_TRACKER_EMAIL_HEADERS.length; i++) {
    const key = BOOSTING_TRACKER_EMAIL_HEADERS[i];
    if (headerIndex[key] != null) return headerIndex[key];
  }
  return -1;
}

/** Adds/updates a creator on the active gift card tab when email is entered on the tracker. */
function promoteCreatorFromTrackerRow_(sheetRow) {
  const trackerSheet = getSheet_(SHEET_NAMES.BOOSTING_TRACKER);
  const lastCol = trackerSheet.getLastColumn();
  const headers = trackerSheet.getRange(HEADER_ROW.BOOSTING_TRACKER, 1, 1, lastCol).getValues()[0];
  const headerIndex = buildHeaderIndex_(headers);
  const row = trackerSheet.getRange(sheetRow, 1, 1, lastCol).getValues()[0];

  const handle = String(row[headerIndex['creator name']] || '').trim();
  const handleKey = normalizeHandle_(handle);
  if (!handleKey) return { promoted: 0 };

  const emailCol0 = getBoostingTrackerEmailCol0_(headerIndex);
  const email = emailCol0 !== -1 ? String(row[emailCol0] || '').trim() : '';
  if (!email || email.indexOf('@') === -1) return { promoted: 0 };

  ensureGiftCardMonthTabForTracker_();
  const ctx = getGiftCardContext_();
  const nameKey = ctx.nameKey;
  const blockRows = readGiftCardRows_(ctx);
  const existing = blockRows.find((r) => normalizeHandle_(r[nameKey]) === handleKey);

  const stats = summarizePendingTrackerRowsForHandle_(handleKey, headerIndex, trackerSheet);
  if (!stats.pieces) return { promoted: 0 };

  const giftSheet = ctx.sheet;
  const nameHeaderLabel = (nameKey === 'creator handle') ? 'Creator Handle' : 'Creator Name';
  const firstNameCol = giftCardCol1_(ctx, 'First Name', false);
  const lastNameCol = giftCardCol1_(ctx, 'Last Name', false);
  const emailCol = giftCardCol1_(ctx, 'Email Address', false);
  const newPiecesCol = giftCardCol1_(ctx, 'New Pieces of Content Used', true);
  const amountCol = giftCardCol1_(ctx, 'Gift Card Amount', false);
  const linksCol = giftCardCol1_(ctx, 'Links', false);
  const profileUrlCol = giftCardCol1_(ctx, 'URL', false);
  const nameLookup = buildNameLookup_();
  const profile = nameLookup[handleKey];

  let targetRow;
  if (existing) {
    targetRow = existing._sheetRow;
    giftSheet.getRange(targetRow, newPiecesCol).setValue(stats.pieces);
    if (amountCol !== -1) {
      giftSheet.getRange(targetRow, amountCol).setValue(formatAmount_(calculateGiftCardAmount_(stats.pieces)));
    }
    if (linksCol !== -1 && stats.links) {
      giftSheet.getRange(targetRow, linksCol).setValue(stats.links);
    }
    if (emailCol !== -1) giftSheet.getRange(targetRow, emailCol).setValue(email);
  } else {
    targetRow = findNextEmptyGiftCardRow_(ctx, blockRows);
    setGiftCardCell_(ctx, targetRow, nameHeaderLabel, handle);
    if (firstNameCol !== -1 && profile) giftSheet.getRange(targetRow, firstNameCol).setValue(profile.firstName);
    if (lastNameCol !== -1 && profile) giftSheet.getRange(targetRow, lastNameCol).setValue(profile.lastName);
    giftSheet.getRange(targetRow, newPiecesCol).setValue(stats.pieces);
    if (amountCol !== -1) {
      giftSheet.getRange(targetRow, amountCol).setValue(formatAmount_(calculateGiftCardAmount_(stats.pieces)));
    }
    if (linksCol !== -1) giftSheet.getRange(targetRow, linksCol).setValue(stats.links);
    if (emailCol !== -1) giftSheet.getRange(targetRow, emailCol).setValue(email);
    if (profileUrlCol !== -1 && stats.profileUrl) {
      giftSheet.getRange(targetRow, profileUrlCol).setValue(stats.profileUrl);
    }
  }

  applyTrackerDateToGiftCardRow_(ctx, targetRow, handle);
  markTrackerRowsYesForHandle_(handleKey, headerIndex, trackerSheet);
  toast_('Added ' + handle + ' to ' + getActiveGiftCardSheetName_() + ' (' + stats.pieces + ' piece(s), ' + formatAmount_(calculateGiftCardAmount_(stats.pieces)) + ').');
  return { promoted: 1 };
}

function summarizePendingTrackerRowsForHandle_(handleKey, headerIndex, trackerSheet) {
  const lastRow = trackerSheet.getLastRow();
  const lastCol = trackerSheet.getLastColumn();
  const firstDataRow = HEADER_ROW.BOOSTING_TRACKER + 1;
  const numRows = lastRow - HEADER_ROW.BOOSTING_TRACKER;
  if (numRows <= 0) return { pieces: 0, links: '', profileUrl: '' };

  const values = trackerSheet.getRange(firstDataRow, 1, numRows, lastCol).getValues();
  const linksIdx = headerIndex['storefront links provided'];
  const contentUrlSet = {};
  const contentUrls = [];
  const productLinkSet = {};
  const productLinks = [];
  let profileUrl = '';

  values.forEach((row) => {
    if (normalizeHandle_(row[headerIndex['creator name']]) !== handleKey) return;
    const notifiedNorm = normalizeHeader_(row[headerIndex['creator notified']]);
    if (ALREADY_HANDLED_VALUES.indexOf(notifiedNorm) !== -1) return;
    if (isTrackerDupeRow_(row, headerIndex)) return;

    const contentUsed = row[headerIndex['content used']];
    const contentLink = String(contentUsed || '').trim();
    if (contentLink) {
      const contentKey = normalizeContentUrl_(contentLink);
      if (contentKey && !contentUrlSet[contentKey]) {
        contentUrlSet[contentKey] = true;
        contentUrls.push(contentLink);
      }
    }
    splitLinks_(resolveTrackerProductLinks_(row, headerIndex)).forEach((link) => {
      const key = normalizeContentUrl_(link);
      if (!key || productLinkSet[key]) return;
      productLinkSet[key] = true;
      productLinks.push(link);
    });
    if (!profileUrl && contentUsed) profileUrl = String(contentUsed).trim();
    if (linksIdx != null && row[linksIdx]) profileUrl = String(row[linksIdx]).trim();
  });

  return {
    pieces: contentUrls.length || 0,
    links: productLinks.join(', '),
    profileUrl: profileUrl,
  };
}

function markTrackerRowsYesForHandle_(handleKey, headerIndex, trackerSheet) {
  const lastRow = trackerSheet.getLastRow();
  const lastCol = trackerSheet.getLastColumn();
  const firstDataRow = HEADER_ROW.BOOSTING_TRACKER + 1;
  const values = trackerSheet.getRange(firstDataRow, 1, lastRow - firstDataRow + 1, lastCol).getValues();
  const notifiedCol = headerIndex['creator notified'] + 1;
  const updates = [];

  values.forEach((row, i) => {
    if (normalizeHandle_(row[headerIndex['creator name']]) !== handleKey) return;
    if (isTrackerDupeRow_(row, headerIndex)) return;
    const notifiedNorm = normalizeHeader_(row[headerIndex['creator notified']]);
    if (ALREADY_HANDLED_VALUES.indexOf(notifiedNorm) !== -1) return;
    updates.push({ row: firstDataRow + i, value: SENT_MARKER });
  });
  batchSetColumnValues_(trackerSheet, notifiedCol, updates);
}

/** Runs when you enter a confirmed email on Boosting Tracker (installable onEdit optional). */
function onEditBoostingTrackerPromote_(e) {
  if (!e || !e.range) return;
  if (e.range.getSheet().getName() !== SHEET_NAMES.BOOSTING_TRACKER) return;
  if (e.range.getRow() <= HEADER_ROW.BOOSTING_TRACKER) return;
  if (!e.value || String(e.value).indexOf('@') === -1) return;

  const lastCol = e.range.getSheet().getLastColumn();
  const headers = e.range.getSheet().getRange(HEADER_ROW.BOOSTING_TRACKER, 1, 1, lastCol).getValues()[0];
  const headerIndex = buildHeaderIndex_(headers);
  const emailCol0 = getBoostingTrackerEmailCol0_(headerIndex);
  if (emailCol0 === -1 || e.range.getColumn() !== emailCol0 + 1) return;

  promoteCreatorFromTrackerRow_(e.range.getRow());
}

function onEdit(e) {
  onEditBoostingTrackerPromote_(e);
}
