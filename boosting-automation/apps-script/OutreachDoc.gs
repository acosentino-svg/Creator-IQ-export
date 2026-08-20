/**
 * OutreachDoc.gs
 * Writes outreach email drafts to a Google Doc (one doc per calendar day).
 * Outreach Queue stays a checklist only — no long message text in cells.
 */

const OUTREACH_DRAFTS_DOC_TITLE_PREFIX = 'Boosting Outreach Drafts — ';

/** Builds draft entries for every unsent Outreach Queue row. */
function collectOutreachDraftEntries_() {
  return scanBoostingTrackerForMonday_();
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
    ' — copy each message into CreatorIQ. Paste confirmed email on Boosting Tracker to add them to the gift card tab.'
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
    body.appendParagraph('Fix these on Boosting Tracker, then run Monday check again.').setItalic(true);
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
