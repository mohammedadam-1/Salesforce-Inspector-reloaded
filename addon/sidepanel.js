/* global React ReactDOM */
import PanelHeader from "./components/PanelHeader.js";
import ContextBar from "./components/ContextBar.js";
import ChatMessage from "./components/ChatMessage.js";
import ChatInput from "./components/ChatInput.js";
import QuickActions from "./components/QuickActions.js";
import EmptyState from "./components/EmptyState.js";
import ErrorState from "./components/ErrorState.js";
import OrgSwitcher from "./components/OrgSwitcher.js";
import ConversationList from "./components/ConversationList.js";
import { health, chat, streamChat, getCapabilities, isConfigured, getConnectionStatus, onConnectionChange, startHealthMonitor, stopHealthMonitor } from "./services/aiApiClient.js";
import * as conv from "./services/conversationService.js";

const h = React.createElement;

const INITIAL_SUGGESTIONS = [
  "Explain this page",
  "Find dependencies",
  "Generate documentation",
  "Impact analysis",
  "Schema overview",
];

function statusToOrgStatus(status) {
  if (status === "connected") return "connected";
  if (status === "reconnecting" || status === "configuring") return "pending";
  return "disconnected";
}

function parseStreamChunk(chunk, handlers) {
  const { onToken, onMeta, onToolStart, onToolProgress, onToolComplete, onToolFailed, onCitation, onReasoning } = handlers;

  const lines = chunk.split("\n");
  let currentEvent = "";

  for (const raw of lines) {
    if (raw.startsWith("event: ")) {
      currentEvent = raw.slice(7).trim();
    } else if (raw.startsWith("data: ")) {
      const payload = raw.slice(6);
      let data;
      try { data = JSON.parse(payload); } catch (e) { data = payload; }

      if (currentEvent === "tool_start" && onToolStart) {
        onToolStart(data);
      } else if (currentEvent === "tool_progress" && onToolProgress) {
        onToolProgress(data);
      } else if (currentEvent === "tool_complete" && onToolComplete) {
        onToolComplete(data);
      } else if (currentEvent === "tool_failed" && onToolFailed) {
        onToolFailed(data);
      } else if (currentEvent === "citation" && onCitation) {
        onCitation(data);
      } else if (currentEvent === "reasoning" && onReasoning) {
        onReasoning(data);
      } else if (currentEvent === "token") {
        const t = typeof data === "object" ? (data.token || data.content || data.text || "") : data;
        if (t && onToken) onToken(t);
      } else if (currentEvent === "done") {
        if (onMeta) onMeta("meta", data);
      } else if (currentEvent === "error") {
        if (onMeta) onMeta("error", data);
      } else if (!currentEvent || currentEvent === "message") {
        const token = typeof data === "object" ? (data.token || data.content || data.text || data.message || "") : data;
        if (token && token !== "") {
          if (onToken) onToken(token);
        } else if (data?.conversation_id || data?.event === "done" || data?.type === "done") {
          if (onMeta) onMeta("meta", data);
        } else if (data?.event === "error" || data?.type === "error") {
          if (onMeta) onMeta("error", data);
        } else {
          if (onMeta) onMeta("meta", data);
        }
      }
      currentEvent = "";
    }
    if (raw === "") currentEvent = "";
  }
}

