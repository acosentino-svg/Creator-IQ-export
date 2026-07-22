/**
 * NameLookup.gs
 * Fills First/Last Name from the local Names tab (no API needed).
 * Runs automatically during sync; also available from the menu for a one-time catch-up.
 */

/**
 * Fills missing First/Last Name on every row in the New Boosted Creators and
 * Follow-Up message sheets whose handle matches the Names tab. Never overwrites
 * a name you already entered yourself.
 * @param {boolean=} showToast When true (default), shows a summary toast.
 * @return {{filled: number}}
 */
function fillMissingNamesFromLookup_(showToast) {
  if (showToast === undefined) showToast = true;
  let filled = 0;
  filled += fillMissingNamesOnSheet_(SHEET_NAMES.NEW_CREATORS_MSG, HEADER_ROW.NEW_CREATORS_MSG);
  filled += fillMissingNamesOnSheet_(SHEET_NAMES.FOLLOWUP_MSG, HEADER_ROW.FOLLOWUP_MSG);

  if (showToast) {
    toast_(
      filled
        ? 'Filled ' + filled + ' missing First/Last Name value(s) from the Names tab.'
        : 'No missing names to fill — every row already has a First Name, or no handle matched the Names tab.'
    );
  }
  return { filled: filled };
}

/**
 * @param {string} sheetName Logical sheet name from SHEET_NAMES.
 * @param {number} headerRowNum 1-based row number of the header row.
 * @return {number} How many rows were updated.
 */
function fillMissingNamesOnSheet_(sheetName, headerRowNum) {
  const lookup = buildNameLookup_();
  if (!Object.keys(lookup).length) return 0;

  const sheet = getSheet_(sheetName);
  const read = readFlatSheetRows_(sheet, headerRowNum);
  const firstNameCol = read.headerIndex['first name'];
  const lastNameCol = read.headerIndex['last name'];
  const handleCol = read.headerIndex['creator handle'];
  if (firstNameCol == null || handleCol == null) return 0;

  let filled = 0;
  read.rows.forEach((row) => {
    if (String(row['first name'] || '').trim() !== '') return;
    const name = lookup[normalizeHandle_(row['creator handle'])];
    if (!name) return;

    sheet.getRange(row._sheetRow, firstNameCol + 1).setValue(name.firstName);
    if (lastNameCol != null) {
      sheet.getRange(row._sheetRow, lastNameCol + 1).setValue(name.lastName);
    }
    filled++;
  });
  return filled;
}
