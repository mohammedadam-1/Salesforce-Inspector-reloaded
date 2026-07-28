/* global React ReactDOM */
import * as backend from "./backend_service.js";

const h = React.createElement;

function getSfHost() {
  return new URLSearchParams(window.location.search).get("host") || "";
}
const sfHost = getSfHost();

function classNames(map) {
  return Object.entries(map).filter(([, v]) => v).map(([k]) => k).join(" ");
}

function markdownToHtml(text) {
  if (!text) return "";
  let html = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  html = html.replace(/^### (.+)$/gm, "<h4>$1</h4>");
  html = html.replace(/^## (.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^# (.+)$/gm, "<h2>$1</h2>");
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/^> (.*)$/gm, "<blockquote>$1</blockquote>");
  html = html.replace(/^- (.+)$/gm, "<li>$1</li>");
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
  html = html.replace(/\n\n/g, "</p><p>");
  html = html.replace(/\n/g, "<br>");
  return "<p>" + html + "</p>";
}

function Skeleton({width, height, rounded}) {
  return h("div", {
    className: "aicon-skeleton",
    style: {width: width || "100%", height: height || "16px", borderRadius: rounded || "6px"}
  });
}

function StatCard({icon, label, value, color}) {
  return h("div", {className: "aicon-stat-card"},
    h("div", {className: "aicon-stat-icon", style: {background: color || "var(--aicon-primary)"}},
      icon
    ),
    h("div", {className: "aicon-stat-body"},
      h("div", {className: "aicon-stat-value"}, value != null ? String(value) : h(Skeleton, {width: "40px"})),
      h("div", {className: "aicon-stat-label"}, label)
    )
  );
}

class App extends React.PureComponent {
  constructor(props) {
    super(props);
    this.state = {
      activeTab: "sync",
      backendReady: false,
      backendError: null,
      organizationId: localStorage.getItem(sfHost + "_backendOrgId") || "",
      syncStatus: "idle",
      syncProgress: 0,
      syncJobId: null,
      syncResult: null,
      syncError: null,
      syncLog: [],
      chatMessages: [],
      chatInput: "",
      chatLoading: false,
      chatError: null,
      conversationId: null,
      showCitations: false,
      citations: [],
      inspectQuery: "",
      inspectComponent: "",
      inspectResults: null,
      inspectLoading: false,
      inspectError: null,
    };
  }

  componentDidMount() {
    this.checkBackend();
  }

  checkBackend() {
    const ready = backend.isBackendConfigured();
    this.setState({
      backendReady: ready,
      backendError: ready ? null : "Backend not configured. Go to Options > Backend to set up.",
    });
  }

  setTab(tab) {
    this.setState({activeTab: tab});
  }

  setOrgId(val) {
    this.setState({organizationId: val});
    localStorage.setItem(sfHost + "_backendOrgId", val);
  }

  async triggerSync() {
    const {organizationId} = this.state;
    if (!organizationId) return this.setState({syncError: "Enter an Organization ID"});
    this.setState({
      syncStatus: "syncing",
      syncProgress: 0,
      syncError: null,
      syncResult: null,
      syncLog: ["Initiating metadata sync..."],
    });
    try {
      const data = await backend.triggerMetadataSync(organizationId);
      const jobId = data?.job_id || data?.task_id || null;
      this.setState({
        syncJobId: jobId,
        syncLog: prev => [...prev, `Sync job submitted${jobId ? ` (ID: ${jobId})` : ""}`],
      });
      if (jobId) {
        await this.pollSyncJob(jobId, organizationId);
      } else {
        this.setState({
          syncStatus: "completed",
          syncProgress: 100,
          syncLog: prev => [...prev, "Sync completed."],
        });
      }
    } catch (e) {
      this.setState({
        syncStatus: "error",
        syncError: e.message,
        syncLog: prev => [...prev, `Error: ${e.message}`],
      });
    }
  }

  getBackendConfig() {
    const url = localStorage.getItem("sfirBackendUrl");
    const apiKey = localStorage.getItem("sfirBackendApiKey");
    return url && apiKey ? {url, apiKey} : null;
  }

  async pollSyncJob(jobId, orgId) {
    const cfg = this.getBackendConfig();
    if (!cfg) return;
    const base = cfg.url.replace(/\/+$/, "");
    const url = `${base}/api/v1/sync/jobs/${jobId}?organization_id=${encodeURIComponent(orgId)}`;
    const poll = async () => {
      try {
        const resp = await fetch(url, {headers: {"X-API-Key": cfg.apiKey, "Accept": "application/json"}});
        if (!resp.ok) throw new Error(`Poll failed (${resp.status})`);
        const data = await resp.json();
        const status = (data?.status || data?.state || "").toLowerCase();
        const progress = data?.progress || data?.percentage || 0;
        this.setState({
          syncProgress: progress,
          syncLog: prev => {
            const msg = data?.message || `Progress: ${progress}%`;
            if (prev[prev.length - 1] !== msg) return [...prev, msg];
            return prev;
          },
        });
        if (status === "completed" || status === "success") {
          this.setState({
            syncStatus: "completed",
            syncProgress: 100,
            syncResult: data,
            syncLog: prev => [...prev, `Sync completed successfully. Total: ${data?.total_components || data?.total || "?"} components.`],
          });
          return;
        }
        if (status === "failed" || status === "error") {
          this.setState({
            syncStatus: "error",
            syncError: data?.error || data?.message || "Sync failed",
            syncLog: prev => [...prev, `Sync failed: ${data?.error || data?.message || "Unknown error"}`],
          });
          return;
        }
        setTimeout(poll, 2000);
      } catch (e) {
        this.setState({
          syncLog: prev => [...prev, `Poll error: ${e.message}`],
        });
        setTimeout(poll, 3000);
      }
    };
    setTimeout(poll, 1000);
  }

  async sendChat() {
    const {chatInput, chatMessages, organizationId, conversationId} = this.state;
    if (!organizationId) return this.setState({chatError: "Enter an Organization ID"});
    if (!chatInput.trim()) return;
    this.setState({chatLoading: true, chatError: null});
    const userMsg = {role: "user", content: chatInput.trim(), ts: Date.now()};
    const updated = [...chatMessages, userMsg];
    this.setState({chatMessages: updated, chatInput: ""});
    try {
      const data = await backend.aiChat(organizationId, chatInput, [], conversationId);
      const reply = data?.content || data?.response || data?.message || JSON.stringify(data);
      const newConvId = data?.conversation_id || conversationId;
      const cites = data?.citations || data?.references || [];
      this.setState({
        chatMessages: [...updated, {role: "assistant", content: reply, ts: Date.now()}],
        conversationId: newConvId,
        citations: cites,
        chatLoading: false,
      });
    } catch (e) {
      this.setState({
        chatMessages: [...updated, {role: "assistant", content: `Error: ${e.message}`, ts: Date.now(), isError: true}],
        chatLoading: false,
        chatError: e.message,
      });
    }
  }

  async analyzeComponent() {
    const {inspectComponent, organizationId} = this.state;
    if (!organizationId) return this.setState({inspectError: "Enter an Organization ID"});
    if (!inspectComponent.trim()) return;
    this.setState({inspectLoading: true, inspectError: null, inspectResults: null});
    try {
      const data = await backend.aiAnalyze(organizationId, `Explain and analyze this Salesforce component in detail: ${inspectComponent.trim()}`, inspectComponent.trim());
      this.setState({inspectResults: data, inspectLoading: false});
    } catch (e) {
      this.setState({inspectError: e.message, inspectLoading: false});
    }
  }

  renderTabBtn(name, label, icon) {
    const active = this.state.activeTab === name;
    return h("button", {
      className: classNames({"aicon-tab-btn": true, active}),
      onClick: () => this.setTab(name),
    }, icon ? h("span", {className: "aicon-tab-icon"}, icon) : null, label);
  }

  renderBackendBanner() {
    if (this.state.backendReady) return null;
    return h("div", {className: "aicon-banner aicon-banner-warning"},
      h("span", {className: "aicon-banner-icon"}, "!"),
      h("span", {}, this.state.backendError)
    );
  }

  renderError(err) {
    if (!err) return null;
    return h("div", {className: "aicon-banner aicon-banner-error"},
      h("span", {className: "aicon-banner-icon"}, "!"),
      h("span", {}, err)
    );
  }

  renderSyncTab() {
    const {syncStatus, syncProgress, syncLog, syncError, syncResult, organizationId} = this.state;
    const isSyncing = syncStatus === "syncing";
    return h("div", {className: "aicon-tab-pane"},
      h("div", {className: "aicon-card aicon-glass"},
        h("div", {className: "aicon-card-header"},
          h("div", {className: "aicon-card-title"},
            h("span", {className: "aicon-status-dot", style: {background: this.state.backendReady ? "var(--aicon-success)" : "var(--aicon-warning)"}}),
            " Backend Status"
          ),
          h("span", {className: "aicon-badge", style: {background: this.state.backendReady ? "var(--aicon-success)" : "var(--aicon-warning)"}},
            this.state.backendReady ? "Connected" : "Disconnected"
          )
        ),
        h("div", {className: "aicon-card-body"},
          h("div", {className: "aicon-form-row"},
            h("label", {className: "aicon-label"}, "Organization ID"),
            h("input", {
              className: "aicon-input",
              type: "text",
              value: organizationId,
              placeholder: "00D... or your Salesforce Org ID",
              onChange: e => this.setOrgId(e.target.value),
              disabled: isSyncing,
            })
          ),
          h("div", {className: "aicon-form-row"},
            h("button", {
              className: classNames({"aicon-btn aicon-btn-primary": true, "aicon-btn-loading": isSyncing}),
              onClick: () => this.triggerSync(),
              disabled: isSyncing || !organizationId || !this.state.backendReady,
            }, isSyncing ? "Syncing..." : "Trigger Full Sync")
          )
        )
      ),
      isSyncing ? h("div", {className: "aicon-progress-container"},
        h("div", {className: "aicon-progress-bar", style: {width: syncProgress + "%"}}),
        h("span", {className: "aicon-progress-label"}, `${syncProgress}%`)
      ) : null,
      this.renderError(syncError),
      h("div", {className: "aicon-stats-grid"},
        h(StatCard, {icon: "S", label: "Components", value: syncResult?.total_components || syncResult?.total, color: "var(--aicon-primary)"}),
        h(StatCard, {icon: "T", label: "Types", value: syncResult?.types_count || syncResult?.type_count, color: "var(--aicon-info)"}),
        h(StatCard, {icon: "O", label: "Org ID", value: organizationId ? organizationId.substring(0, 10) + "..." : null, color: "var(--aicon-success)"}),
        h(StatCard, {icon: "!", label: "Errors", value: syncResult?.error_count || 0, color: syncResult?.error_count > 0 ? "var(--aicon-danger)" : "var(--aicon-muted)"})
      ),
      syncLog.length > 0 ? h("div", {className: "aicon-log"},
        h("div", {className: "aicon-log-title"}, "Activity Log"),
        h("div", {className: "aicon-log-list"},
          syncLog.map((msg, i) => h("div", {key: i, className: "aicon-log-item"},
            h("span", {className: "aicon-log-time"}, new Date(Date.now() - (syncLog.length - i) * 1000).toLocaleTimeString()),
            h("span", {className: "aicon-log-msg"}, msg)
          ))
        )
      ) : null
    );
  }

  renderChatTab() {
    const {chatMessages, chatInput, chatLoading, chatError, citations, showCitations} = this.state;
    return h("div", {className: "aicon-tab-pane aicon-chat-pane"},
      h("div", {className: "aicon-chat-feed"},
        chatMessages.length === 0
          ? h("div", {className: "aicon-chat-empty"},
              h("div", {className: "aicon-chat-empty-icon"}, "AI"),
              h("div", {className: "aicon-chat-empty-text"}, "Ask questions about your Salesforce metadata using natural language."),
              h("div", {className: "aicon-chat-suggestions"},
                ["Where is Account.Industry__c used?", "What depends on the Opportunity object?", "What breaks if I remove Product2?", "Explain the flow 'Opportunity_Stage_Update'", "Find all unused Apex classes"].map((s, i) =>
                  h("button", {
                    key: i,
                    className: "aicon-chip",
                    onClick: () => this.setState({chatInput: s}),
                  }, s)
                )
              )
            )
          : chatMessages.map((msg, i) =>
              h("div", {
                key: i,
                className: classNames({"aicon-msg": true, "aicon-msg-user": msg.role === "user", "aicon-msg-ai": msg.role === "assistant", "aicon-msg-error": msg.isError}),
              },
                h("div", {className: "aicon-msg-avatar"},
                  msg.role === "user" ? "U" : "AI"
                ),
                h("div", {className: "aicon-msg-content"},
                  h("div", {
                    className: "aicon-msg-bubble",
                    dangerouslySetInnerHTML: {__html: markdownToHtml(msg.content)},
                  }),
                  msg.role === "assistant" && !msg.isError && citations.length > 0
                    ? h("div", {className: "aicon-citation-bar"},
                        h("button", {
                          className: "aicon-chip aicon-chip-small",
                          onClick: () => this.setState({showCitations: !showCitations}),
                        }, `Citations (${citations.length})`)
                      )
                    : null
                )
              )
            ),
        chatLoading ? h("div", {className: "aicon-msg aicon-msg-ai"},
          h("div", {className: "aicon-msg-avatar"}, "AI"),
          h("div", {className: "aicon-msg-content"},
            h("div", {className: "aicon-typing"},
              h("span", {className: "aicon-typing-dot"}),
              h("span", {className: "aicon-typing-dot"}),
              h("span", {className: "aicon-typing-dot"})
            )
          )
        ) : null,
        this.renderError(chatError)
      ),
      showCitations && citations.length > 0 ? h("div", {className: "aicon-citations-drawer"},
        h("div", {className: "aicon-citations-header"},
          h("span", {}, "Citations"),
          h("button", {className: "aicon-chip aicon-chip-small", onClick: () => this.setState({showCitations: false})}, "Close")
        ),
        citations.map((c, i) =>
          h("div", {key: i, className: "aicon-citation-item"},
            h("span", {className: "aicon-citation-num"}, i + 1),
            h("div", {},
              h("div", {className: "aicon-citation-title"}, c.title || c.name || `Source ${i + 1}`),
              h("div", {className: "aicon-citation-detail"}, c.type || c.component_type || "")
            )
          )
        )
      ) : null,
      h("div", {className: "aicon-chat-input"},
        h("input", {
          className: "aicon-input",
          type: "text",
          value: chatInput,
          placeholder: "Ask a question about your metadata...",
          onChange: e => this.setState({chatInput: e.target.value}),
          onKeyDown: e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); this.sendChat(); }},
          disabled: chatLoading,
        }),
        h("button", {
          className: classNames({"aicon-btn aicon-btn-primary aicon-btn-icon": true, "aicon-btn-loading": chatLoading}),
          onClick: () => this.sendChat(),
          disabled: chatLoading || !chatInput.trim(),
        }, "Send")
      )
    );
  }

  renderInspectTab() {
    const {inspectComponent, inspectQuery, inspectResults, inspectLoading, inspectError} = this.state;
    return h("div", {className: "aicon-tab-pane"},
      h("div", {className: "aicon-card aicon-glass"},
        h("div", {className: "aicon-card-header"},
          h("div", {className: "aicon-card-title"}, "Component Analyzer")
        ),
        h("div", {className: "aicon-card-body"},
          h("div", {className: "aicon-form-row"},
            h("label", {className: "aicon-label"}, "Component Key"),
            h("input", {
              className: "aicon-input",
              type: "text",
              value: inspectComponent,
              placeholder: "e.g. ApexClass:MyController or Flow:MyFlow",
              onChange: e => this.setState({inspectComponent: e.target.value}),
              onKeyDown: e => { if (e.key === "Enter") this.analyzeComponent(); },
              disabled: inspectLoading,
            })
          ),
          h("div", {className: "aicon-form-row"},
            h("label", {className: "aicon-label"}, "Optional Prompt"),
            h("textarea", {
              className: "aicon-input aicon-textarea",
              value: inspectQuery,
              placeholder: "What would you like to know? (default: full analysis)",
              onChange: e => this.setState({inspectQuery: e.target.value}),
              rows: 2,
              disabled: inspectLoading,
            })
          ),
          h("button", {
            className: classNames({"aicon-btn aicon-btn-primary": true, "aicon-btn-loading": inspectLoading}),
            onClick: () => this.analyzeComponent(),
            disabled: inspectLoading || !inspectComponent.trim(),
          }, inspectLoading ? "Analyzing..." : "Analyze Component")
        )
      ),
      this.renderError(inspectError),
      inspectResults ? h("div", {className: "aicon-card aicon-glass aicon-result-card"},
        h("div", {className: "aicon-card-header"},
          h("div", {className: "aicon-card-title"}, "Analysis Results")
        ),
        h("div", {className: "aicon-card-body aicon-result-body",
          dangerouslySetInnerHTML: {__html: markdownToHtml(inspectResults.content || inspectResults.response || JSON.stringify(inspectResults, null, 2))}
        })
      ) : null,
      !inspectResults && !inspectLoading ? h("div", {className: "aicon-card aicon-glass aicon-tip-card"},
        h("div", {className: "aicon-card-body"},
          "Enter a component key to get an AI-powered analysis including its purpose, dependencies, risks, and recommendations."
        )
      ) : null
    );
  }

  render() {
    const {activeTab} = this.state;
    return h("div", {className: "aicon slds-scope"},
      h("div", {className: "aicon-header"},
        h("h1", {className: "aicon-title"}, "AI Console")
      ),
      this.renderBackendBanner(),
      h("div", {className: "aicon-tabs"},
        this.renderTabBtn("sync", "Sync Dashboard", "S"),
        this.renderTabBtn("chat", "Chatbot", "C"),
        this.renderTabBtn("inspect", "Component Inspect", "I")
      ),
      h("div", {className: "aicon-body"},
        activeTab === "sync" ? this.renderSyncTab() : null,
        activeTab === "chat" ? this.renderChatTab() : null,
        activeTab === "inspect" ? this.renderInspectTab() : null,
      )
    );
  }
}

ReactDOM.render(h(App), document.getElementById("root"));
