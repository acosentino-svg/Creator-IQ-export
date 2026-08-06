/**
 * Run this once after adding/updating the Names tab. It fills First Name and
 * Last Name on every existing New Boosted Creators row whose handle matches
 * either an Instagram or TikTok handle in that tab. It never overwrites a
 * name you already entered yourself.
 */
function fillMissingNamesFromLookup() {
  const sheet = getOutreachQueueSheet_();
  const read = readFlatSheetRows_(sheet, HEADER_ROW.OUTREACH_QUEUE);
  const lookup = buildNameLookup_();

  const firstNameCol = read.headerIndex['first name'];
  const lastNameCol = read.headerIndex['last name'];
  const handleCol = read.headerIndex['creator handle'];
  if (firstNameCol == null || lastNameCol == null || handleCol == null) {
    throw new Error('Outreach Queue must have Creator Handle, First Name, and Last Name columns.');
  }

  let filled = 0;
  read.rows.forEach((row) => {
    if (String(row['first name'] || '').trim() !== '') return; // never overwrite a human-entered name
    const name = lookup[normalizeHandle_(row['creator handle'])];
    if (!name) return;

    sheet.getRange(row._sheetRow, firstNameCol + 1).setValue(name.firstName);
    sheet.getRange(row._sheetRow, lastNameCol + 1).setValue(name.lastName);
    filled++;
  });

  toast_('Filled ' + filled + ' missing First/Last Name value(s) from the Names tab.');
}
