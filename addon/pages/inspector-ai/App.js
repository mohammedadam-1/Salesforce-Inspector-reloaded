/* global React ReactDOM */
import ChatState from "./state/chatState.js";
import WorkspaceLayout from "./Layout.js";
import CitationChips from "./components/CitationChips.js";
import ConfidenceBadge from "./components/ConfidenceBadge.js";
import NextActionsPanel from "./components/NextActionsPanel.js";
import ContextPanel from "./components/ContextPanel.js";
import useChatState from "./hooks/useChatState.js";
import useConversations from "./hooks/useConversations.js";
import useSalesforceContext from "./hooks/useSalesforceContext.js";
import useWorkspaceSettings from "./hooks/useWorkspaceSettings.js";
import ChatMessage from "../../components/ChatMessage.js";
import ChatInput from "../../components/ChatInput.js";
import EmptyState from "../../components/EmptyState.js";
import ErrorState from "../../components/ErrorState.js";
import QuickActions from "../../components/QuickActions.js";
import ConversationList from "../../components/ConversationList.js";
import ToolExecutionPanel from "../../components/ToolExecutionPanel.js";

const h = React.createElement;

function InspectorAiApp() {
  const {
    messages, isStreaming, streamingMessage, error, isProcessing,
    suggestedQuestions, toolExecutions,
    submitMessage, clearChat, retry,
  } = useChatState();

  const {
    conversations, activeId, isLoading: convsLoading,
    selectConversation, createConversation, deleteConversation, renameConversation,
  } = useConversations();

  const {context: sfContext, isLoading: ctxLoading, refresh: refreshContext} = useSalesforceContext();
  const {showTimeline} = useWorkspaceSettings();

  const handleSend = React.useCallback(async (content) => {
    if (!content || !content.trim()) return;
    await submitMessage(content, sfContext);
  }, [submitMessage, sfContext]);

  const handleAction = React.useCallback((action) => {
    if (action.type === "query" && action.payload) handleSend(action.payload);
    else if (action.type === "navigate" && action.url) {
      if (window.openInTab) window.openInTab(action.url);
    } else if (action.type === "analyze" && action.prompt) handleSend(action.prompt);
    else if (action.type === "execute" && action.command) handleSend(action.command);
  }, [handleSend]);

  const handleCitationNavigate = React.useCallback((url) => {
    if (window.openInTab) window.openInTab(url);
  }, []);

  const renderMessage = React.useCallback((msg, idx) => {
    if (msg.role === "user") {
      return h(ChatMessage, {
        key: msg.timestamp || idx,
        content: msg.content,
        role: "user",
        time: msg.timestamp,
      });
    }
    return h("div", {key: msg.timestamp || idx},
      h(ChatMessage, {
        content: msg.content || "",
        role: "assistant",
        isStreaming: msg.isStreaming,
        time: msg.timestamp,
      }),
      h(CitationChips, {citations: msg.citations, onNavigate: handleCitationNavigate}),
      h(ConfidenceBadge, {confidence: msg.confidence}),
      h(NextActionsPanel, {actions: msg.suggestedActions, onAction: handleAction})
    );
  }, [handleCitationNavigate, handleAction]);

  const renderSidebar = React.useCallback(() =>
    h("div", null,
      h("div", {className: "ai-workspace-sidebar-header"},
        h("span", {style: {fontWeight: 600, fontSize: 13}}, "History"),
        h("button", {
          className: "ai-workspace-btn",
          onClick: () => createConversation("New Conversation", sfContext),
          title: "New conversation",
          style: {padding: "2px 6px", fontSize: 11},
        }, "+ New")
      ),
      h("div", {className: "ai-workspace-sidebar-list"},
        h(ConversationList, {
          conversations,
          activeId,
          onSelect: selectConversation,
          onDelete: deleteConversation,
          onRename: renameConversation,
          isLoading: convsLoading,
        })
      )
    ),
  [conversations, activeId, selectConversation, deleteConversation, renameConversation, convsLoading, createConversation, sfContext]);

  const renderTimeline = React.useCallback(() =>
    h("div", null,
      h("div", {className: "ai-workspace-timeline-title"}, "Tool Executions"),
      h(ToolExecutionPanel, {executions: toolExecutions})
    ),
  [toolExecutions]);

  return h(WorkspaceLayout, {
    header: "Inspector AI",
    headerActions: h("button", {
      className: "ai-workspace-btn",
      onClick: clearChat,
      title: "Clear conversation",
    }, "Clear"),
    contextBar: h(ContextPanel, {context: sfContext, isLoading: ctxLoading, onRefresh: refreshContext}),
    sidebar: renderSidebar(),
    chat: h("div", null,
      messages.length === 0 && !isProcessing && !error
        ? h(EmptyState, {title: "Inspector AI", description: "Ask questions about your Salesforce org, analyze metadata, generate SOQL queries, and more."})
        : null,
      error ? h(ErrorState, {message: error, onRetry: retry, onDismiss: () => ChatState.clearError()}) : null,
      messages.map(renderMessage),
      isStreaming && streamingMessage && !messages.includes(streamingMessage)
        ? h("div", {key: "streaming"},
          h(ChatMessage, {content: streamingMessage.content || "", role: "assistant", isStreaming: true}),
          h(CitationChips, {citations: streamingMessage.citations, onNavigate: handleCitationNavigate}),
          h(ConfidenceBadge, {confidence: streamingMessage.confidence})
        )
        : null,
      suggestedQuestions.length > 0 && !isStreaming
        ? h(QuickActions, {actions: suggestedQuestions, onAction: handleSend})
        : null
    ),
    timeline: showTimeline && toolExecutions.length > 0 ? renderTimeline() : null,
    inputArea: h(ChatInput, {
      onSend: handleSend,
      disabled: isProcessing || isStreaming,
      placeholder: isProcessing ? "Processing..." : "Ask about your Salesforce org...",
    }),
  });
}

export default InspectorAiApp;

const root = document.getElementById("ai-workspace-root");
if (root) {
  ReactDOM.render(h(InspectorAiApp), root); // eslint-disable-line react/no-deprecated
}
