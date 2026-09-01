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
    const currentFirst = String(row['first name'] || '').trim();
    if (currentFirst !== '' && !cellLooksLikeTrackerDate_(currentFirst)) return;
    const handle = String(row[ctx.nameKey] || '').trim();
    const name = lookup[normalizeHandle_(handle)];
    const firstName = resolveGiftCardFirstName_(handle, name);
    if (!firstName) return;
    ctx.sheet.getRange(row._sheetRow, firstNameCol).setValue(firstName);
    if (lastNameCol !== -1 && name && name.lastName) {
      ctx.sheet.getRange(row._sheetRow, lastNameCol).setValue(name.lastName);
    }
    filled++;
  });

  toast_('Filled ' + filled + ' missing name(s) on ' + ctx.sheet.getName() + ' from the Names tab.');
}
