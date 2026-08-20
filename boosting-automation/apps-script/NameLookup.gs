/**
 * NameLookup.gs
 * Fills missing names on the active gift card month tab from the Names tab.
 */
function fillMissingNamesFromLookup() {
  const ctx = getGiftCardContext_();
  const rows = readGiftCardRows_(ctx);
  const lookup = buildNameLookup_();
  const firstNameCol = giftCardCol1_(ctx, 'First Name', false);
  const lastNameCol = giftCardCol1_(ctx, 'Last Name', false);
  if (firstNameCol === -1 || lastNameCol === -1) {
    throw new Error('Gift card tab must have First Name and Last Name columns.');
  }

  let filled = 0;
  rows.forEach((row) => {
    if (String(row['first name'] || '').trim() !== '') return;
    const name = lookup[normalizeHandle_(row[ctx.nameKey])];
    if (!name) return;
    ctx.sheet.getRange(row._sheetRow, firstNameCol).setValue(name.firstName);
    ctx.sheet.getRange(row._sheetRow, lastNameCol).setValue(name.lastName);
    filled++;
  });

  toast_('Filled ' + filled + ' missing name(s) on ' + ctx.sheet.getName() + ' from the Names tab.');
}
