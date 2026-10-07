/**
 * CreatorIQ.gs
 * Integration point for CreatorIQ's API (ExchangeIQ / "CreatorIQ Standard CRM API").
 *
 * I don't yet have your exact API docs/Postman collection, so the endpoint
 * paths below are best-guess placeholders based on typical CreatorIQ REST
 * conventions (Publishers, Posts, Messages). Everything is wired so the rest
 * of the project (Automation.gs) already calls these functions — once you
 * share the real paths/response shape, only CIQ_CONFIG and the three
 * `ciq*_` functions below need to change, nothing else in the project.
 *
 * Until confirmed, every call is wrapped in try/catch and fails soft (logs +
 * returns null) so a wrong/placeholder endpoint never breaks the sheet sync.
 */

const CIQ_CONFIG = {
  BASE_URL: 'https://apis.creatoriq.com', // CONFIRM: exact base URL for your account/environment
  API_KEY_PROPERTY: 'CREATORIQ_API_KEY',
  CAMPAIGN_NAME: 'Wayfair Creators Boosting Partnership',
  // CONFIRM these three paths against your API docs / Postman collection:
  PUBLISHER_SEARCH_PATH: '/publishers', // e.g. GET /publishers?handle={handle}
  MESSAGES_LIST_PATH: '/messages', // e.g. GET /messages?campaign={id}&since={iso}
  MESSAGES_SEND_PATH: '/messages', // e.g. POST /messages { publisherId, body }
};

function setCreatorIQApiKey_() {
  const ui = SpreadsheetApp.getUi();
  const resp = ui.prompt('Set CreatorIQ API key', 'Paste your CreatorIQ API key:', ui.ButtonSet.OK_CANCEL);
  if (resp.getSelectedButton() !== ui.Button.OK) return;
  const key = resp.getResponseText().trim();
  if (!key) return;
  PropertiesService.getScriptProperties().setProperty(CIQ_CONFIG.API_KEY_PROPERTY, key);
  ui.alert('CreatorIQ API key saved.');
}

function getCreatorIQApiKey_() {
  const key = PropertiesService.getScriptProperties().getProperty(CIQ_CONFIG.API_KEY_PROPERTY);
  if (!key) throw new Error('No CreatorIQ API key set. Run "Boosting Automation > Setup > Set CreatorIQ API key" first.');
  return key;
}

/**
 * Diagnostic only - tries a handful of plausible base URLs + auth header
 * styles against your real API key and writes the raw HTTP status + response
 * body into a "CIQ Debug Output" tab, since I can't get into CreatorIQ's
 * documentation site directly. Even an error response can be useful - a 404
 * vs. a 401 vs. an HTML login page all tell us different things about what's
 * wrong with the guess. Run this, then copy/paste the tab's contents back.
 * Purely read-only GET requests - does not send or change anything.
 */
function testCreatorIQConnection_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const existing = ss.getSheetByName('CIQ Debug Output');
  if (existing) ss.deleteSheet(existing);
  const sheet = ss.insertSheet('CIQ Debug Output');
  sheet.getRange(1, 1, 1, 3).setValues([['Test', 'HTTP Status', 'Response (first 500 chars)']]).setFontWeight('bold');

  const key = getCreatorIQApiKey_();
  const base = 'https://apis.creatoriq.com'; // confirmed as the real domain by round 1 (structured JSON error, not a generic 404 page)

  const tests = [
    { label: 'Bare root, Bearer token', url: base + '/', headers: { Authorization: 'Bearer ' + key } },
    { label: 'Bare root, no auth at all', url: base + '/', headers: {} },
    { label: '/publishers?handle=test, NO auth at all', url: base + '/publishers?handle=test', headers: {} },
    { label: '/v1/publishers?handle=test, Bearer token', url: base + '/v1/publishers?handle=test', headers: { Authorization: 'Bearer ' + key } },
    { label: '/v2/publishers?handle=test, Bearer token', url: base + '/v2/publishers?handle=test', headers: { Authorization: 'Bearer ' + key } },
    { label: '/publishers?handle=test, lowercase x-api-key', url: base + '/publishers?handle=test', headers: { 'x-api-key': key } },
    { label: '/publishers?handle=test, key as query param', url: base + '/publishers?handle=test&api_key=' + encodeURIComponent(key), headers: {} },
    { label: '/oauth/token (checking for a token-exchange endpoint)', url: base + '/oauth/token', headers: {} },
  ];

  const rows = tests.map((t) => {
    try {
      const resp = UrlFetchApp.fetch(t.url, {
        method: 'get', headers: t.headers, muteHttpExceptions: true, followRedirects: true,
      });
      return ['GET ' + t.url + ' (' + t.label + ')', resp.getResponseCode(), resp.getContentText().substring(0, 500)];
    } catch (e) {
      return ['GET ' + t.url + ' (' + t.label + ')', 'ERROR', String(e)];
    }
  });

  sheet.getRange(2, 1, rows.length, 3).setValues(rows);
  sheet.autoResizeColumns(1, 1);
  SpreadsheetApp.getUi().alert('Done. Check the "CIQ Debug Output" tab, then copy/paste its contents back to me.');
}