class SidePanelApp extends React.PureComponent {
  constructor(props) {
    super(props);
    this.state = {
      messages: conv.getActiveMessages(),
      isStreaming: false,
      showContext: false,
      showConversations: false,
      showOrgSwitcher: false,
      connectionStatus: getConnectionStatus(),
      orgName: null,
      quickActions: INITIAL_SUGGESTIONS,
      context: null,
      error: null,
      conversationTitle: "",
      capabilities: null,
    };
    this.chatRef = React.createRef();
    this.inputRef = React.createRef();
    this._mounted = false;
    this._onChromeMessage = null;
    this._unsubscribeConnection = null;
    this._unsubscribeConv = null;
    this._streamControl = null;
    this._streamingMsgId = null;
    this._streamingConvId = null;
    this._userScrolledUp = false;
    this._pendingRegenerate = null;
    this._saveScrollTimeout = null;
    this.closeOrgSwitcher = this.closeOrgSwitcher.bind(this);
    this.clearError = this.clearError.bind(this);
    this.onKeyDown = this.onKeyDown.bind(this);
    this.onSendMessage = this.onSendMessage.bind(this);
    this.onQuickAction = this.onQuickAction.bind(this);
    this.onToggleContext = this.onToggleContext.bind(this);
    this.onToggleConversations = this.onToggleConversations.bind(this);
    this.onToggleOrgSwitcher = this.onToggleOrgSwitcher.bind(this);
    this.onContextUpdate = this.onContextUpdate.bind(this);
    this.onRetryConnection = this.onRetryConnection.bind(this);
    this.onCancelGeneration = this.onCancelGeneration.bind(this);
    this.onRegenerate = this.onRegenerate.bind(this);
    this.onRetryMessage = this.onRetryMessage.bind(this);
    this.onSelectConversation = this.onSelectConversation.bind(this);
    this.onNewConversation = this.onNewConversation.bind(this);
    this.onDeleteConversation = this.onDeleteConversation.bind(this);
    this.onRenameConversation = this.onRenameConversation.bind(this);
    this.onScroll = this.onScroll.bind(this);
    this._streamToken = this._streamToken.bind(this);
    this._streamMeta = this._streamMeta.bind(this);
    this._streamDone = this._streamDone.bind(this);
    this._streamError = this._streamError.bind(this);
  }

  async componentDidMount() {
    this._mounted = true;
    document.addEventListener("keydown", this.onKeyDown);
    if (typeof chrome !== "undefined" && chrome.runtime?.onMessage) {
      this._onChromeMessage = (msg) => {
        if (msg.type === "ai_context_update") {
          this.onContextUpdate(msg.context);
        }
      };
      chrome.runtime.onMessage.addListener(this._onChromeMessage);
    }
    this._unsubscribeConnection = onConnectionChange((status) => {
      if (this._mounted) this.setState({ connectionStatus: status });
    });
    this._unsubscribeConv = conv.onChange(() => {
      if (!this._mounted) return;
      const active = conv.getActiveConversation();
      this.setState({
        messages: conv.getActiveMessages(),
        conversationTitle: active?.title || "",
      });
    });
    await conv.init();
    this.setState({
      messages: conv.getActiveMessages(),
      conversationTitle: conv.getActiveConversation()?.title || "",
    });
    startHealthMonitor();
    getCapabilities().then((caps) => {
      if (this._mounted) this.setState({ capabilities: caps });
    }).catch(() => {});
  }

  componentWillUnmount() {
    this._mounted = false;
    document.removeEventListener("keydown", this.onKeyDown);
    if (this._unsubscribeConnection) { this._unsubscribeConnection(); this._unsubscribeConnection = null; }
    if (this._unsubscribeConv) { this._unsubscribeConv(); this._unsubscribeConv = null; }
    if (typeof chrome !== "undefined" && chrome.runtime?.onMessage && this._onChromeMessage) {
      chrome.runtime.onMessage.removeListener(this._onChromeMessage);
      this._onChromeMessage = null;
    }
    stopHealthMonitor();
    this._abortStream();
    if (this._saveScrollTimeout) clearTimeout(this._saveScrollTimeout);
  }

  _scrollToBottom() {
    if (!this.chatRef.current) return;
    this.chatRef.current.scrollTop = this.chatRef.current.scrollHeight;
  }

  _isNearBottom() {
    const el = this.chatRef.current;
    if (!el) return true;
    return el.scrollHeight - el.scrollTop - el.clientHeight < 150;
  }

  _scrollIfNeeded() {
    if (!this._userScrolledUp && this.chatRef.current) {
      this._scrollToBottom();
    }
  }

  onScroll() {
    if (this._saveScrollTimeout) clearTimeout(this._saveScrollTimeout);
    this._saveScrollTimeout = setTimeout(() => {
      this._userScrolledUp = !this._isNearBottom();
    }, 200);
  }

