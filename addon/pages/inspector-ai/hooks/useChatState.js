/* global React */
import ChatState from "../state/chatState.js";
import {streamChat} from "../../../services/aiApiClient.js";
import * as conv from "../../../services/conversationService.js";

function parseStreamChunk(chunk, handlers) {
  const {onToken, onMeta, onToolStart, onToolProgress, onToolComplete, onToolFailed, onCitation} = handlers;
  const lines = chunk.split("\n");
  let currentEvent = "";

  for (const raw of lines) {
    if (raw.startsWith("event: ")) {
      currentEvent = raw.slice(7).trim();
    } else if (raw.startsWith("data: ")) {
      const payload = raw.slice(6);
      let data;
      try { data = JSON.parse(payload); } catch { data = payload; }

      if (currentEvent === "tool_start" && onToolStart) onToolStart(data);
      else if (currentEvent === "tool_progress" && onToolProgress) onToolProgress(data);
      else if (currentEvent === "tool_complete" && onToolComplete) onToolComplete(data);
      else if (currentEvent === "tool_failed" && onToolFailed) onToolFailed(data);
      else if (currentEvent === "citation" && onCitation) onCitation(data);
      else if (currentEvent === "token") {
        const t = typeof data === "object" ? (data.token || data.content || data.text || "") : data;
        if (t && onToken) onToken(t);
      } else if (currentEvent === "done") { if (onMeta) onMeta("meta", data); } else if (currentEvent === "error") { if (onMeta) onMeta("error", data); } else if (!currentEvent || currentEvent === "message") {
        const token = typeof data === "object" ? (data.token || data.content || data.text || data.message || "") : data;
        if (token && token !== "") { if (onToken) onToken(token); } else if (data?.conversation_id || data?.event === "done" || data?.type === "done") { if (onMeta) onMeta("meta", data); } else if (data?.event === "error" || data?.type === "error") { if (onMeta) onMeta("error", data); } else if (onMeta) onMeta("meta", data);
      }
      currentEvent = "";
    }
    if (raw === "") currentEvent = "";
  }
}

