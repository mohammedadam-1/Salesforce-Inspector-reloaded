import { Constants } from "./utils.js";

const DEFAULT_GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions";
const DEFAULT_GROQ_MODEL = "mixtral-8x7b-32768";
const DEFAULT_MAX_QUERIES = 8;

const SALESFORCE_TOOLS = [
  {
    name: "query_salesforce",
    type: "function",
    description: "Execute a SOQL query to fetch records from Salesforce. Use for finding records, counts, relationships.",
    parameters: {
      type: "object",
      properties: {
        soql: {
          type: "string",
          description: "Valid SOQL query. Example: SELECT Id, Name FROM Account WHERE OwnerId = '005xx' LIMIT 50"
        }
      },
      required: ["soql"]
    }
  },
  {
    name: "describe_object",
    type: "function",
    description: "Get the list of fields available on a Salesforce object. Use this before querying an object you are unsure about.",
    parameters: {
      type: "object",
      properties: {
        objectName: {
          type: "string",
          description: "Salesforce API name of the object. Example: Account, Contact, Opportunity, Case"
        }
      },
      required: ["objectName"]
    }
  },
  {
    name: "get_record",
    type: "function",
    description: "Fetch a single Salesforce record by ID with all key fields.",
    parameters: {
      type: "object",
      properties: {
        objectName: {
          type: "string",
          description: "Salesforce object API name. Example: Account"
        },
        recordId: {
          type: "string",
          description: "18-character Salesforce record ID"
        }
      },
      required: ["objectName", "recordId"]
    }
  }
];

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
          payloadToSend = { ...payload };
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