function ciqFetch_(path, opts) {
  opts = opts || {};
  const url = CIQ_CONFIG.BASE_URL + path;
  const response = UrlFetchApp.fetch(url, Object.assign({
    method: opts.method || 'get',
    contentType: 'application/json',
    headers: { Authorization: 'Bearer ' + getCreatorIQApiKey_() }, // CONFIRM: header name/scheme (Bearer vs. API-key header)
    muteHttpExceptions: true,
  }, opts));
  const code = response.getResponseCode();
  if (code < 200 || code >= 300) {
    throw new Error('CreatorIQ API ' + (opts.method || 'GET') + ' ' + path + ' -> ' + code + ': ' + response.getContentText());
  }
  return JSON.parse(response.getContentText());
}

/**
 * Looks up a creator's profile by handle so we can pre-fill First/Last Name
 * in the gift card tracker WITHOUT waiting for them to reply. The email this
 * returns is deliberately NOT written into the tracker's Email Address column
 * — it's their CreatorIQ account/login email, not necessarily the address
 * they want a gift card sent to (the outreach message explicitly asks them
 * to confirm that separately). Automation.gs leaves it as a cell note only,
 * as a hint for whoever's filling in the confirmed address later.
 * Returns null (never throws) so a lookup miss/placeholder-endpoint never
 * blocks the sheet sync — the row just falls back to the old "ask them"
 * flow, same as before.
 */
function ciqFindPublisherByHandle_(handle) {
  try {
    const data = ciqFetch_(CIQ_CONFIG.PUBLISHER_SEARCH_PATH + '?handle=' + encodeURIComponent(handle));
    const publisher = Array.isArray(data) ? data[0] : (data.results ? data.results[0] : data);
    if (!publisher) return null;
    return {
      id: publisher.id || publisher.publisherId,
      firstName: publisher.firstName || (publisher.name ? String(publisher.name).split(' ')[0] : ''),
      lastName: publisher.lastName || (publisher.name ? String(publisher.name).split(' ').slice(1).join(' ') : ''),
      email: publisher.email || (publisher.emails && publisher.emails[0]) || '',
    };
  } catch (err) {
    console.warn('ciqFindPublisherByHandle_ failed for "' + handle + '": ' + err);
    return null;
  }
}

/** Sends a drafted message directly through CreatorIQ instead of copy/paste. */
function ciqSendMessage_(publisherId, body) {
  return ciqFetch_(CIQ_CONFIG.MESSAGES_SEND_PATH, {
    method: 'post',
    payload: JSON.stringify({ publisherId: publisherId, body: body }),
  });
}

/**
 * Polls for inbound replies since a given time. Intended use: extract email
 * + product links from the free-text reply (Gemini is a good fit for THIS
 * step, unlike the outbound mail-merge — extracting unstructured fields is
 * exactly what an LLM is good at) and write them into the gift card tracker
 * / Boosting Tracker automatically. Not wired into Automation.gs yet pending
 * confirmation of the real endpoint + response shape.
 */
function ciqListInboundMessagesSince_(sinceIso) {
  return ciqFetch_(CIQ_CONFIG.MESSAGES_LIST_PATH + '?since=' + encodeURIComponent(sinceIso) + '&direction=inbound');
}

/**
 * Uses Gemini to pull a structured { email, links[] } out of a free-text
 * creator reply. Kept separate from the outbound mail-merge logic in
 * Gemini.gs — this is a case where an LLM genuinely earns its keep, since
 * the input is unstructured and the shape of a "sure, here's my email and
 * links" reply varies a lot creator to creator.
 */
function extractEmailAndLinksFromReply_(replyText) {
  const prompt = 'Extract the email address and all product/storefront links from this creator reply. ' +
    'Return ONLY compact JSON like {"email": "...", "links": ["...", "..."]} with no other text. ' +
    'If the email is missing, use null. If no links are found, use an empty array.\n\nReply:\n' + replyText;
  const raw = callGemini_(prompt);
  const jsonMatch = raw.match(/\{[\s\S]*\}/);
  if (!jsonMatch) throw new Error('Could not parse Gemini extraction output: ' + raw);
  return JSON.parse(jsonMatch[0]);
}