  _abortStream() {
    if (this._streamControl) {
      this._streamControl.abort();
      this._streamControl = null;
    }
    this._streamingMsgId = null;
    this._streamingConvId = null;
    this._pendingRegenerate = null;
  }

  _streamToken(msgId, token) {
    if (!this._mounted || !this._streamingConvId) return;
    const msgs = conv.getConversation(this._streamingConvId)?.messages;
    if (!msgs) return;
    const existing = msgs.find(m => m.id === msgId);
    if (!existing) return;
    conv.streamUpdateContent(this._streamingConvId, msgId, (existing.content || "") + token, false);
    this._scrollIfNeeded();
  }

  _streamMeta(msgId, data) {
    if (data.conversation_id && this._streamingConvId) {
      conv.renameConversation(this._streamingConvId, null);
      const c = conv.getConversation(this._streamingConvId);
      if (c) c.backendConversationId = data.conversation_id;
    }
    if (data.token) {
      this._streamToken(msgId, data.token);
    }
  }

  _streamDone(msgId) {
    if (!this._mounted) return;
    this._streamControl = null;
    this._streamingMsgId = null;
    this._streamingConvId = null;
    this.setState({ isStreaming: false });
    this._scrollIfNeeded();
  }

  _streamError(msgId, errorMsg) {
    if (!this._mounted) return;
    conv.updateMessage(this._streamingConvId, msgId, { error: errorMsg });
    this._streamControl = null;
    this._streamingMsgId = null;
    this._streamingConvId = null;
    this._pendingRegenerate = null;
    this.setState({ isStreaming: false });
  }

  _getStreamingMsg() {
    if (!this._streamingConvId || !this._streamingMsgId) return null;
    return conv.getConversation(this._streamingConvId)?.messages?.find(m => m.id === this._streamingMsgId) || null;
  }

  _streamToolStart(data) {
    if (!this._mounted || !this._streamingMsgId) return;
    const msg = this._getStreamingMsg();
    if (!msg) return;
    const execs = msg.toolExecutions || [];
    execs.push({
      tool: data.tool || data.name || "unknown",
      status: "running",
      input: data.input || undefined,
      executionId: data.execution_id || `exec_${Date.now()}`,
      startedAt: Date.now(),
    });
    conv.streamUpdateMeta(this._streamingConvId, this._streamingMsgId, { toolExecutions: execs }, false);
    this._scrollIfNeeded();
  }

  _streamToolProgress(data) {
    if (!this._mounted || !this._streamingMsgId) return;
    const msg = this._getStreamingMsg();
    if (!msg) return;
    const execs = (msg.toolExecutions || []).map((e) => {
      if (e.tool === (data.tool || data.name) || e.executionId === data.execution_id) {
        return { ...e, progress: data.progress, progressMessage: data.message || e.progressMessage };
      }
      return e;
    });
    conv.streamUpdateMeta(this._streamingConvId, this._streamingMsgId, { toolExecutions: execs }, false);
  }

  _streamToolComplete(data) {
    if (!this._mounted || !this._streamingMsgId) return;
    const msg = this._getStreamingMsg();
    if (!msg) return;
    const execs = (msg.toolExecutions || []).map((e) => {
      if (e.tool === (data.tool || data.name) || e.executionId === data.execution_id) {
        return {
          ...e,
          status: "completed",
          durationMs: data.duration_ms || (Date.now() - e.startedAt),
          outputSummary: data.output_summary || data.result || undefined,
          output: data.output || undefined,
        };
      }
      return e;
    });
    conv.streamUpdateMeta(this._streamingConvId, this._streamingMsgId, { toolExecutions: execs }, false);
    this._scrollIfNeeded();
  }

  _streamToolFailed(data) {
    if (!this._mounted || !this._streamingMsgId) return;
    const msg = this._getStreamingMsg();
    if (!msg) return;
    const execs = (msg.toolExecutions || []).map((e) => {
      if (e.tool === (data.tool || data.name) || e.executionId === data.execution_id) {
        return { ...e, status: "failed", error: data.error || "Tool execution failed" };
      }
      return e;
    });
    conv.streamUpdateMeta(this._streamingConvId, this._streamingMsgId, { toolExecutions: execs }, false);
    this._scrollIfNeeded();
  }

