/* global React */
/**
 * InspectorAiBackendConfig — Enterprise-grade AI backend configuration panel
 *
 * Storage keys (reused, NOT duplicated):
 *   sfirBackendUrl   — Backend URL
 *   sfirBackendApiKey — API Key
 *   sfirBackendOrgId  — Organization ID
 *   sfirBackendAdvanced — JSON blob for provider, model, timeouts, etc.
 */

const h = React.createElement;

const AI_PROVIDERS = [
  {value: "openai", label: "OpenAI", models: ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo"]},
  {value: "groq", label: "Groq", models: ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768", "gemma2-9b-it"]},
  {value: "anthropic", label: "Anthropic", models: ["claude-sonnet-4-20250514", "claude-haiku-35-20241022", "claude-3-5-sonnet-20241022"]},
  {value: "gemini", label: "Gemini", models: ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"]},
  {value: "azure-openai", label: "Azure OpenAI", models: ["gpt-4o", "gpt-4", "gpt-35-turbo"]},
  {value: "ollama", label: "Ollama", models: ["llama3", "mistral", "codellama", "phi3"]},
  {value: "openrouter", label: "OpenRouter", models: ["openai/gpt-4o", "anthropic/claude-3.5-sonnet", "google/gemini-pro"]},
  {value: "custom", label: "Custom", models: []},
];

const STATUS_LABELS = {
  connected: "Connected",
  connecting: "Connecting…",
  offline: "Offline",
  auth_failed: "Authentication Failed",
  unreachable: "Backend Unreachable",
  unknown: "Not Configured",
};

function normalizeBackendUrl(value) {
  let url = (value || "").trim();
  if (!url) return "";
  if (url.startsWith("//")) url = "http:" + url;
  if (/^0\.0\.0\.0(?::\d+)?(?:\/.*)?$/.test(url)) url = "http://" + url;

  try {
    const parsed = new URL(url);
    if (parsed.hostname === "0.0.0.0") parsed.hostname = "localhost";
    return parsed.toString().replace(/\/+$/, "");
  } catch {
    return url.replace(/\/+$/, "");
  }
}

function getAdvanced() {
  try {
    return JSON.parse(localStorage.getItem("sfirBackendAdvanced") || "{}");
  } catch { return {}; }
}

function saveAdvanced(obj) {
  localStorage.setItem("sfirBackendAdvanced", JSON.stringify(obj));
}

class InspectorAiBackendConfig extends React.Component {
  constructor(props) {
    super(props);
    const adv = getAdvanced();
    const storedBackendUrl = localStorage.getItem("sfirBackendUrl") || "";
    const normalizedBackendUrl = normalizeBackendUrl(storedBackendUrl);
    if (normalizedBackendUrl && normalizedBackendUrl !== storedBackendUrl) {
      localStorage.setItem("sfirBackendUrl", normalizedBackendUrl);
    }
    this.state = {
      // Core config (existing keys)
      backendUrl: normalizedBackendUrl,
      apiKey: localStorage.getItem("sfirBackendApiKey") || "",
      orgId: localStorage.getItem("sfirBackendOrgId") || "",
      // Provider & model
      provider: adv.provider || "custom",
      model: adv.model || "",
      // Advanced
      requestTimeout: adv.requestTimeout ?? 30,
      enableStreaming: adv.enableStreaming ?? true,
      retryAttempts: adv.retryAttempts ?? 2,
      connectionTimeout: adv.connectionTimeout ?? 10,
      debugLogging: adv.debugLogging ?? false,
      // UI state
      connectionStatus: "unknown",
      statusMessage: "",
      backendVersion: null,
      responseTime: null,
      lastHealthCheck: null,
      isTesting: false,
      isSaving: false,
      toast: null, // {type, message}
      expandedSections: {connection: true, provider: true, advanced: false},
      urlError: null,
      apiKeyError: null,
      dirty: false,
    };
    this.testConnection = this.testConnection.bind(this);
    this.saveConfig = this.saveConfig.bind(this);
    this.resetConfig = this.resetConfig.bind(this);
    this.reconnect = this.reconnect.bind(this);
  }

  componentDidMount() {
    if (this.state.backendUrl && this.state.apiKey) {
      this.testConnection(true);
    }
  }

  toggleSection(name) {
    this.setState(prev => ({
      expandedSections: {...prev.expandedSections, [name]: !prev.expandedSections[name]}
    }));
  }

  setField(field, value) {
    this.setState({[field]: value, dirty: true});
    // Clear inline errors on edit
    if (field === "backendUrl") this.setState({urlError: null});
    if (field === "apiKey") this.setState({apiKeyError: null});
  }

  validateUrl(url) {
    if (!url) return "Backend URL is required.";
    try {
      const u = new URL(url);
      if (!["http:", "https:"].includes(u.protocol)) return "URL must start with http:// or https://";
    } catch {
      return "Invalid URL format.";
    }
    return null;
  }

  async testConnection(silent = false) {
    const {backendUrl, apiKey} = this.state;
    const normalizedBackendUrl = normalizeBackendUrl(backendUrl);
    const urlErr = this.validateUrl(normalizedBackendUrl);
    if (urlErr) {
      this.setState({urlError: urlErr, connectionStatus: "offline"});
      return false;
    }
    if (!apiKey) {
      this.setState({apiKeyError: "API Key is required.", connectionStatus: "offline"});
      return false;
    }

    this.setState({
      backendUrl: normalizedBackendUrl,
      isTesting: true,
      connectionStatus: "connecting",
      statusMessage: "",
      urlError: null,
      apiKeyError: null,
    });
    const start = performance.now();

    try {
      const base = normalizedBackendUrl;
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), (this.state.connectionTimeout || 10) * 1000);

      const resp = await fetch(`${base}/api/v1/health/live`, {
        method: "GET",
        headers: {"Authorization": "Bearer " + apiKey, "Accept": "application/json"},
        signal: controller.signal,
      });
      clearTimeout(timeout);
      const elapsed = Math.round(performance.now() - start);

      if (resp.ok) {
        let data = {};
        try { data = await resp.json(); } catch { /* ok */ }
        this.setState({
          connectionStatus: "connected",
          statusMessage: "Backend is healthy and responding.",
          backendVersion: data.version || data.app_version || null,
          responseTime: elapsed,
          lastHealthCheck: new Date().toLocaleTimeString(),
          isTesting: false,
        });
        if (!silent) this.showToast("success", "Connection successful — backend is healthy.");
        return true;
      } else if (resp.status === 401 || resp.status === 403) {
        this.setState({
          connectionStatus: "auth_failed",
          statusMessage: `Authentication failed (${resp.status}). Check your API key.`,
          apiKeyError: `HTTP ${resp.status} — Invalid or expired API key.`,
          isTesting: false,
          responseTime: elapsed,
        });
        if (!silent) this.showToast("error", "Authentication failed. Please verify your API key.");
        return false;
      } else if (resp.status === 404) {
        this.setState({
          connectionStatus: "unreachable",
          statusMessage: "Health endpoint not found (404). Verify the backend URL.",
          urlError: "Health endpoint returned 404. Is this the correct backend URL?",
          isTesting: false,
          responseTime: elapsed,
        });
        return false;
      } else {
        this.setState({
          connectionStatus: "offline",
          statusMessage: `Backend returned HTTP ${resp.status}.`,
          isTesting: false,
          responseTime: elapsed,
        });
        if (!silent) this.showToast("error", `Backend returned HTTP ${resp.status}.`);
        return false;
      }
    } catch (e) {
      const elapsed = Math.round(performance.now() - start);
      if (e.name === "AbortError") {
        this.setState({
          connectionStatus: "unreachable",
          statusMessage: "Connection timed out.",
          isTesting: false,
          responseTime: elapsed,
        });
        if (!silent) this.showToast("error", "Connection timed out. Check URL and network.");
        return false;
      } else {
        const isSSL = e.message?.includes("SSL") || e.message?.includes("certificate");
        const isCORS = e.message?.includes("CORS") || e.message?.includes("NetworkError");
        let msg = e.message || "Connection refused or network error.";
        if (isSSL) msg = "SSL/TLS error — check certificate configuration.";
        if (isCORS) msg = "Network error — backend may be unreachable or CORS blocked.";
        this.setState({
          connectionStatus: "unreachable",
          statusMessage: msg,
          urlError: msg,
          isTesting: false,
          responseTime: elapsed,
        });
        if (!silent) this.showToast("error", msg);
        return false;
      }
    }
  }

  saveConfig() {
    const {backendUrl, apiKey, orgId, provider, model, requestTimeout, enableStreaming, retryAttempts, connectionTimeout, debugLogging} = this.state;
    const normalizedBackendUrl = normalizeBackendUrl(backendUrl);
    const urlErr = this.validateUrl(normalizedBackendUrl);
    if (urlErr) {
      this.setState({urlError: urlErr});
      this.showToast("error", urlErr);
      return;
    }
    if (!apiKey) {
      this.setState({apiKeyError: "API Key is required."});
      this.showToast("error", "API Key is required.");
      return;
    }
    this.setState({isSaving: true});

    // Core keys — the ONLY storage keys consumed by backend_service.js and aiApiClient.js
    localStorage.setItem("sfirBackendUrl", normalizedBackendUrl);
    localStorage.setItem("sfirBackendApiKey", apiKey);
    if (orgId) {
      localStorage.setItem("sfirBackendOrgId", orgId);
    } else {
      localStorage.removeItem("sfirBackendOrgId");
    }

    // Additional settings stored in a single JSON blob
    saveAdvanced({provider, model, requestTimeout, enableStreaming, retryAttempts, connectionTimeout, debugLogging});

    setTimeout(async () => {
      this.setState({isSaving: false, dirty: false});
      this.showToast("success", "Configuration saved. Testing connection...");
      const ok = await this.testConnection(true);
      if (ok) {
        this.showToast("success", "Connected! Opening Inspector AI...");
        setTimeout(() => {
          const host = new URLSearchParams(location.search).get("host") || "";
          const inspectorUrl = chrome.runtime.getURL("pages/inspector-ai/index.html?host=" + encodeURIComponent(host));
          window.location.href = inspectorUrl;
        }, 1200);
      }
    }, 300);
  }

  resetConfig() {
    if (!confirm("Reset all Inspector AI backend configuration?")) return;
    localStorage.removeItem("sfirBackendUrl");
    localStorage.removeItem("sfirBackendApiKey");
    localStorage.removeItem("sfirBackendOrgId");
    localStorage.removeItem("sfirBackendAdvanced");
    this.setState({
      backendUrl: "", apiKey: "", orgId: "",
      provider: "custom", model: "",
      requestTimeout: 30, enableStreaming: true, retryAttempts: 2,
      connectionTimeout: 10, debugLogging: false,
      connectionStatus: "unknown", statusMessage: "", backendVersion: null,
      responseTime: null, lastHealthCheck: null,
      urlError: null, apiKeyError: null, dirty: false,
    });
    this.showToast("warning", "Configuration reset. All backend settings cleared.");
  }

  reconnect() {
    this.testConnection(false);
  }

  showToast(type, message) {
    this.setState({toast: {type, message}});
    setTimeout(() => this.setState({toast: null}), 5000);
  }

  getModelsForProvider() {
    const p = AI_PROVIDERS.find(x => x.value === this.state.provider);
    return p ? p.models : [];
  }

  renderChevron(expanded) {
    return h("svg", {className: "ai-config-section-chevron" + (expanded ? " expanded" : ""), viewBox: "0 0 24 24", width: "20", height: "20", fill: "none", stroke: "currentColor", strokeWidth: "2"},
      h("path", {d: "M6 9l6 6 6-6"})
    );
  }

  render() {
    const {connectionStatus, statusMessage, isTesting, isSaving, toast, expandedSections,
      backendUrl, apiKey, orgId, provider, model,
      requestTimeout, enableStreaming, retryAttempts, connectionTimeout, debugLogging,
      backendVersion, responseTime, lastHealthCheck,
      urlError, apiKeyError, dirty} = this.state;

    const statusClass = (connectionStatus === "auth_failed" || connectionStatus === "unreachable") ? "error"
      : connectionStatus === "connecting" ? "unknown" : connectionStatus;
    const statusLabel = STATUS_LABELS[connectionStatus] || "Unknown";
    const models = this.getModelsForProvider();
    const providerLabel = AI_PROVIDERS.find(p => p.value === provider)?.label || provider;

    return h("div", {className: "ai-config-panel"},

      // Toast
      toast && h("div", {className: "ai-config-toast " + toast.type},
        h("span", {className: "ai-config-toast-icon"}, toast.type === "success" ? "✓" : toast.type === "error" ? "✕" : "!"),
        h("span", null, toast.message),
        h("button", {className: "ai-config-toast-close", onClick: () => this.setState({toast: null})}, "×")
      ),

      // Status Banner
      h("div", {className: "ai-config-status-banner " + statusClass},
        h("div", {className: "ai-config-status-left"},
          h("div", {className: "ai-config-status-dot " + statusClass}),
          h("div", null,
            h("div", {className: "ai-config-status-text"}, statusLabel),
            statusMessage && h("div", {className: "ai-config-status-sub"}, statusMessage)
          )
        ),
        h("div", {className: "ai-config-status-right"},
          h("button", {
            className: "ai-config-btn ai-config-btn-neutral",
            onClick: this.reconnect,
            disabled: isTesting || !backendUrl,
          }, isTesting ? h("span", {className: "ai-config-spinner dark"}) : null, isTesting ? "Testing…" : "Test Connection"),
          connectionStatus === "connected" ? h("button", {
            className: "ai-config-btn ai-config-btn-success",
            onClick: () => {
              const host = new URLSearchParams(location.search).get("host") || "";
              const url = chrome.runtime.getURL("pages/inspector-ai/index.html?host=" + encodeURIComponent(host));
              window.location.href = url;
            },
            style: {marginLeft: "6px"},
          }, "Launch Inspector AI") : null
        )
      ),

      // Stats Row
      h("div", {className: "ai-config-stats"},
        h("div", {className: "ai-config-stat"},
          h("span", {className: "ai-config-stat-label"}, "Backend Version"),
          h("span", {className: "ai-config-stat-value" + (backendVersion ? "" : " muted")}, backendVersion || "—")
        ),
        h("div", {className: "ai-config-stat"},
          h("span", {className: "ai-config-stat-label"}, "Last Health Check"),
          h("span", {className: "ai-config-stat-value" + (lastHealthCheck ? "" : " muted")}, lastHealthCheck || "—")
        ),
        h("div", {className: "ai-config-stat"},
          h("span", {className: "ai-config-stat-label"}, "Response Time"),
          h("span", {className: "ai-config-stat-value" + (responseTime != null ? "" : " muted")}, responseTime != null ? responseTime + " ms" : "—")
        ),
        h("div", {className: "ai-config-stat"},
          h("span", {className: "ai-config-stat-label"}, "Provider"),
          h("span", {className: "ai-config-stat-value" + (provider !== "custom" ? "" : " muted")}, providerLabel)
        ),
        h("div", {className: "ai-config-stat"},
          h("span", {className: "ai-config-stat-label"}, "Model"),
          h("span", {className: "ai-config-stat-value" + (model ? "" : " muted")}, model || "—")
        )
      ),

      // Section 1: Connection
      h("div", {className: "ai-config-section"},
        h("div", {className: "ai-config-section-header", onClick: () => this.toggleSection("connection")},
          h("div", {className: "ai-config-section-title"},
            h("span", {className: "ai-config-section-icon primary"}, "⚡"),
            "Connection Settings",
            h("span", {className: "ai-config-section-badge required"}, "Required")
          ),
          this.renderChevron(expandedSections.connection)
        ),
        expandedSections.connection && h("div", {className: "ai-config-section-body"},
          h("div", {className: "ai-config-field"},
            h("label", {className: "ai-config-field-label"}, "Backend URL", h("span", {className: "required-marker"}, " *")),
            h("span", {className: "ai-config-field-help"}, "The URL of your Inspector AI FastAPI server. (e.g. http://localhost:8000)"),
            h("input", {
              className: "ai-config-input" + (urlError ? " error" : connectionStatus === "connected" ? " success" : ""),
              type: "url",
              placeholder: "https://your-backend.example.com",
              value: backendUrl,
              onChange: (e) => this.setField("backendUrl", e.target.value),
              id: "ai-config-backend-url",
            }),
            urlError && h("div", {className: "ai-config-field-error"}, "⚠ ", urlError)
          ),
          h("div", {className: "ai-config-field"},
            h("label", {className: "ai-config-field-label"}, "API Key", h("span", {className: "required-marker"}, " *")),
            h("span", {className: "ai-config-field-help"}, "Generate this from your Inspector AI backend. (Currently not implemented in backend, enter any value)"),
            h("input", {
              className: "ai-config-input" + (apiKeyError ? " error" : ""),
              type: "password",
              placeholder: "sk-... or your API key",
              value: apiKey,
              onChange: (e) => this.setField("apiKey", e.target.value),
              id: "ai-config-api-key",
            }),
            apiKeyError && h("div", {className: "ai-config-field-error"}, "⚠ ", apiKeyError)
          ),
          h("div", {className: "ai-config-field"},
            h("label", {className: "ai-config-field-label"}, "Organization ID"),
            h("span", {className: "ai-config-field-help"}, "Automatically detected from Salesforce whenever possible.")
          )
        )
      ),

      // Section 2: AI Provider
      h("div", {className: "ai-config-section"},
        h("div", {className: "ai-config-section-header", onClick: () => this.toggleSection("provider")},
          h("div", {className: "ai-config-section-title"},
            h("span", {className: "ai-config-section-icon green"}, "AI"),
            "AI Provider & Model"
          ),
          this.renderChevron(expandedSections.provider)
        ),
        expandedSections.provider && h("div", {className: "ai-config-section-body"},
          h("div", {className: "ai-config-field-row"},
            h("div", {className: "ai-config-field"},
              h("label", {className: "ai-config-field-label"}, "Provider"),
              h("select", {
                className: "ai-config-select",
                value: provider,
                onChange: (e) => {
                  const newProvider = e.target.value;
                  const newModels = AI_PROVIDERS.find(p => p.value === newProvider)?.models || [];
                  this.setState({provider: newProvider, model: newModels[0] || "", dirty: true});
                },
                id: "ai-config-provider",
              },
              AI_PROVIDERS.map(p => h("option", {key: p.value, value: p.value}, p.label))
              )
            ),
            h("div", {className: "ai-config-field"},
              h("label", {className: "ai-config-field-label"}, "Model"),
              models.length > 0
                ? h("select", {
                  className: "ai-config-select",
                  value: model,
                  onChange: (e) => this.setField("model", e.target.value),
                  id: "ai-config-model",
                },
                models.map(m => h("option", {key: m, value: m}, m))
                )
                : h("input", {
                  className: "ai-config-input",
                  type: "text",
                  placeholder: "Enter model name",
                  value: model,
                  onChange: (e) => this.setField("model", e.target.value),
                  id: "ai-config-model",
                })
            )
          )
        )
      ),

      // Section 3: Advanced
      h("div", {className: "ai-config-section"},
        h("div", {className: "ai-config-section-header", onClick: () => this.toggleSection("advanced")},
          h("div", {className: "ai-config-section-title"},
            h("span", {className: "ai-config-section-icon amber"}, "⚙"),
            "Advanced Settings",
            h("span", {className: "ai-config-section-badge optional"}, "Optional")
          ),
          this.renderChevron(expandedSections.advanced)
        ),
        expandedSections.advanced && h("div", {className: "ai-config-section-body"},
          h("div", {className: "ai-config-field-row"},
            h("div", {className: "ai-config-field"},
              h("label", {className: "ai-config-field-label"}, "Request Timeout (seconds)"),
              h("input", {className: "ai-config-input", type: "number", min: 5, max: 300, value: requestTimeout,
                onChange: (e) => this.setField("requestTimeout", parseInt(e.target.value, 10) || 30)})
            ),
            h("div", {className: "ai-config-field"},
              h("label", {className: "ai-config-field-label"}, "Connection Timeout (seconds)"),
              h("input", {className: "ai-config-input", type: "number", min: 3, max: 60, value: connectionTimeout,
                onChange: (e) => this.setField("connectionTimeout", parseInt(e.target.value, 10) || 10)})
            )
          ),
          h("div", {className: "ai-config-field"},
            h("label", {className: "ai-config-field-label"}, "Retry Attempts"),
            h("span", {className: "ai-config-field-help"}, "Number of automatic retries for failed requests (0–5)."),
            h("input", {className: "ai-config-input", type: "number", min: 0, max: 5, value: retryAttempts, style: {maxWidth: "120px"},
              onChange: (e) => this.setField("retryAttempts", parseInt(e.target.value, 10) || 0)})
          ),
          h("div", {className: "ai-config-toggle-row"},
            h("div", null,
              h("div", {className: "ai-config-toggle-label"}, "Enable Streaming"),
              h("div", {className: "ai-config-toggle-desc"}, "Stream AI responses in real-time for faster perceived performance.")
            ),
            h("label", {className: "ai-config-toggle"},
              h("input", {type: "checkbox", checked: enableStreaming, onChange: (e) => this.setField("enableStreaming", e.target.checked)}),
              h("span", {className: "ai-config-toggle-track"})
            )
          ),
          h("div", {className: "ai-config-toggle-row"},
            h("div", null,
              h("div", {className: "ai-config-toggle-label"}, "Debug Logging"),
              h("div", {className: "ai-config-toggle-desc"}, "Log detailed request/response data to the browser console for troubleshooting.")
            ),
            h("label", {className: "ai-config-toggle"},
              h("input", {type: "checkbox", checked: debugLogging, onChange: (e) => this.setField("debugLogging", e.target.checked)}),
              h("span", {className: "ai-config-toggle-track"})
            )
          )
        )
      ),

      // Action Bar
      h("div", {className: "ai-config-actions"},
        h("div", {className: "ai-config-actions-left"},
          h("button", {className: "ai-config-btn ai-config-btn-danger", onClick: this.resetConfig}, "Reset"),
          h("button", {className: "ai-config-btn ai-config-btn-neutral", onClick: this.reconnect, disabled: isTesting || !backendUrl},
            isTesting ? h("span", {className: "ai-config-spinner dark"}) : null, "Reconnect")
        ),
        h("div", {className: "ai-config-actions-right"},
          h("button", {
            className: "ai-config-btn ai-config-btn-success",
            onClick: this.saveConfig,
            disabled: isSaving || !backendUrl || !apiKey,
          }, isSaving ? h("span", {className: "ai-config-spinner"}) : null, isSaving ? "Saving…" : "Save Configuration")
        )
      )
    );
  }
}

export default InspectorAiBackendConfig;
