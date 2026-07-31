/* eslint-disable react/no-deprecated */
/* global React ReactDOM */
import ChatState from "./state/chatState.js";
import ConversationState from "./state/conversationState.js";
import CitationChips from "./components/CitationChips.js";
import ConfidenceBadge from "./components/ConfidenceBadge.js";
import NextActionsPanel from "./components/NextActionsPanel.js";
import ContextPanel from "./components/ContextPanel.js";
import ChatController from "./controllers/ChatController.js";
import ConversationController from "./controllers/ConversationController.js";
import ContextController from "./controllers/ContextController.js";
import SettingsController from "./controllers/SettingsController.js";
import ConversationList from "../../components/ConversationList.js";
import ToolExecutionPanel from "../../components/ToolExecutionPanel.js";
import MarkdownRenderer from "../../components/MarkdownRenderer.js";
import {isConfigured, getConnectionStatus, onConnectionChange, startHealthMonitor, stopHealthMonitor} from "../../services/aiApiClient.js";

const h = React.createElement;

function formatTime(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  return d.toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"});
}

const FEATURES = [
  {id: "explain-apex", icon: "code", tone: "blue", title: "Explain Apex", desc: "Translate classes, triggers, tests, and patterns into clear engineering guidance."},
  {id: "metadata-analysis", icon: "search", tone: "teal", title: "Metadata Analysis", desc: "Inspect fields, objects, flows, layouts, and automation with org-aware context."},
  {id: "dependency-analysis", icon: "share", tone: "green", title: "Dependency Analysis", desc: "Trace references and downstream consumers before you change Salesforce assets."},
  {id: "deployment-impact", icon: "layers", tone: "amber", title: "Deployment Impact", desc: "Assess release risk, blast radius, and validation needs before deployment."},
  {id: "doc-generator", icon: "file-text", tone: "violet", title: "Documentation Generator", desc: "Create concise technical documentation for Apex, Flow, metadata, and integrations."},
  {id: "soql-generator", icon: "database", tone: "indigo", title: "SOQL Generator", desc: "Generate focused SOQL from natural language and refine it for real org data."},
  {id: "security-review", icon: "shield", tone: "rose", title: "Security Review", desc: "Review sharing, CRUD/FLS, risky automation, and implementation gaps."},
];

const EXAMPLE_PROMPTS = [
  "Where is Account.Name used?",
  "Explain this Apex class.",
  "Generate documentation.",
  "Can I safely delete this field?",
  "Find every Flow using Opportunity.",
];

const SETUP_STEPS = [
  "Open AI Settings",
  "Enter Backend URL",
  "Enter API Key",
  "Save",
  "Return here",
];

function SparkleIcon({className}) {
  return h("svg", {className: className || "", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "1.5", strokeLinecap: "round", strokeLinejoin: "round"},
    h("path", {d: "M12 3l1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5z"}),
    h("path", {d: "M5 18l2-1 2 1-2 1z"}),
    h("path", {d: "M17 16l2-1 2 1-2 1z"})
  );
}

