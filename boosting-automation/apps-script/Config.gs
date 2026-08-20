/**
 * Config.gs
 * All sheet/tab names and column-header aliases live here so the rest of the
 * project never hard-codes a column letter. If a tab gets renamed or a
 * column gets reworded, update it here instead of hunting through the logic.
 */

const SHEET_NAMES = {
  BOOSTING_TRACKER: 'Boosting Tracker',
  GIFT_CARD_TEMPLATE: 'Gift Card Template',
  /** @deprecated Legacy horizontal layout — still supported as a fallback. */
  GIFT_CARD_LEGACY: 'Monthly Gift Card Cost Tracker',
  EOM_EXPORT: 'EOM Export',
};

/** Per-month tabs are named like "August Gift Card Cost Tracker" (month name only). */
const GIFT_CARD_MONTH_TAB_SUFFIX = 'Gift Card Cost Tracker';
const GIFT_CARD_YEAR_MIN = 2024;
const GIFT_CARD_YEAR_MAX = 2035;
const ACTIVE_GIFT_CARD_SHEET_PROPERTY = 'ACTIVE_GIFT_CARD_SHEET';
/** How many data rows get the Gift Card Amount formula when a new month tab is created. */
const GIFT_CARD_FORMULA_ROWS = 400;

/**
 * Boosting Tracker column D (1-based) holds the content/comp date when no "Date"
 * header is found. Used to pick the active gift card month tab automatically.
 */
const BOOSTING_TRACKER_DATE_COL = 4;
/** Gift card month tabs: copy each creator's tracker date into this column when present. */
const GIFT_CARD_DATE_COL = 4;
const BOOSTING_TRACKER_DATE_HEADERS = [
  'date', 'content date', 'video date', 'date added', 'boost date', 'comp date',
];
/** When a confirmed gift card email is pasted on Boosting Tracker, promotion runs automatically. */
const BOOSTING_TRACKER_EMAIL_HEADERS = [
  'email address', 'confirmed email', 'gift card email', 'creator email',
];
const BOOSTING_TRACKER_PLATFORM_HEADERS = [
  'platform(s) for usage', 'platform', 'platform for usage',
];

/** Optional: URL of a separate file that holds the Names tab. Leave blank if Names is in this spreadsheet. */
const EXTERNAL_NAMES_SHEET_ID = '';

const HEADER_ROW = {
  BOOSTING_TRACKER: 2,
  /** Header row on per-month gift card tabs (e.g. "August Gift Card Cost Tracker"). */
  GIFT_CARD_TRACKER: 1,
  /** Legacy horizontal layout only — row 1 = month labels, row 2 = field headers. */
  GIFT_CARD_TRACKER_MONTH_LABEL_ROW: 1,
  GIFT_CARD_TRACKER_FIELD_ROW: 2,
};

const DUPE_MARKERS = ['dupe'];
/** Creator Notified = Yes means the initial outreach email was sent (set manually or on email paste). */
const SENT_MARKER = 'Yes';
const ALREADY_HANDLED_VALUES = ['yes'];
/** Old script marker — cleared to blank automatically on Monday check. */
const LEGACY_QUEUED_MARKER = 'queued (auto)';
/** Only draft rows whose column D date is within this many days and matches the active batch month. */
const OUTREACH_DRAFT_MAX_AGE_DAYS = 45;
const PLATFORM_COLUMN_HEADER = 'Platform (auto)';

const OUTREACH_TYPE_NEW = 'New';
const OUTREACH_TYPE_FOLLOWUP = 'Follow-Up';

// Payout: 1st selected piece = $100, each additional piece = +$50.
const GIFT_CARD_BASE_AMOUNT = 100;
const GIFT_CARD_INCREMENT_AMOUNT = 50;

const CREATORIQ_LOOKUP_ENABLED = false;
const NAMES_LOOKUP_SHEET_NAME = 'Names';

const GEMINI_API_KEY_PROPERTY = 'GEMINI_API_KEY';
const GEMINI_MODEL = 'gemini-2.5-flash';

// --- Brand-new creator this month (first boost) ---

const NEW_CREATOR_PROMPT = `Hi {{FIRST_NAME}},

Exciting news, my team loved your partnership content and would like to use {{PIECES_LABEL}} of it! This means that as of right now you have earned a {{AMOUNT}} Wayfair Gift Card. My team will continue monitoring for content and for every additional piece of your content they use, your gift card amount will be raised by $50.

I will update you if anything else gets selected, and I plan to send gift cards out early next month!

Can you please confirm the email you would like the gift card to be addressed to, and send over the product links you featured in {{SELECTED_VIDEOS_PHRASE}} when you get a chance?:
{{LINKS}}

Best,
Adriana`;

const NEW_CREATOR_PROMPT_NO_LINKS = `Hi {{FIRST_NAME}},

Exciting news, my team loved your partnership content and would like to use {{PIECES_LABEL}} of it! This means that as of right now you have earned a {{AMOUNT}} Wayfair Gift Card. My team will continue monitoring for content and for every additional piece of your content they use, your gift card amount will be raised by $50.

I will update you if anything else gets selected, and I plan to send gift cards out early next month!

Can you please confirm the email you would like the gift card to be addressed to when you get a chance?

Best,
Adriana`;

// --- Already boosted this month: one new piece selected ---

const INCREMENTAL_SINGLE_PROMPT = `Hi {{FIRST_NAME}},

Exciting news, my team loved another piece of your partnership content and would like to use it! This means your Wayfair Gift Card amount has now been raised by another {{INCREMENT_AMOUNT}}.

My team will continue monitoring for content and for every additional piece of your content they use, your gift card amount will be raised by $50.

I will update you if anything else gets selected, and I plan to send gift cards out early next month!

Can you please send over the product link you featured in this selected video when you get a chance?:
{{LINKS}}

Best,
Adriana`;

const INCREMENTAL_SINGLE_PROMPT_NO_LINKS = `Hi {{FIRST_NAME}},

Exciting news, my team loved another piece of your partnership content and would like to use it! This means your Wayfair Gift Card amount has now been raised by another {{INCREMENT_AMOUNT}}.

My team will continue monitoring for content and for every additional piece of your content they use, your gift card amount will be raised by $50.

I will update you if anything else gets selected, and I plan to send gift cards out early next month!

Best,
Adriana`;

// --- Already boosted this month: multiple new pieces in one email ---

const INCREMENTAL_MULTI_PROMPT = `Hi {{FIRST_NAME}},

More exciting news, my team loved your latest partnership content and would like to use {{NEW_PIECES_LABEL}} more of it! Combined with what we've already used this month, your gift card total is now up to {{AMOUNT}}.

I will keep you posted if anything else gets selected, and I plan to send gift cards out early next month!

Can you please send over the product links you featured in {{SELECTED_VIDEOS_PHRASE}} when you get a chance?:
{{LINKS}}

Best,
Adriana`;

const INCREMENTAL_MULTI_PROMPT_NO_LINKS = `Hi {{FIRST_NAME}},

More exciting news, my team loved your latest partnership content and would like to use {{NEW_PIECES_LABEL}} more of it! Combined with what we've already used this month, your gift card total is now up to {{AMOUNT}}.

I will keep you posted if anything else gets selected, and I plan to send gift cards out early next month!

Best,
Adriana`;
