import {Constants} from "./utils.js";

const DEFAULT_GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions";
const DEFAULT_GROQ_MODEL = "mixtral-8x7b-32768";
const DEFAULT_MAX_QUERIES = 8;

function readNumberSetting(key, defaultValue, min, max) {
  const value = parseInt(localStorage.getItem(key), 10);
  if (Number.isNaN(value)) {
    return defaultValue;
  }
  return Math.max(min, Math.min(max, value));
}

function getAiSettings() {
  return {
    apiKey: localStorage.getItem(Constants.USER_INSIGHT_AI_API_KEY) || "",
    endpoint: localStorage.getItem(Constants.USER_INSIGHT_AI_ENDPOINT) || DEFAULT_GROQ_ENDPOINT,
    model: localStorage.getItem(Constants.USER_INSIGHT_AI_MODEL) || DEFAULT_GROQ_MODEL,
    maxQueries: readNumberSetting(Constants.USER_INSIGHT_AI_MAX_QUERIES, DEFAULT_MAX_QUERIES, 1, 12)
  };
}

function sendAiRequest(settings, payload) {
  // Ensure compatibility with both Groq /responses (input) and /chat/completions (messages)
  return new Promise((resolve, reject) => {
    let payloadToSend = payload;
    try {
      const endpoint = (settings.endpoint || "").toLowerCase();
      // If endpoint appears to be the older /responses style, convert messages -> input
      if (endpoint.includes("/responses")) {
        // Build a simple input string from the messages array if provided
        if (Array.isArray(payload.messages)) {
          const combined = payload.messages.map(m => (m.content || m.text || "")).filter(Boolean).join("\n\n");
          payloadToSend = {...payload};
          payloadToSend.input = combined || payloadToSend.input || "";
          delete payloadToSend.messages;
        }
        // Convert OpenAI-style `max_tokens` to Groq `/responses` `max_output_tokens` when present
        if (payloadToSend && typeof payloadToSend.max_tokens !== "undefined") {
          // eslint-disable-next-line camelcase
          payloadToSend.max_output_tokens = payloadToSend.max_tokens;
          delete payloadToSend.max_tokens;
        }
        // Some /responses endpoints expect `model` and `input` at top-level — keep those fields
      }
    } catch {
      // If transformation fails, fall back to original payload
      payloadToSend = payload;
    }

    chrome.runtime.sendMessage({
      message: "userInsightAiRequest",
      apiKey: settings.apiKey,
      endpoint: settings.endpoint,
      payload: payloadToSend
    }, response => {
      if (!response) {
        reject(new Error("AI request returned no response."));
      } else if (!response.success) {
        reject(new Error(response.error || "AI request failed."));
      } else {
        resolve(response.data);
      }
    });
  });
}

function extractOutputText(response) {
  if (!response) {
    return "";
  }
  // Handle Groq OpenAI-compatible API format: choices[0].message.content
  if (Array.isArray(response.choices) && response.choices.length > 0) {
    const choice = response.choices[0];
    if (choice.message?.content) {
      return choice.message.content;
    }
    if (choice.text) {
      return choice.text;
    }
  }
  // Legacy formats
  if (typeof response.output_text === "string") {
    return response.output_text;
  }
  if (Array.isArray(response.output)) {
    return response.output.flatMap(item => item.content || [])
      .map(content => content.text || content.output_text || "")
      .filter(Boolean)
      .join("\n");
  }
  if (typeof response.text === "string") {
    return response.text;
  }
  return "";
}

function parseJsonOutput(response, fallbackMessage) {
  let text = extractOutputText(response).trim();
  if (!text) {
    throw new Error(fallbackMessage);
  }

  // Strip markdown code fences that some models wrap around JSON output
  // e.g. ```json { ... } ``` or ``` { ... } ```
  text = text.replace(/^```(?:json|JSON)?\s*/i, "").replace(/\s*```$/i, "").trim();

  try {

    return JSON.parse(text);
  } catch {
    // Extraction attempt: find the first { and then match it with the last }
    // This handles cases where the model adds text before/after the JSON
    const openIdx = text.indexOf("{");
    const closeIdx = text.lastIndexOf("}");

    if (openIdx !== -1 && closeIdx !== -1 && closeIdx > openIdx) {
      const jsonCandidate = text.substring(openIdx, closeIdx + 1);
      try {
        return JSON.parse(jsonCandidate);
      } catch {
        // Continue to the final error throw
      }
    }

    // Last resort: try to find a valid JSON array if object extraction failed
    if (text.includes("[")) {
      const arrayStart = text.indexOf("[");
      const arrayEnd = text.lastIndexOf("]");
      if (arrayStart !== -1 && arrayEnd !== -1 && arrayEnd > arrayStart) {
        try {
          return JSON.parse(text.substring(arrayStart, arrayEnd + 1));
        } catch {
          // Continue to the final error throw
        }
      }
    }

    throw new Error(fallbackMessage + " (The model did not return valid JSON. Response: " + text.substring(0, 200) + ")");
  }
}


