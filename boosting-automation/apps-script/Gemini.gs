/**
 * Gemini.gs
 * Thin wrapper around the Gemini API so Automation.gs can draft messages
 * without a human pasting the sheet into the Gemini web app every time.
 *
 * One-time setup: run setGeminiApiKey_() from the Apps Script editor (or use
 * Project Settings > Script Properties) with your Gemini API key from
 * https://aistudio.google.com/apikey.
 */

function setGeminiApiKey_() {
  const ui = SpreadsheetApp.getUi();
  const resp = ui.prompt('Set Gemini API key', 'Paste your Gemini API key (from aistudio.google.com/apikey):', ui.ButtonSet.OK_CANCEL);
  if (resp.getSelectedButton() !== ui.Button.OK) return;
  const key = resp.getResponseText().trim();
  if (!key) return;
  PropertiesService.getScriptProperties().setProperty(GEMINI_API_KEY_PROPERTY, key);
  ui.alert('Gemini API key saved.');
}

function getGeminiApiKey_() {
  const key = PropertiesService.getScriptProperties().getProperty(GEMINI_API_KEY_PROPERTY);
  if (!key) throw new Error('No Gemini API key set. Run "Boosting Automation > Setup > Set Gemini API key" first.');
  return key;
}

/**
 * Sends one prompt to Gemini and returns the plain-text response.
 * Kept simple (single string in, single string out) since each message is
 * already fully templated in Config.gs before it gets here.
 */
function callGemini_(prompt) {
  const apiKey = getGeminiApiKey_();
  const url = 'https://generativelanguage.googleapis.com/v1beta/models/' + GEMINI_MODEL + ':generateContent?key=' + apiKey;
  const payload = {
    contents: [{ parts: [{ text: prompt }] }],
    generationConfig: { temperature: 0.4 },
  };
  const response = UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    payload: JSON.stringify(payload),
    muteHttpExceptions: true,
  });
  const code = response.getResponseCode();
  const body = JSON.parse(response.getContentText());
  if (code !== 200) {
    throw new Error('Gemini API error ' + code + ': ' + (body.error ? body.error.message : response.getContentText()));
  }
  const candidate = body.candidates && body.candidates[0];
  const text = candidate && candidate.content && candidate.content.parts && candidate.content.parts.map((p) => p.text).join('\n');
  if (!text) throw new Error('Gemini returned no text. Raw response: ' + response.getContentText());
  return text.trim();
}

/** Fills a Config.gs message template with row values. No LLM call needed for this part. */
function fillTemplate_(template, values) {
  let out = template;
  Object.keys(values).forEach((key) => {
    out = out.replace(new RegExp('{{' + key + '}}', 'g'), values[key] == null ? '' : String(values[key]));
  });
  return out;
}

/**
 * Optional polish pass: ask Gemini to lightly personalize the templated
 * message (e.g. reference the platform/content type) while preserving all
 * facts (amount, piece count, links) exactly. This mirrors what the old
 * "attach the sheet to Gemini" step did, but per-row and auditable.
 */
function personalizeWithGemini_(filledMessage, context) {
  const prompt = 'You are lightly polishing an already-correct outreach message to a content creator.\n' +
    'Rules:\n' +
    '- Do NOT change any dollar amount, number of pieces, links, or the sign-off.\n' +
    '- Keep it warm and concise, 1 short paragraph tweak at most.\n' +
    '- Return ONLY the final message text, no preamble, no markdown.\n\n' +
    'Context (for tone only, do not repeat verbatim): ' + JSON.stringify(context) + '\n\n' +
    'Message to polish:\n' + filledMessage;
  return callGemini_(prompt);
}