  _streamCitation(data) {
    if (!this._mounted || !this._streamingMsgId) return;
    const msg = this._getStreamingMsg();
    if (!msg) return;
    const citations = msg.citations || [];
    citations.push({
      title: data.title || data.name || "Reference",
      type: data.type || "reference",
      id: data.id || data.url || `ref_${citations.length}`,
      url: data.url || undefined,
    });
    conv.streamUpdateMeta(this._streamingConvId, this._streamingMsgId, { citations }, false);
  }

  _streamReasoning(data) {
    if (!this._mounted || !this._streamingMsgId) return;
    const text = typeof data === "string" ? data : (data.text || data.content || data.reasoning || "");
    if (!text) return;
    const msg = this._getStreamingMsg();
    if (!msg) return;
    const existing = msg.reasoning || "";
    conv.streamUpdateMeta(this._streamingConvId, this._streamingMsgId, { reasoning: existing + text }, false);
  }

  onKeyDown(e) {
    if (e.key === "Escape") {
      if (this.state.showConversations) {
        this.setState({ showConversations: false });
        return;
      }
      if (this.state.showOrgSwitcher) {
        this.setState({ showOrgSwitcher: false });
        return;
      }
    }
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      if (this.state.isStreaming) {
        e.preventDefault();
        this.onCancelGeneration();
      }
    }
    if (e.key === "/" && !e.ctrlKey && !e.metaKey && !e.altKey) {
      const tag = document.activeElement?.tagName;
      if (tag !== "INPUT" && tag !== "TEXTAREA") {
        e.preventDefault();
        if (this.inputRef.current) this.inputRef.current.focus();
      }
    }
  }

  onContextUpdate(context) {
    if (!this._mounted) return;
    this.setState({ context, orgName: context?.orgName || null });
  }

  onToggleOrgSwitcher() {
    this.setState((s) => ({ showOrgSwitcher: !s.showOrgSwitcher }));
  }

  closeOrgSwitcher() {
    this.setState({ showOrgSwitcher: false });
  }

  onToggleContext() {
    this.setState((s) => ({ showContext: !s.showContext }));
  }

  onToggleConversations() {
    this.setState((s) => ({ showConversations: !s.showConversations }));
  }

  clearError() {
    this.setState({ error: null });
  }

  onRetryConnection() {
    this.setState({ error: null });
    health().then((result) => {
      if (result.status !== "ok" && this._mounted) {
        this.setState({ error: "Cannot connect to backend. Check your configuration." });
      }
    });
  }

  onCancelGeneration() {
    if (this.state.isStreaming) {
      this._abortStream();
      this.setState({ isStreaming: false });
    }
  }

  onRegenerate() {
    if (this.state.isStreaming) return;
    const msgs = conv.getActiveMessages();
    if (msgs.length < 2) return;
    const lastUserMsg = [...msgs].reverse().find((m) => m.role === "user");
    if (!lastUserMsg) return;
    this._pendingRegenerate = lastUserMsg.content;
    const activeId = conv.getActiveConversationId();
    if (activeId) conv.deleteLastUserAndAssistant(activeId);
  }

  onRetryMessage(msgId) {
    if (this.state.isStreaming) return;
    const msgs = conv.getActiveMessages();
    const errMsg = msgs.find((m) => m.id === msgId);
    if (!errMsg || errMsg.role !== "assistant") return;
    const lastUserMsg = [...msgs].reverse().find((m) => m.role === "user");
    if (lastUserMsg) {
      this._pendingRegenerate = lastUserMsg.content;
      const activeId = conv.getActiveConversationId();
      if (activeId) conv.deleteLastUserAndAssistant(activeId);
    }
  }

  onSelectConversation(id) {
    conv.setActiveConversation(id);
    this.setState({ showConversations: false });
  }

  onNewConversation() {
    conv.createConversation("New conversation");
    this.setState({ showConversations: false });
  }

  onDeleteConversation(id) {
    conv.deleteConversation(id);
  }

  onRenameConversation(id, title) {
    conv.renameConversation(id, title);
  }

  async onSendMessage(text) {
    if (!text || !text.trim()) return;
    if (this.state.isStreaming) {
      this.onCancelGeneration();
    }

    this._pendingRegenerate = null;
    const trimmed = text.trim();

    if (!isConfigured()) {
      this.setState({ error: "Backend not configured. Open Options to set the backend URL and API key." });
      return;
    }

    let activeId = conv.getActiveConversationId();
    if (!activeId) {
      const c = await conv.createConversation("New conversation");
      activeId = c.id;
    }
    const activeConv = conv.getConversation(activeId);
    if (!activeConv) return;

    const userMsg = await conv.addMessage(activeId, { role: "user", content: trimmed });
    if (!userMsg) return;

    const aiMsg = await conv.addMessage(activeId, { role: "assistant", content: "" });
    if (!aiMsg) return;

    this._streamingMsgId = aiMsg.id;
    this._streamingConvId = activeId;
    this._userScrolledUp = false;
    this.setState({ isStreaming: true, error: null });

    const messagesPayload = conv.getConversation(activeId).messages
      .filter((m) => !m.error)
      .map((m) => ({ role: m.role, content: m.content || "" }));

    const ctx = this.state.context;
    const contextPayload = ctx ? {
      pageType: ctx.pageType, setupArea: ctx.setupArea,
      sobject: ctx.sobject, recordId: ctx.recordId, recordName: ctx.recordName,
    } : undefined;

    try {
      const streamControl = streamChat(messagesPayload, {
        context: contextPayload,
        conversationId: activeConv.backendConversationId || undefined,
        onRawChunk: (chunk) => {
          parseStreamChunk(chunk, {
            onToken: (token) => this._streamToken(aiMsg.id, token),
            onMeta: (type, data) => {
              if (type === "meta") this._streamMeta(aiMsg.id, data);
              else if (type === "error") this._streamError(aiMsg.id, data.message || data.error || "Stream error");
            },
            onToolStart: (d) => this._streamToolStart(d),
            onToolProgress: (d) => this._streamToolProgress(d),
            onToolComplete: (d) => this._streamToolComplete(d),
            onToolFailed: (d) => this._streamToolFailed(d),
            onCitation: (d) => this._streamCitation(d),
            onReasoning: (d) => this._streamReasoning(d),
          });
        },
        onEvent: (event, data) => {
          if (event === "token" && data?.token) this._streamToken(aiMsg.id, data.token);
          if (event === "conversation_id" && this._streamingConvId) {
            const c = conv.getConversation(this._streamingConvId);
            if (c) c.backendConversationId = data;
          }
        },
        onDone: () => this._streamDone(aiMsg.id),
        onError: (err) => this._streamError(aiMsg.id, err.message),
      });
      this._streamControl = streamControl;
      try {
        await streamControl.result;
      } catch (e) {
        if (e.message !== "Stream disconnected" && e.message !== "The user aborted a request.") {
          if (this._mounted && this._streamingMsgId) {
            this._streamError(aiMsg.id, e.message);
          }
        }
      }
    } catch (e) {
      if (this._mounted) {
        this._streamError(aiMsg.id, e.message || "Failed to send message");
      }
    }
  }

  async componentDidUpdate(prevProps, prevState) {
    if (this._pendingRegenerate && !this.state.isStreaming) {
      const text = this._pendingRegenerate;
      this._pendingRegenerate = null;
      await this.onSendMessage(text);
    }
    const prevLen = prevState.messages.length;
    const currLen = this.state.messages.length;
    if (prevLen !== currLen && !this._userScrolledUp && this.chatRef.current) {
      this._scrollToBottom();
    }
  }

  onQuickAction(action) {
    this.onSendMessage(action);
  }

  render() {
    const { messages, isStreaming, showContext, showConversations, quickActions, context, error, showOrgSwitcher, connectionStatus, orgName, conversationTitle } = this.state;
    const hasMessages = messages.length > 0;
    const isUnconfigured = !isConfigured();
    const showReconnecting = connectionStatus === "reconnecting" && isConfigured();
    const showOffline = connectionStatus === "offline" && isConfigured();
    const lastMsg = hasMessages ? messages[messages.length - 1] : null;
    const hasError = lastMsg?.role === "assistant" && lastMsg?.error;

    return h("div", { className: "ai-scope ai-panel" },
      h(PanelHeader, {
        orgName: orgName || "Not connected",
        orgStatus: statusToOrgStatus(connectionStatus),
        connectionStatus,
        onToggleOrgSwitcher: this.onToggleOrgSwitcher,
        onToggleConversations: this.onToggleConversations,
        conversationTitle,
      }),
      (showReconnecting || showOffline) && h("div", {
        className: "ai-connection-banner",
        role: "alert",
      },
        h("span", { className: "ai-connection-banner-icon" },
          showReconnecting ? "\u21BB" : "\u2716"
        ),
        h("span", null,
          showReconnecting ? "Connection lost. Reconnecting..." : "Backend offline. Check your connection."
        ),
        showOffline && h("button", {
          className: "ai-connection-banner-btn",
          onClick: this.onRetryConnection,
        }, "Retry")
      ),
      showConversations && h(ConversationList, {
        conversations: conv.getConversations(),
        activeId: conv.getActiveConversationId(),
        onSelect: this.onSelectConversation,
        onNew: this.onNewConversation,
        onDelete: this.onDeleteConversation,
        onRename: this.onRenameConversation,
        onClose: () => this.setState({ showConversations: false }),
      }),
      showOrgSwitcher && h(OrgSwitcher, {
        orgs: [],
        onClose: this.closeOrgSwitcher,
      }),
      h(ContextBar, {
        context,
        expanded: showContext,
        onToggle: this.onToggleContext,
      }),
      h("div", {
        className: "ai-chat-scroll",
        ref: this.chatRef,
        onScroll: this.onScroll,
      },
        !hasMessages && !error && h(EmptyState, {
          onExampleClick: !isUnconfigured ? this.onQuickAction : undefined,
          isUnconfigured,
        }),
        error && h(ErrorState, { message: error, onRetry: this.clearError }),
        hasMessages && h("div", { className: "ai-message-group" },
          messages.map((msg, idx) =>
            h(ChatMessage, {
              key: msg.id,
              role: msg.role,
              content: msg.content || "",
              time: msg.time,
              error: msg.error,
              isStreaming: isStreaming && idx === messages.length - 1 && msg.role === "assistant",
              onRetry: msg.error ? () => this.onRetryMessage(msg.id) : undefined,
              toolExecutions: msg.toolExecutions,
              citations: msg.citations,
              reasoning: msg.reasoning,
            })
          )
        ),
        isStreaming && hasMessages && h("div", { className: "ai-typing" },
          h("div", { className: "ai-typing-dots" },
            h("div", { className: "ai-typing-dot" }),
            h("div", { className: "ai-typing-dot" }),
            h("div", { className: "ai-typing-dot" })
          ),
          h("span", { className: "ai-typing-text" }, "Generating...")
        )
      ),
      isStreaming && h("div", { className: "ai-streaming-controls" },
        h("button", {
          className: "ai-btn ai-btn-ghost",
          onClick: this.onCancelGeneration,
          "aria-label": "Cancel generation",
        },
          h("svg", { width: "14", height: "14", viewBox: "0 0 14 14", fill: "currentColor" },
            h("rect", { x: "3", y: "3", width: "8", height: "8", rx: "1" })
          ),
          h("span", null, "Cancel")
        ),
        h("span", { className: "ai-streaming-indicator" }),
      ),
      !isStreaming && h(QuickActions, {
        actions: quickActions,
        onAction: this.onQuickAction,
        visible: !hasMessages && !isStreaming,
      }),
      h(ChatInput, {
        ref: this.inputRef,
        onSend: this.onSendMessage,
        disabled: false,
        placeholder: isUnconfigured ? "Configure backend in Options" : "Ask about this page...",
      })
    );
  }
}

ReactDOM.render(
  h(SidePanelApp),
  document.getElementById("ai-root")
);
