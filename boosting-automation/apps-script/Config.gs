/**
 * Config.gs
 * All sheet/tab names and column-header aliases live here so the rest of the
 * project never hard-codes a column letter. If a tab gets renamed or a
 * column gets reworded, update it here instead of hunting through the logic.
 */

const SHEET_NAMES = {
  BOOSTING_TRACKER: 'Boosting Tracker',
  GIFT_CARD_TRACKER: 'Monthly Gift Card Cost Tracker',
  NEW_CREATORS_MSG: 'New Boosted Creators Automated Message',
  FOLLOWUP_MSG: 'Follow-Up Boosted Creators Automated Message',
  EOM_EXPORT: 'EOM Export', // created automatically by exportEndOfMonth()
};

// Row (1-indexed) that holds the real column headers in each tab.
const HEADER_ROW = {
  BOOSTING_TRACKER: 2, // row 1 is the "tag Adriana" instruction banner
  GIFT_CARD_TRACKER_MONTH_LABEL_ROW: 1, // month name band, e.g. "July"
  GIFT_CARD_TRACKER_FIELD_ROW: 2, // Creator Handle / New Pieces / ... per block
  NEW_CREATORS_MSG: 1,
  FOLLOWUP_MSG: 1,
};

// Values in the Boosting Tracker "Creator Notified" column that mean
// "already handled, do not touch again".
const ALREADY_HANDLED_VALUES = ['yes'];

// Any "Creator Notified" value containing one of these substrings is a dupe.
const DUPE_MARKERS = ['dupe'];

// Marker this script writes into "Creator Notified" once a row has been
// drafted (added to a message sheet + gift card tracker) but a human has not
// yet actually sent the message in CreatorIQ. Keeping this distinct from
// "Yes" preserves the rule that "Yes" = a person actually notified the creator.
const QUEUED_MARKER = 'Queued (auto)';

// Column this script adds to the message sheets to hold the Gemini-drafted
// text and to track whether Josh has actually sent it yet.
const DRAFT_COLUMN_HEADER = 'Drafted Message (auto)';
const SENT_CHECKBOX_HEADER = 'Sent?';

// Script Properties key for the Gemini API key. Set once via
// Extensions > Apps Script > Project Settings > Script Properties,
// or by running setGeminiApiKey_() from the script editor.
const GEMINI_API_KEY_PROPERTY = 'GEMINI_API_KEY';
const GEMINI_MODEL = 'gemini-2.5-flash';

const NEW_CREATOR_PROMPT = `Hi {{FIRST_NAME}},

Exciting news, my team loved your partnership content and would like to use {{PIECES}} piece/s of it! This means that as of right now you have earned a {{AMOUNT}} Wayfair Gift Card. My team will continue monitoring for content and for every additional piece of your content they use, your gift card amount will be raised by $50.

I will update you if anything else gets selected, and I plan to send gift cards out early next month!

Can you please confirm the email you would like the gift card to be addressed to, and send over the product links you featured in just these selected videos when you get a chance?:
{{LINKS}}

Best,
Josh`;

const FOLLOWUP_PROMPT = `Hi {{FIRST_NAME}},

More exciting news, my team loved your latest partnership content and would like to use {{NEW_PIECES}} more piece/s of it! Combined with what we've already used this month, your gift card total is now up to {{AMOUNT}}.

I will keep you posted if anything else gets selected, and I plan to send gift cards out early next month!

Can you send over the product links you featured in just this newest content when you get a chance?:
{{LINKS}}

Best,
Josh`;