function FeatureIcon({id}) {
  const paths = {
    code: "M16 18l6-6-6-6M8 6l-6 6 6 6",
    search: "M21 21l-4.35-4.35M11 19a8 8 0 100-16 8 8 0 000 16z",
    share: "M4 12v7a2 2 0 002 2h12a2 2 0 002-2v-7M16 6l-4-4-4 4M12 2v13",
    layers: "M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5",
    "file-text": "M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6zM14 2v6h6M16 13H8M16 17H8M10 9H8",
    database: "M12 8c-4.42 0-8-1.79-8-4s3.58-4 8-4 8 1.79 8 4-3.58 4-8 4zM4 12c0 2.21 3.58 4 8 4s8-1.79 8-4M4 16c0 2.21 3.58 4 8 4s8-1.79 8-4",
    shield: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
  };
  return h("svg", {className: "ai-feature-svg", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", strokeLinecap: "round", strokeLinejoin: "round"},
    h("path", {d: paths[id] || paths.search})
  );
}

function StatusPill({status}) {
  const labels = {
    connected: "Connected",
    reconnecting: "Reconnecting",
    offline: "Offline",
    error: "Action needed",
    configuring: "Configuring",
    unknown: "Checking",
  };
  return h("span", {className: "ai-status-pill ai-status-pill-" + (status || "unknown")},
    h("span", {className: "ai-status-dot ai-status-" + (status || "unknown")}),
    labels[status] || "Checking"
  );
}

class InspectorAiApp extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      chat: ChatState.getState(),
      conversations: ConversationState.getState(),
      sfContext: null,
      connectionStatus: getConnectionStatus(),
      inputText: "",
      sidebarOpen: true,
    };
    this._mounted = false;
    this._unsubChat = null;
    this._unsubConv = null;
    this._unsubCtx = null;
    this._unsubConn = null;

    this.handleSend = this.handleSend.bind(this);
    this.handleAction = this.handleAction.bind(this);
    this.handleKeyDown = this.handleKeyDown.bind(this);
    this.openOptions = this.openOptions.bind(this);
  }

  componentDidMount() {
    this._unsubChat = ChatState.subscribe((state) => {
      if (this._mounted) this.setState({chat: state});
    });
    this._unsubConv = ConversationState.subscribe((state) => {
      if (this._mounted) this.setState({conversations: state});
    });
    this._unsubConn = onConnectionChange((status) => {
      if (this._mounted) this.setState({connectionStatus: status});
    });
    ContextController.init();
    this.setState({sfContext: ContextController.context});
    this._unsubCtx = ContextController.subscribe((ctx) => {
      if (this._mounted) this.setState({sfContext: ctx});
    });
    ConversationController.init();
    startHealthMonitor();
    this._mounted = true;
  }

  componentWillUnmount() {
    this._mounted = false;
    if (this._unsubChat) this._unsubChat();
    if (this._unsubConv) this._unsubConv();
    if (this._unsubCtx) this._unsubCtx();
    if (this._unsubConn) this._unsubConn();
    stopHealthMonitor();
  }

  handleSend(text) {
    const input = text || this.state.inputText.trim();
    if (!input) return;
    this.setState({inputText: ""});
    if (!isConfigured()) return;
    ChatController.sendMessage(input, this.state.sfContext);
  }

  handleAction(action) {
    if (action.type === "query" && action.payload) {
      this.setState({inputText: action.payload}, () => this.handleSend());
    } else if (action.type === "navigate" && action.url) {
      if (window.openInTab) window.openInTab(action.url);
    } else if (action.type === "analyze" && action.prompt) {
      this.setState({inputText: action.prompt}, () => this.handleSend());
    } else if (action.type === "execute" && action.command) {
      this.setState({inputText: action.command}, () => this.handleSend());
    }
  }

  handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      this.handleSend();
    }
    if (e.key === "Escape") {
      e.target.blur();
    }
  }

  openOptions() {
    const host = this.state.sfContext?.sfHost || "";
    const selectedTab = "inspector-ai-backend";
    const url = chrome.runtime.getURL("options.html?host=" + encodeURIComponent(host) + "&selectedTab=" + selectedTab);
    chrome.tabs.create({url});
  }

  renderMessage(msg, idx) {
    const isUser = msg.role === "user";
    const isStreaming = msg.isStreaming;
    return h("div", {key: msg.timestamp || idx, className: "ai-msg " + (isUser ? "ai-msg-user" : "ai-msg-result")},
      h("div", {className: "slds-card"},
        h("div", {className: "slds-card__header slds-card__header_inner"},
          h("div", {className: "slds-media slds-media_center slds-has-flexi-truncate"},
            h("div", {className: "slds-media__figure"},
              h("span", {className: "slds-icon_container slds-icon-standard-" + (isUser ? "user" : "record_lookup")},
                h("svg", {className: "slds-icon slds-icon_small", "aria-hidden": "true"},
                  isUser
                    ? h("use", {xlinkHref: "../../symbols.svg#user"})
                    : h("use", {xlinkHref: "../../symbols.svg#record_lookup"})
                )
              )
            ),
            h("div", {className: "slds-media__body"},
              h("h3", {className: "slds-text-heading_small"}, isUser ? "Query" : "Analysis Result"),
              h("span", {className: "slds-text-body_small slds-text-color_weak"}, formatTime(msg.timestamp || msg.time))
            )
          ),
          isStreaming && h("div", {className: "slds-spinner slds-spinner_x-small slds-spinner_inline", role: "status"},
            h("span", {className: "slds-assistive-text"}, "Generating"),
            h("div", {className: "slds-spinner__dot-a"}),
            h("div", {className: "slds-spinner__dot-b"})
          )
        ),
        h("div", {className: "slds-card__body slds-card__body_inner"},
          isUser
            ? h("div", {className: "slds-text-body_regular"}, msg.content)
            : h(MarkdownRenderer, {content: msg.content})
        ),
        !isUser ? h("div", {className: "slds-card__footer slds-grid slds-wrap slds-gutters"},
          msg.confidence ? h("div", {className: "slds-col"},
            h(ConfidenceBadge, {confidence: msg.confidence})
          ) : null,
          msg.citations && msg.citations.length > 0 ? h("div", {className: "slds-col slds-size_1-of-1 slds-m-top_x-small"},
            h(CitationChips, {citations: msg.citations})
          ) : null,
          msg.suggestedActions && msg.suggestedActions.length > 0 ? h("div", {className: "slds-col slds-size_1-of-1 slds-m-top_x-small"},
            h(NextActionsPanel, {actions: msg.suggestedActions, onAction: this.handleAction})
          ) : null
        ) : null
      )
    );
  }

  renderWelcomeScreen() {
    if (isConfigured()) return null;
    return h("div", {className: "ai-welcome"},
      h("section", {className: "ai-welcome-hero"},
        h("div", {className: "ai-welcome-hero-content"},
          h("div", {className: "ai-brand-lockup"},
            h("div", {className: "ai-logo-mark ai-logo-mark-large"},
              h(SparkleIcon, {className: "ai-logo-icon"})
            ),
            h("div", null,
              h("h1", {className: "ai-welcome-title"}, "Inspector AI"),
              h("p", {className: "ai-welcome-subtitle"}, "Your AI Engineering Assistant for Salesforce")
            )
          ),
          h("p", {className: "ai-welcome-lede"},
            "A premium engineering workspace for understanding org metadata, reasoning through change impact, and turning Salesforce questions into actionable implementation steps."
          ),
          h("div", {className: "ai-welcome-actions"},
            h("button", {
              className: "slds-button slds-button_brand ai-primary-action",
              onClick: this.openOptions,
            }, "Configure Inspector AI"),
            h("span", {className: "ai-hero-note"}, "Open AI Settings, connect your backend, then return here to start working.")
          )
        )
      ),
      h("div", {className: "ai-welcome-body"},
        h("section", {className: "ai-intro-grid"},
          h("div", {className: "ai-value-panel"},
            h("span", {className: "ai-section-kicker"}, "Enterprise AI Copilot"),
            h("h2", {className: "ai-section-title"}, "Move from org questions to confident engineering decisions."),
            h("p", {className: "ai-welcome-desc"},
              "Inspector AI brings intelligent analysis to your Salesforce org. Ask questions about metadata, analyze dependencies, assess deployment impact, generate documentation, draft SOQL, and review security from one focused workspace."
            ),
            h("div", {className: "ai-value-metrics"},
              h("div", {className: "ai-value-metric"}, h("strong", null, "Org-aware"), h("span", null, "Salesforce context")),
              h("div", {className: "ai-value-metric"}, h("strong", null, "Actionable"), h("span", null, "Next steps")),
              h("div", {className: "ai-value-metric"}, h("strong", null, "Traceable"), h("span", null, "Citations"))
            )
          ),
          h("div", {className: "ai-setup-panel"},
            h("div", {className: "ai-panel-heading-row"},
              h("span", {className: "ai-section-kicker"}, "Setup Guide"),
              h("span", {className: "ai-setup-time"}, "5 steps")
            ),
            h("ol", {className: "ai-setup-steps"},
              SETUP_STEPS.map((text, i) =>
                h("li", {key: text, className: "ai-setup-step"},
                  h("span", {className: "ai-setup-step-num"}, String(i + 1)),
                  h("span", {className: "ai-setup-step-text"}, text)
                )
              )
            ),
            h("button", {
              className: "slds-button slds-button_brand ai-setup-button",
              onClick: this.openOptions,
            }, "Configure Inspector AI")
          )
        ),
        h("section", {className: "ai-welcome-section"},
          h("div", {className: "ai-section-header"},
            h("span", {className: "ai-section-kicker"}, "Quick Capabilities"),
            h("h2", {className: "ai-section-title"}, "Built for Salesforce engineering work")
          ),
          h("div", {className: "ai-feature-grid"},
            FEATURES.map((f) =>
              h("article", {key: f.id, className: "slds-card ai-feature-card ai-feature-tone-" + f.tone},
                h("div", {className: "ai-feature-card-icon"},
                  h(FeatureIcon, {id: f.icon})
                ),
                h("div", {className: "ai-feature-card-body"},
                  h("h3", {className: "ai-feature-card-title"}, f.title),
                  h("p", {className: "ai-feature-card-desc"}, f.desc)
                )
              )
            )
          )
        ),
        h("section", {className: "ai-welcome-section ai-prompt-panel"},
          h("div", {className: "ai-section-header ai-section-header-inline"},
            h("div", null,
              h("span", {className: "ai-section-kicker"}, "Example Prompts"),
              h("h2", {className: "ai-section-title"}, "Start with the questions teams already ask")
            ),
            h("button", {
              className: "slds-button slds-button_neutral ai-secondary-action",
              onClick: this.openOptions,
            }, "Open AI Settings")
          ),
          h("div", {className: "ai-prompt-grid ai-prompt-grid-premium"},
            EXAMPLE_PROMPTS.map((p) =>
              h("button", {
                key: p,
                className: "ai-prompt-chip",
                onClick: this.openOptions,
                title: "Configure Inspector AI to ask: " + p,
              },
              h("span", {className: "ai-prompt-bullet"}, "+"),
              h("span", null, p)
              )
            )
          )
        )
      )
    );
  }

  renderQuickActions() {
    return h("div", {className: "ai-empty-state ai-empty-state-premium"},
      h("div", {className: "ai-empty-content"},
        h("div", {className: "ai-empty-hero-row"},
          h("div", {className: "ai-logo-mark"},
            h(SparkleIcon, {className: "ai-logo-icon"})
          ),
          h("div", {className: "ai-empty-copy"},
            h("span", {className: "ai-section-kicker"}, "Inspector AI Workspace"),
            h("h2", {className: "ai-empty-title"}, "What Salesforce engineering question should we solve first?"),
            h("p", {className: "ai-empty-desc"},
              "Ask for analysis, impact, documentation, query help, or a review of the current Salesforce context."
            )
          )
        ),
        h("div", {className: "ai-empty-grid"},
          h("section", {className: "ai-empty-panel"},
            h("h3", {className: "ai-empty-section-title"}, "Example Prompts"),
            h("div", {className: "ai-prompt-grid"},
              EXAMPLE_PROMPTS.map((p) =>
                h("button", {
                  key: p,
                  className: "ai-prompt-chip",
                  onClick: () => this.handleSend(p),
                },
                h("span", {className: "ai-prompt-bullet"}, "+"),
                h("span", null, p)
                )
              )
            )
          ),
          h("section", {className: "ai-empty-panel"},
            h("h3", {className: "ai-empty-section-title"}, "Quick Capabilities"),
            h("div", {className: "ai-feature-grid ai-feature-grid-sm"},
              FEATURES.map((f) =>
                h("button", {
                  key: f.id,
                  className: "ai-feature-card ai-feature-card-sm ai-feature-tone-" + f.tone,
                  onClick: () => this.handleSend(f.title),
                },
                h("span", {className: "ai-feature-card-icon"},
                  h(FeatureIcon, {id: f.icon})
                ),
                h("span", {className: "ai-feature-card-body"},
                  h("span", {className: "ai-feature-card-title"}, f.title)
                )
                )
              )
            )
          )
        )
      )
    );
  }

  render() {
    const {chat, sfContext, connectionStatus} = this.state;
    const {messages, isStreaming, streamingMessage, error, isProcessing, toolExecutions} = chat;
    const isLoading = false;
    const showTimeline = SettingsController.showTimeline && toolExecutions.length > 0;
    const isUnconfigured = !isConfigured();
    const hasMessages = messages.length > 0;
    const hasContext = sfContext && (sfContext.orgName || sfContext.sfHost);

    return h("div", {className: "ai-page-scope"},
      h("div", {className: "ai-header-shell"},
        h("header", {className: "ai-command-header"},
          h("div", {className: "ai-command-brand"},
            h("div", {className: "ai-logo-mark ai-logo-mark-header"},
              h(SparkleIcon, {className: "ai-logo-icon"})
            ),
            h("div", {className: "ai-command-title-wrap"},
              h("div", {className: "ai-command-title"}, "Inspector AI"),
              h("div", {className: "ai-command-subtitle"}, sfContext?.orgName || "Salesforce engineering copilot")
            )
          ),
          h("div", {className: "ai-command-actions"},
            !isConfigured() ? null : h(StatusPill, {status: connectionStatus}),
            isConfigured() ? h("button", {
              className: "slds-button slds-button_neutral ai-header-button",
              onClick: () => ChatController.clearChat(),
              title: "Clear results",
            },
            h("span", {className: "ai-button-icon", "aria-hidden": "true"}, "x"),
            h("span", null, "Clear")
            ) : null,
            h("button", {
              className: "slds-button slds-button_neutral ai-header-button",
              onClick: this.openOptions,
            },
            h("span", {className: "ai-button-icon", "aria-hidden": "true"}, "*"),
            h("span", null, "Settings")
            )
          )
        )
      ),
      h("div", {className: "ai-workspace-body"},
        isUnconfigured ? this.renderWelcomeScreen()
        : h("div", {className: "ai-workspace-layout"},
          this.state.sidebarOpen ? h("aside", {className: "ai-sidebar"},
            h("div", {className: "ai-sidebar-header"},
              h("div", null,
                h("span", {className: "ai-sidebar-title"}, "Workspace History"),
                h("span", {className: "ai-sidebar-subtitle"}, "Recent AI sessions")
              ),
              h("button", {
                className: "slds-button slds-button_icon slds-button_icon-border slds-button_icon-x-small ai-icon-button",
                onClick: () => this.setState({sidebarOpen: false}),
                title: "Close sidebar",
              },
              h("svg", {className: "slds-button__icon", "aria-hidden": "true", viewBox: "0 0 24 24", width: "14", height: "14"},
                h("path", {d: "M18 6L6 18M6 6l12 12", fill: "none", stroke: "currentColor", strokeWidth: "2"})
              )
              )
            ),
            h("div", {className: "ai-sidebar-list"},
              h(ConversationList, {
                conversations: this.state.conversations.conversations,
                activeId: this.state.conversations.activeId,
                onSelect: (id) => ConversationController.selectConversation(id),
                onDelete: (id) => ConversationController.deleteConversation(id),
                onRename: (id, title) => ConversationController.renameConversation(id, title),
                isLoading: this.state.conversations.isLoading,
              })
            ),
            h("div", {className: "ai-sidebar-footer"},
              h("button", {
                className: "slds-button slds-button_neutral ai-new-conversation-button",
                onClick: () => ConversationController.createConversation("New Conversation", sfContext),
              }, "+ New Conversation")
            )
          ) : null,
          h("main", {className: "ai-workspace-content"},
            h("div", {className: "ai-workspace-toolbar"},
              this.state.sidebarOpen ? null
              : h("button", {
                className: "slds-button slds-button_icon slds-button_icon-border slds-button_icon-x-small ai-icon-button",
                onClick: () => this.setState({sidebarOpen: true}),
                title: "Show history",
              },
              h("svg", {className: "slds-button__icon", "aria-hidden": "true", viewBox: "0 0 24 24", width: "14", height: "14"},
                h("path", {d: "M4 6h16M4 12h16M4 18h16", fill: "none", stroke: "currentColor", strokeWidth: "2"})
              )
              ),
              h("div", {className: "ai-toolbar-copy"},
                h("span", {className: "ai-toolbar-kicker"}, "Live Context"),
                hasContext ? h(ContextPanel, {
                  context: sfContext,
                  isLoading,
                  onRefresh: () => ContextController.refresh(),
                }) : h("span", {className: "slds-text-body_small slds-text-color_weak"}, "No Salesforce context")
              )
            ),
            h("div", {className: "ai-results-area"},
              !hasMessages && !isProcessing && !error
                ? this.renderQuickActions()
                : null,
              error ? h("div", {className: "slds-card slds-m-bottom_x-small slds-theme_error"},
                h("div", {className: "slds-card__body slds-card__body_inner slds-p-around_medium"},
                  h("div", {className: "slds-grid slds-grid_vertical-align-center"},
                    h("div", {className: "slds-col slds-size_2-of-3"},
                      h("h3", {className: "slds-text-heading_small"}, "Error"),
                      h("p", {className: "slds-text-body_small"}, error)
                    ),
                    h("div", {className: "slds-col slds-size_1-of-3 slds-text-align_right"},
                      h("button", {className: "slds-button slds-button_neutral ai-compact-button", onClick: () => ChatController.retry()}, "Retry"),
                      h("button", {className: "slds-button slds-button_neutral ai-compact-button", onClick: () => ChatState.clearError()}, "Dismiss")
                    )
                  )
                )
              ) : null,
              hasMessages ? messages.map((msg, idx) => this.renderMessage(msg, idx)) : null,
              isStreaming && streamingMessage && messages.indexOf(streamingMessage) === -1
                ? h("div", {key: "streaming", className: "ai-msg ai-msg-result"},
                  h("div", {className: "slds-card"},
                    h("div", {className: "slds-card__header slds-card__header_inner"},
                      h("div", {className: "slds-media slds-media_center"},
                        h("div", {className: "slds-media__figure"},
                          h("div", {className: "slds-spinner slds-spinner_x-small slds-spinner_inline", role: "status"},
                            h("span", {className: "slds-assistive-text"}, "Generating"),
                            h("div", {className: "slds-spinner__dot-a"}),
                            h("div", {className: "slds-spinner__dot-b"})
                          )
                        ),
                        h("div", {className: "slds-media__body"},
                          h("h3", {className: "slds-text-heading_small"}, "Generating Analysis...")
                        )
                      )
                    ),
                    h("div", {className: "slds-card__body slds-card__body_inner"},
                      h(MarkdownRenderer, {content: streamingMessage.content || ""})
                    )
                  )
                )
                : null,
              showTimeline ? h("div", {className: "ai-timeline-card"},
                h("div", {className: "ai-timeline-header"},
                  h("span", {className: "ai-timeline-title"}, "Tool Executions"),
                  h("span", {className: "ai-badge-count"}, toolExecutions.length)
                ),
                h(ToolExecutionPanel, {executions: toolExecutions})
              ) : null
            ),
            h("div", {className: "ai-input-section"},
              h("div", {className: "ai-input-shell"},
                h("textarea", {
                  className: "slds-textarea ai-query-input",
                  placeholder: isProcessing ? "Processing..." : "Ask Inspector AI about Apex, metadata, dependencies, deployments, SOQL, or security...",
                  value: this.state.inputText,
                  onChange: (e) => this.setState({inputText: e.target.value}),
                  onKeyDown: this.handleKeyDown,
                  disabled: isProcessing || isStreaming,
                  rows: 1,
                }),
                h("button", {
                  className: "slds-button slds-button_brand ai-send-button",
                  onClick: this.handleSend,
                  disabled: isProcessing || isStreaming || !this.state.inputText.trim(),
                }, isProcessing ? "Processing" : "Analyze")
              )
            )
          )
        )
      )
    );
  }
}

export default InspectorAiApp;

const root = document.getElementById("ai-workspace-root");
if (root) {
  ReactDOM.render(h(InspectorAiApp), root);
}