export default function useChatState() {
  const [state, setState] = React.useState(ChatState.getState());

  React.useEffect(() => {
    const unsub = ChatState.subscribe(setState);
    return unsub;
  }, []);

  const submitMessage = React.useCallback(async (content, sfContext) => {
    ChatState.submitMessage(content);

    let activeId = conv.getActiveConversationId();
    if (!activeId) {
      const c = await conv.createConversation("New conversation");
      activeId = c.id;
      ChatState.setActiveConversationId(activeId);
    }

    const userMsg = await conv.addMessage(activeId, {role: "user", content});
    if (!userMsg) { ChatState.setProcessing(false); return; }

    const aiMsg = await conv.addMessage(activeId, {role: "assistant", content: ""});
    if (!aiMsg) { ChatState.setProcessing(false); return; }

    const messagesPayload = conv.getConversation(activeId).messages
      .filter((m) => !m.error)
      .map((m) => ({role: m.role, content: m.content || ""}));

    const contextPayload = sfContext ? {
      pageType: sfContext.pageType,
      sobject: sfContext.objectType,
      recordId: sfContext.recordId,
    } : undefined;

    const activeConv = conv.getConversation(activeId);

    try {
      const streamControl = streamChat(messagesPayload, {
        context: contextPayload,
        conversationId: activeConv?.backendConversationId || undefined,
        onRawChunk: (chunk) => {
          parseStreamChunk(chunk, {
            onToken: (token) => {
              if (!ChatState.streamingMessage) {
                ChatState.setStreaming(true, {
                  role: "assistant",
                  content: token,
                  isStreaming: true,
                  citations: [],
                  confidence: null,
                  suggestedActions: [],
                  toolCalls: [],
                  timestamp: Date.now(),
                });
              } else {
                ChatState.appendStreamingContent(token);
              }
            },
            onMeta: (type, data) => {
              if (type === "meta") {
                if (data?.conversation_id && activeId) {
                  const c = conv.getConversation(activeId);
                  if (c) c.backendConversationId = data.conversation_id;
                }
                if (data?.suggested_questions) {
                  ChatState.setSuggestedQuestions(data.suggested_questions);
                }
                if (data?.confidence !== undefined) {
                  ChatState.updateLastMessage({confidence: data.confidence});
                }
                if (data?.citations) {
                  ChatState.updateLastMessage({citations: data.citations});
                }
                if (data?.suggested_actions) {
                  ChatState.updateLastMessage({suggestedActions: data.suggested_actions});
                }
              } else if (type === "error") {
                ChatState.setError(data?.message || data?.error || "Stream error");
              }
            },
            onToolStart: (d) => {
              ChatState.addToolExecution({
                id: d.execution_id || `exec_${Date.now()}`,
                tool: d.tool || d.name || "unknown",
                input: d.input,
                status: "running",
                startedAt: Date.now(),
              });
            },
            onToolProgress: (d) => {
              ChatState.updateToolExecution(d.execution_id, {
                progress: d.progress,
                progressMessage: d.message,
              });
            },
            onToolComplete: (d) => {
              ChatState.updateToolExecution(d.execution_id, {
                status: "completed",
                outputSummary: d.output_summary || d.result,
                durationMs: d.duration_ms,
                completedAt: Date.now(),
              });
            },
            onToolFailed: (d) => {
              ChatState.updateToolExecution(d.execution_id, {
                status: "failed",
                error: d.error || "Tool execution failed",
              });
            },
            onCitation: (d) => {
              ChatState.updateLastMessage({
                citations: [...(ChatState.state?.messages?.[ChatState.state.messages.length - 1]?.citations || []), {
                  title: d.title || d.name || "Reference",
                  type: d.type || "reference",
                  id: d.id || d.url || `ref_${Date.now()}`,
                  url: d.url,
                }],
              });
            },
          });
        },
        onEvent: (event, data) => {
          if (event === "token" && data?.token) {
            if (!ChatState.streamingMessage) {
              ChatState.setStreaming(true, {
                role: "assistant",
                content: data.token,
                isStreaming: true,
                citations: [],
                confidence: null,
                suggestedActions: [],
                toolCalls: [],
                timestamp: Date.now(),
              });
            } else {
              ChatState.appendStreamingContent(data.token);
            }
          }
        },
        onDone: () => {
          const finalMsg = ChatState.streamingMessage;
          if (finalMsg) {
            ChatState.finalizeStreaming();
          }
          ChatState.setProcessing(false);
        },
        onError: (err) => {
          ChatState.setStreaming(false, null);
          ChatState.setProcessing(false);
          ChatState.setError(err.message || "Stream error");
        },
      });

      try {
        await streamControl.result;
      } catch (e) {
        if (e.message !== "Stream disconnected" && e.message !== "The user aborted a request.") {
          ChatState.setStreaming(false, null);
          ChatState.setProcessing(false);
          ChatState.setError(e.message);
        }
      }
    } catch (e) {
      ChatState.setStreaming(false, null);
      ChatState.setProcessing(false);
      ChatState.setError(e.message || "Failed to send message");
    }
  }, []);

  const clearChat = React.useCallback(() => {
    ChatState.reset();
  }, []);

  const retry = React.useCallback(async () => {
    const msgs = ChatState.messages;
    const lastUser = [...msgs].reverse().find((m) => m.role === "user");
    if (lastUser) {
      ChatState.setError(null);
      ChatState.setProcessing(false);
      const activeId = conv.getActiveConversationId();
      if (activeId) conv.deleteLastUserAndAssistant(activeId);
      await submitMessage(lastUser.content, ChatState.context);
    }
  }, [submitMessage]);

  return {
    state,
    submitMessage,
    clearChat,
    retry,
    messages: state.messages,
    isStreaming: state.isStreaming,
    streamingMessage: state.streamingMessage,
    error: state.error,
    isLoading: state.isLoading,
    isProcessing: state.isProcessing,
    suggestedQuestions: state.suggestedQuestions,
    toolExecutions: state.toolExecutions,
    activeConversationId: state.activeConversationId,
  };
}
