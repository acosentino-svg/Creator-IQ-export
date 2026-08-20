/**
 * OutreachDoc.gs
 * Writes outreach email drafts to a Google Doc (one doc per calendar day).
 * Outreach Queue stays a checklist only — no long message text in cells.
 */

const OUTREACH_DRAFTS_DOC_TITLE_PREFIX = 'Boosting Outreach Drafts — ';

/** Builds draft entries for every unsent Outreach Queue row. */
function collectOutreachDraftEntries_() {
  const sheet = getOutreachQueueSheet_();
  const read = readFlatSheetRows_(sheet, HEADER_ROW.OUTREACH_QUEUE);
  const sentKey = normalizeHeader_(SENT_CHECKBOX_HEADER);
  const typeKey = normalizeHeader_(TYPE_COLUMN_HEADER);
  const platformKey = normalizeHeader_(PLATFORM_COLUMN_HEADER);
  const platformLookup = buildPlatformLookupFromTracker_();
  const linksLookup = buildLinksLookupFromTracker_();

  const entries = [];
  const skipped = [];
  let alreadySent = 0;

  read.rows.forEach((row) => {
    if (row[sentKey]) {
      alreadySent++;
      return;
    }

    const firstName = String(row['first name'] || '').trim();
    const handle = String(row['creator handle'] || '').trim();
    const displayName = firstName || (handle ? capitalizeFirst_(handle.replace(/^@/, '').split(/[._]/)[0]) : '');
    const rowType = String(row[typeKey] || '').trim() || OUTREACH_TYPE_NEW;
    const isFollowUp = rowType === OUTREACH_TYPE_FOLLOWUP;
    const platform = String(row[platformKey] || '').trim()
      || lookupPlatformsForHandleFromTracker_(handle, platformLookup);
    const needsLinks = needsProductLinksForPlatforms_(platform);
    const links = resolveOutreachLinks_(row, handle, linksLookup);

    let newPieces = Number(row['new pieces of content used']) || 1;
    if (newPieces < 1) newPieces = 1;
    let amount = String(row['gift card amount'] || '').trim();
    if (!amount) amount = formatAmount_(calculateGiftCardAmount_(newPieces));

    const reasons = [];
    if (!displayName) reasons.push('missing name');
    if (needsLinks && !links) reasons.push('missing link');

    if (reasons.length) {
      skipped.push({
        row: row._sheetRow,
        handle: handle || '(blank handle)',
        type: rowType,
        pieces: newPieces,
        amount: amount,
        reasons: reasons.join(', '),
      });
      return;
    }

    entries.push({
      row: row._sheetRow,
      handle: handle,
      firstName: displayName,
      type: rowType,
      isFollowUp: isFollowUp,
      pieces: newPieces,
      amount: amount,
      links: links,
      platform: platform,
      message: buildDraftMessage_({
        isFollowUp: isFollowUp,
        handle: handle,
        firstName: displayName,
        pieces: newPieces,
        newPieces: newPieces,
        amount: amount,
        links: links,
        needsLinks: needsLinks,
      }),
    });
  });

  return {
    entries: entries,
    skipped: skipped,
    drafted: entries.length,
    skippedCount: skipped.length,
    skippedNoName: skipped.filter((s) => s.reasons.indexOf('missing name') !== -1).length,
    skippedNoLinks: skipped.filter((s) => s.reasons.indexOf('missing link') !== -1).length,
    alreadySent: alreadySent,
  };
}

function outreachDocPropertyKey_() {
  const tz = Session.getScriptTimeZone();
  return 'OUTREACH_DOC_' + Utilities.formatDate(new Date(), tz, 'yyyy-MM-dd');
}

function formatOutreachDocTitle_() {
  const tz = Session.getScriptTimeZone();
  return OUTREACH_DRAFTS_DOC_TITLE_PREFIX + Utilities.formatDate(new Date(), tz, 'MMM d, yyyy');
}

function getSpreadsheetParentFolder_() {
  try {
    const parents = DriveApp.getFileById(SpreadsheetApp.getActiveSpreadsheet().getId()).getParents();
    if (parents.hasNext()) return parents.next();
  } catch (e) {
    console.warn('getSpreadsheetParentFolder_ failed: ' + e);
  }
  return null;
}