export function buildQueryGenerationPrompt({ user, objectInventory, maxQueries }) {
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

export function buildSummaryPrompt({ user, sections }) {
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

export function buildFieldDependencyAnalysisPrompt({ field, objectName, dependencies }) {
  return `You are an expert Salesforce Architect analyzing a specific field's dependencies.

STRICT RULES:
1. Respond with exactly one valid JSON object and nothing else.
2. DO NOT wrap the JSON in markdown code blocks.
3. DO NOT include any conversational text before or after the JSON.
4. Use only the keys: riskLevel, executiveSummary, refactoringRisks, recommendations.
5. Categorize riskLevel as "safe", "moderate", or "high".
6. If there are no dependencies in a category, return an empty array for that category.

Context:
- Object: ${objectName}
- Field: ${field}

Dependencies:
${JSON.stringify(dependencies, null, 2)}

Expected Output Format:
{
  "riskLevel": "safe",
  "executiveSummary": "Summary here.",
  "refactoringRisks": ["Risk 1"],
  "recommendations": ["Recommendation 1"]
}`;
}

export class UserInsightAiService {
  constructor() {
    this.settings = getAiSettings();
  }

  getConfiguration() {
    return { ...this.settings };
  }

  ensureConfigured() {
    if (!this.settings.apiKey) {
      throw new Error("Groq API key is not configured. Open Options > AI and add an API key.");
    }
  }

  async generateQueryPlan({ user, objectInventory }) {
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



  async summarize({ user, sections }) {
    this.ensureConfigured();
    const prompt = buildSummaryPrompt({ user, sections });
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

  async runAgent(userMessage, sfConn, apiVersion, onThinking = null) {
    this.ensureConfigured();

    const messages = [
      {
        role: "system",
        content: `You are an expert Salesforce assistant with direct access to a Salesforce org via tools.

Your capabilities:
- query_salesforce: run any SOQL query
- describe_object: inspect fields on any object
- get_record: fetch a single record by ID

Rules:
- Always use describe_object before querying an unfamiliar object name.
- Never guess field names — verify with describe_object first.
- If a query returns 0 results, try a broader query before concluding.
- Keep queries efficient — use LIMIT when counts are large.
- When you have enough information, stop calling tools and provide a final answer.
- Be concise, specific, and include counts, names, and key findings where useful.`
      },
      {
        role: "user",
        content: userMessage
      }
    ];

    const toolExecutors = {
      query_salesforce: async ({soql}) => {
        const result = await sfConn.rest(
          `/services/data/v${apiVersion}/query?q=${encodeURIComponent(soql)}`
        );
        return {
          totalSize: result.totalSize,
          records: Array.isArray(result.records) ? result.records.slice(0, 50) : []
        };
      },
      describe_object: async ({objectName}) => {
        const result = await sfConn.rest(
          `/services/data/v${apiVersion}/sobjects/${encodeURIComponent(objectName)}/describe`
        );
        return Array.isArray(result.fields)
          ? result.fields.map(f => ({
              name: f.name,
              label: f.label,
              type: f.type,
              referenceTo: Array.isArray(f.referenceTo) && f.referenceTo.length > 0 ? f.referenceTo : undefined
            }))
          : [];
      },
      get_record: async ({objectName, recordId}) => {
        return await sfConn.rest(
          `/services/data/v${apiVersion}/sobjects/${encodeURIComponent(objectName)}/${encodeURIComponent(recordId)}`
        );
      }
    };

    const MAX_ITERATIONS = 10;

    for (let i = 0; i < MAX_ITERATIONS; i++) {
      const response = await sendAiRequest(this.settings, {
        model: this.settings.model,
        messages,
        tools: SALESFORCE_TOOLS,
        tool_choice: "auto",
        temperature: 0,
        max_tokens: 4096
      });

      let choice = Array.isArray(response.choices) && response.choices[0];
      if (!choice) {
        const fallbackText = extractOutputText(response).trim();
        if (fallbackText) {
          return {
            answer: fallbackText,
            iterations: i + 1
          };
        }
        throw new Error("No response from AI.");
      }

      const toolCalls = choice.message?.tool_calls || choice.tool_calls || [];

      if (choice.finish_reason === "stop" || toolCalls.length === 0) {
        const answerText = typeof choice.message?.content === "string"
          ? choice.message.content
          : (choice.text || extractOutputText(response));
        return {
          answer: answerText || "",
          iterations: i + 1
        };
      }

      messages.push(choice.message || { role: "assistant", content: "", tool_calls: toolCalls });

      for (const toolCall of toolCalls) {
        const toolName = toolCall.function?.name;
        let args = {};
        try {
          args = JSON.parse(toolCall.function?.arguments || "{}");
        } catch (err) {
          args = { error: "Invalid tool arguments JSON" };
        }

        if (onThinking) {
          onThinking(toolName || "tool", args);
        }

        let toolResult;
        if (!toolName || !toolExecutors[toolName]) {
          toolResult = { error: `Unknown tool: ${toolName}` };
        } else {
          try {
            toolResult = await toolExecutors[toolName](args);
          } catch (err) {
            toolResult = { error: err.message || String(err) };
          }
        }

        messages.push({
          role: "tool",
          tool_call_id: toolCall.id,
          content: JSON.stringify(toolResult)
        });
      }
    }

    return {
      answer: "The agent reached the maximum number of iterations without producing a final answer. Please try a more specific question.",
      iterations: MAX_ITERATIONS
    };
  }
}

export class FieldDependencyAiService {
  constructor() {
    this.settings = getAiSettings();
  }

  ensureConfigured() {
    if (!this.settings.apiKey) {
      throw new Error("Groq API key is not configured. Open Options > AI and add an API key.");
    }
  }

  async analyzeField({ field, objectName, dependencies }) {
    this.ensureConfigured();
    const prompt = buildFieldDependencyAnalysisPrompt({ field, objectName, dependencies });
    const response = await sendAiRequest(this.settings, {
      model: this.settings.model,
      messages: [
        {
          role: "system",
          content: "You are a JSON-only API. Respond with exactly one valid JSON object containing keys riskLevel, executiveSummary, refactoringRisks, and recommendations. No markdown, no code fences, no explanation."
        },
        {
          role: "user",
          content: prompt
        }
      ],
      temperature: 0,
      max_tokens: 2048
    });

    try {
      return parseJsonOutput(response, "Unable to parse AI-generated field analysis.");
    } catch (error) {
      const text = extractOutputText(response).trim();
      return {
        riskLevel: "unknown",
        executiveSummary: text || "The AI returned an unexpected response.",
        refactoringRisks: [],
        recommendations: [],
        rawResponse: text
      };
    }
  }
}
