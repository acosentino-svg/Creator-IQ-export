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
 * and Email in the gift card tracker WITHOUT waiting for them to reply
 * (this is the single biggest win from having API access — it can shrink
 * Step 3 down to "just links", since email is often already on file).
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
