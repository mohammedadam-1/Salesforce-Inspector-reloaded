import {Constants} from "./utils.js";

const DEFAULT_GROQ_ENDPOINT = "https://api.groq.com/openai/v1/responses";
const DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b";
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
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({
      message: "userInsightAiRequest",
      apiKey: settings.apiKey,
      endpoint: settings.endpoint,
      payload
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
  const text = extractOutputText(response).trim();
  if (!text) {
    throw new Error(fallbackMessage);
  }
  try {
    return JSON.parse(text);
  } catch {
    const match = text.match(/\{[\s\S]*\}/);
    if (match) {
      return JSON.parse(match[0]);
    }
    throw new Error(fallbackMessage + " The model did not return valid JSON.");
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
      input: prompt,
      text: {
        format: {
          type: "json_schema",
          name: "user_insight_query_plan",
          strict: true,
          schema: {
            type: "object",
            additionalProperties: false,
            properties: {
              queries: {
                type: "array",
                maxItems: this.settings.maxQueries,
                items: {
                  type: "object",
                  additionalProperties: false,
                  properties: {
                    section: {type: "string", enum: ["owned", "created", "activity"]},
                    objectApiName: {type: "string"},
                    filterField: {type: "string"},
                    title: {type: "string"},
                    soql: {type: "string"},
                    rationale: {type: "string"}
                  },
                  required: ["section", "objectApiName", "filterField", "title", "soql", "rationale"]
                }
              }
            },
            required: ["queries"]
          }
        }
      }
    });
    return parseJsonOutput(response, "Unable to parse AI-generated SOQL plan.");
  }



  async summarize({user, sections}) {
    this.ensureConfigured();
    const prompt = buildSummaryPrompt({user, sections});
    const response = await sendAiRequest(this.settings, {
      model: this.settings.model,
      input: prompt,
      text: {
        format: {
          type: "json_schema",
          name: "user_insight_summary",
          strict: true,
          schema: {
            type: "object",
            additionalProperties: false,
            properties: {
              summary: {type: "string"},
              highlights: {
                type: "array",
                maxItems: 6,
                items: {type: "string"}
              }
            },
            required: ["summary", "highlights"]
          }
        }
      }
    });
    return parseJsonOutput(response, "Unable to parse AI-generated summary.");
  }
}