/** Creates or overwrites today's outreach Google Doc and returns its URL. */
function writeOutreachDraftsGoogleDoc_(collectResult) {
  const entries = collectResult.entries || [];
  const skipped = collectResult.skipped || [];
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const props = PropertiesService.getScriptProperties();
  const propertyKey = outreachDocPropertyKey_();
  const title = formatOutreachDocTitle_();
  const tz = Session.getScriptTimeZone();

  let docId = props.getProperty(propertyKey);
  let doc;
  if (docId) {
    try {
      doc = DocumentApp.openById(docId);
    } catch (e) {
      docId = null;
    }
  }

  if (!docId) {
    doc = DocumentApp.create(title);
    docId = doc.getId();
    props.setProperty(propertyKey, docId);
    props.setProperty('OUTREACH_DOC_LATEST', docId);
    const folder = getSpreadsheetParentFolder_();
    if (folder) {
      try {
        DriveApp.getFileById(docId).moveTo(folder);
      } catch (e) {
        console.warn('Could not move outreach doc to spreadsheet folder: ' + e);
      }
    }
  } else {
    doc = DocumentApp.openById(docId);
    doc.setName(title);
  }

  const body = doc.getBody();
  body.clear();

  body.appendParagraph(title).setHeading(DocumentApp.ParagraphHeading.HEADING1);
  body.appendParagraph('Tracker: ' + ss.getName()).setItalic(true);
  body.appendParagraph(
    'Generated ' + Utilities.formatDate(new Date(), tz, 'MMMM d, yyyy h:mm a z') +
    ' — copy each message into CreatorIQ, then check Sent? on Outreach Queue.'
  );
  body.appendParagraph(
    entries.length + ' ready to send' +
    (skipped.length ? (' · ' + skipped.length + ' need fixes (see bottom)') : '')
  );
  body.appendHorizontalRule();

  if (!entries.length) {
    body.appendParagraph('No unsent outreach rows are ready to draft yet.').setItalic(true);
  }

  entries.forEach((entry, index) => {
    if (index > 0) body.appendHorizontalRule();
    body.appendParagraph(entry.handle).setHeading(DocumentApp.ParagraphHeading.HEADING2);
    body.appendParagraph(
      entry.type + ' · ' + formatPiecesLabel_(entry.pieces) + ' · ' + entry.amount +
      (entry.platform ? (' · ' + entry.platform) : '')
    );
    if (entry.links) {
      body.appendParagraph('Links').setBold(true);
      splitLinks_(entry.links).forEach((link) => body.appendListItem(link));
    }
    body.appendParagraph('Message').setBold(true);
    String(entry.message || '').split('\n').forEach((line) => {
      if (line.trim() === '') body.appendParagraph('');
      else body.appendParagraph(line);
    });
  });

  if (skipped.length) {
    body.appendPageBreak();
    body.appendParagraph('Needs attention before drafting').setHeading(DocumentApp.ParagraphHeading.HEADING1);
    body.appendParagraph('Fix these on Outreach Queue (or Boosting Tracker), then run Monday check again.').setItalic(true);
    skipped.forEach((s) => {
      body.appendParagraph(
        'Row ' + s.row + ': ' + s.handle + ' (' + s.type + ', ' + s.pieces + ' piece(s), ' + s.amount + ') — ' + s.reasons
      );
    });
  }

  doc.saveAndClose();
  return { url: doc.getUrl(), id: docId, count: entries.length };
}

function openUrlInNewTab_(url) {
  if (!url) return;
  const safeUrl = String(url).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
  const html = HtmlService.createHtmlOutput(
    '<p style="font-family:sans-serif;font-size:13px">Opening outreach drafts doc…</p>' +
    '<script>window.open("' + safeUrl + '");google.script.host.close();</script>'
  ).setWidth(260).setHeight(50);
  SpreadsheetApp.getUi().showModalDialog(html, 'Opening doc');
}

/** Opens today's outreach doc, or alerts if none exists yet. */
function openOutreachDraftsDoc_() {
  const props = PropertiesService.getScriptProperties();
  const docId = props.getProperty(outreachDocPropertyKey_()) || props.getProperty('OUTREACH_DOC_LATEST');
  if (!docId) {
    SpreadsheetApp.getUi().alert('No outreach doc yet. Run Monday check first.');
    return;
  }
  try {
    openUrlInNewTab_(DocumentApp.openById(docId).getUrl());
  } catch (e) {
    SpreadsheetApp.getUi().alert('Could not open outreach doc: ' + e);
  }
}
