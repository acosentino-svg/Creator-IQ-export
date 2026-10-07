/**
 * OutreachDoc.gs
 * Writes outreach email drafts to a Google Doc (one doc per calendar day).
 * Outreach Queue stays a checklist only — no long message text in cells.
 */

const OUTREACH_DRAFTS_DOC_TITLE_PREFIX = 'Boosting Outreach Drafts — ';
const OUTREACH_DOC_LINKS_TAB = 'Automation Links';

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
    ' — copy each message into CreatorIQ, then mark Creator Notified Yes after sending. When they reply, paste product links in column F or G on Boosting Tracker (auto-adds to gift card tab). Paste their email on the gift card tab Email Address column when ready.'
  );
  body.appendParagraph(
    entries.length + ' ready to send' +
    (collectResult.draftMonthLabel ? (' · batch month: ' + collectResult.draftMonthLabel) : '') +
    (skipped.length ? (' · ' + skipped.length + ' need fixes (see bottom)') : '')
  );
  body.appendHorizontalRule();

  if (!entries.length) {
    body.appendParagraph('No unsent outreach rows are ready to draft yet.').setItalic(true);
    const pending = collectResult.pending || 0;
    const skippedDupes = collectResult.skippedDupes || 0;
    const skippedRepeat = collectResult.skippedRepeatLinks || 0;
    const skippedStale = collectResult.skippedStale || 0;
    const skippedFix = collectResult.skippedCount || 0;
    if (pending || skippedDupes || skippedRepeat || skippedFix || skippedStale) {
      body.appendParagraph(
        'Scan: ' + pending + ' pending video(s)' +
        (skippedDupes ? (', ' + skippedDupes + ' dupe row(s) skipped') : '') +
        (skippedRepeat ? (', ' + skippedRepeat + ' repeat video(s) ignored') : '') +
        (skippedStale ? (', ' + skippedStale + ' out-of-month row(s) skipped') : '') +
        (skippedFix ? (', ' + skippedFix + ' creator(s) need a name') : '') +
        '.'
      );
    }
    if (pending > 0 && skippedFix) {
      body.appendParagraph(
        'Creators with missing names or non-AppLovin product links are listed at the bottom of this doc. AppLovin rows only need a handle (first name is guessed from the handle if Names tab is empty).'
      ).setItalic(true);
    }
  }

  entries.forEach((entry, index) => {
    if (index > 0) body.appendHorizontalRule();
    body.appendParagraph(entry.handle).setHeading(DocumentApp.ParagraphHeading.HEADING2);
    body.appendParagraph(
      entry.type + ' · ' + formatPiecesSlashLabel_(entry.pieces) + ' · ' + entry.amount +
      (entry.platform ? (' · ' + entry.platform) : '')
    ).setItalic(true);
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
        s.handle + ' (' + s.type + ', ' + s.pieces + ' piece(s), ' + s.amount + ') — ' + s.reasons
      );
    });
  }

  doc.saveAndClose();
  const url = doc.getUrl();
  showOutreachDocLinkTab_(url, title);
  return { url: url, id: docId, count: entries.length };
}

/** Puts a clickable doc link on a tab — no popup permissions needed. */
function showOutreachDocLinkTab_(url, title) {
  if (!url) return;
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(OUTREACH_DOC_LINKS_TAB);
  if (!sheet) sheet = ss.insertSheet(OUTREACH_DOC_LINKS_TAB);
  sheet.clear();
  sheet.getRange(1, 1).setValue('Latest outreach email drafts').setFontWeight('bold');
  sheet.getRange(2, 1).setValue(String(title || 'Google Doc'));
  sheet.getRange(3, 1).setFormula('=HYPERLINK("' + String(url).replace(/"/g, '""') + '","Click here to open the Google Doc")');
  sheet.getRange(4, 1).setValue(url).setFontSize(9);
  sheet.setColumnWidth(1, 520);
  ss.setActiveSheet(sheet);
  toast_('Emails written to Google Doc — click the link on the "' + OUTREACH_DOC_LINKS_TAB + '" tab.');
}

function openUrlInNewTab_(url) {
  showOutreachDocLinkTab_(url, formatOutreachDocTitle_());
}

/** Opens today's outreach doc via the Automation Links tab. */
function openOutreachDraftsDoc_() {
  const props = PropertiesService.getScriptProperties();
  const docId = props.getProperty(outreachDocPropertyKey_()) || props.getProperty('OUTREACH_DOC_LATEST');
  if (!docId) {
    toast_('No outreach doc yet. Run Monday check first.');
    return;
  }
  try {
    showOutreachDocLinkTab_(DocumentApp.openById(docId).getUrl(), formatOutreachDocTitle_());
  } catch (e) {
    toast_('Could not open outreach doc: ' + e);
  }
}
