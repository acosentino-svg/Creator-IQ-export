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
  NEW_CREATORS_MSG: 'New Boosted Creators Automated Message',
  FOLLOWUP_MSG: 'Follow-Up Boosted Creators Automated Message',
  EOM_EXPORT: 'EOM Export',
};

/** Per-month tabs are named like "July 2026 Gift Card Cost Tracker". */
const GIFT_CARD_MONTH_TAB_SUFFIX = 'Gift Card Cost Tracker';
const ACTIVE_GIFT_CARD_SHEET_PROPERTY = 'ACTIVE_GIFT_CARD_SHEET';
/** How many data rows get the Gift Card Amount formula when a new month tab is created. */
const GIFT_CARD_FORMULA_ROWS = 400;

const EXTERNAL_SHEET_IDS = {
  NEW_CREATORS_MSG: 'https://docs.google.com/spreadsheets/d/1iYm99c9OaUf3uwSu6AsR2XTEGwBbGop7TU3s-LV_9UI/edit',
  FOLLOWUP_MSG: 'https://docs.google.com/spreadsheets/d/1eWhsrdo5jxBTms70o5yuHpDV2rEgIvNowwO0T7Z6I7c/edit',
};

const HEADER_ROW = {
  BOOSTING_TRACKER: 2,
  /** Header row on per-month gift card tabs (e.g. "July 2026 Gift Card Cost Tracker"). */
  GIFT_CARD_TRACKER: 1,
  /** Legacy horizontal layout only — row 1 = month labels, row 2 = field headers. */
  GIFT_CARD_TRACKER_MONTH_LABEL_ROW: 1,
  GIFT_CARD_TRACKER_FIELD_ROW: 2,
  NEW_CREATORS_MSG: 1,
  FOLLOWUP_MSG: 1,
};

const ALREADY_HANDLED_VALUES = ['yes'];
const DUPE_MARKERS = ['dupe'];
const QUEUED_MARKER = 'Queued (auto)';
const DRAFT_COLUMN_HEADER = 'Drafted Message (auto)';
const SENT_CHECKBOX_HEADER = 'Sent?';
const PROMOTED_COLUMN_HEADER = 'Added to Tracker? (auto)';
const PLATFORM_COLUMN_HEADER = 'Platform (auto)';

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