function userForPrompt(user) {
  return {
    Id: user.Id,
    Name: user.Name,
    Email: user.Email || "",
    Username: user.Username || "",
    Alias: user.Alias || "",
    IsActive: user.IsActive,
    LastLoginDate: user.LastLoginDate || null,
    ProfileName: user.Profile?.Name || null,
    RoleName: user.UserRole?.Name || null
  };
}

export function buildQueryGenerationPrompt({user, objectInventory, maxQueries}) {
  return `You are selecting which Salesforce objects and filter relationships to inspect for a given User.

Task:
Identify where the supplied User is referenced in Salesforce data (owned records, created records, activity).

Rules:
- Return JSON only.
- Do not invent objects, fields, records, or counts.
- Use only objects and fields from the supplied object inventory.
- Use the exact placeholder {{USER_ID}} wherever the Salesforce User Id belongs in the soql field.
- Prefer high-signal relationships: owned records (OwnerId), created records (CreatedById), and activity.
- Do not generate more than ${maxQueries} queries.
- The soql field is for reference only and will NOT be executed as-is. The system rebuilds
  every query from scratch using only objectApiName, filterField, and section. Do not add
  any extra WHERE conditions — they will be ignored.

User:
${JSON.stringify(userForPrompt(user), null, 2)}

Object inventory:
${JSON.stringify(objectInventory, null, 2)}

Expected JSON shape:
{
  "queries": [
    {
      "section": "owned | created | activity",
      "objectApiName": "Account",
      "filterField": "OwnerId",
      "title": "All Accounts",
      "soql": "SELECT Id, Name FROM Account WHERE OwnerId = '{{USER_ID}}'",
      "rationale": "Short explanation"
    }
  ]
}`;
}

export function buildSummaryPrompt({user, sections}) {
  return `You are summarizing Salesforce query results for an admin.

Rules:
- Return JSON only.
- Use only the data supplied below.
- Do not guess missing counts, missing records, or activity.
- If a query failed or returned zero records, say that plainly.
- Keep the summary concise and human-readable.

User:
${JSON.stringify(userForPrompt(user), null, 2)}

Aggregated result sections:
${JSON.stringify(sections, null, 2)}

Expected JSON shape:
{
  "summary": "One concise paragraph.",
  "highlights": ["Short bullet", "Short bullet"]
}`;
}

export class UserInsightAiService {
  constructor() {
    this.settings = getAiSettings();
  }

  getConfiguration() {
    return {...this.settings};
  }

  ensureConfigured() {
    if (!this.settings.apiKey) {
      throw new Error("Groq API key is not configured. Open Options > AI and add an API key.");
    }
  }

  async generateQueryPlan({user, objectInventory}) {
    this.ensureConfigured();
    const prompt = buildQueryGenerationPrompt({
      user,
      objectInventory,
      maxQueries: this.settings.maxQueries
    });
    const response = await sendAiRequest(this.settings, {
      model: this.settings.model,
      messages: [
        {
          role: "system",
          content: "You are a JSON-only API. Respond with a single valid JSON object. No markdown, no code fences, no explanation — raw JSON only."
        },
        {
          role: "user",
          content: prompt
        }
      ],
      temperature: 0,
      // eslint-disable-next-line camelcase
      max_tokens: 4096
    });
    return parseJsonOutput(response, "Unable to parse AI-generated SOQL plan.");
  }



  async summarize({user, sections}) {
    this.ensureConfigured();
    const prompt = buildSummaryPrompt({user, sections});
    const response = await sendAiRequest(this.settings, {
      model: this.settings.model,
      messages: [
        {
          role: "system",
          content: "You are a JSON-only API. Respond with a single valid JSON object. No markdown, no code fences, no explanation — raw JSON only."
        },
        {
          role: "user",
          content: prompt
        }
      ],
      temperature: 0,
      // eslint-disable-next-line camelcase
      max_tokens: 2048
    });
    return parseJsonOutput(response, "Unable to parse AI-generated summary.");
  }
}



