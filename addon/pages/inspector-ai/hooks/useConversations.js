/* global React */
import ConversationState from "../state/conversationState.js";
import ChatState from "../state/chatState.js";
import * as conv from "../../../services/conversationService.js";

export default function useConversations() {
  const [state, setState] = React.useState(ConversationState.getState());

  React.useEffect(() => {
    const unsub = ConversationState.subscribe(setState);
    return unsub;
  }, []);

  const loadConversations = React.useCallback(async () => {
    ConversationState.setLoading(true);
    ConversationState.clearError();
    try {
      const conversations = conv.getConversations();
      ConversationState.setConversations(conversations || []);
    } catch (err) {
      ConversationState.setError(err.message || "Failed to load conversations");
    } finally {
      ConversationState.setLoading(false);
    }
  }, []);

  const selectConversation = React.useCallback(async (id) => {
    ConversationState.setActiveId(id);
    conv.setActiveConversation(id);
    ChatState.setLoading(true);
    try {
      const c = conv.getConversation(id);
      if (c) {
        ChatState.setMessages(c.messages || []);
        ChatState.setActiveConversationId(id);
      }
    } catch (err) {
      ChatState.setError(err.message || "Failed to load conversation");
    } finally {
      ChatState.setLoading(false);
    }
  }, []);

  const createConversation = React.useCallback(async (title, context) => {
    try {
      const convResult = await conv.createConversation(title || "New Conversation");
      if (!convResult) return null;
      ConversationState.addConversation(convResult);
      ConversationState.setActiveId(convResult.id);
      ChatState.reset();
      ChatState.setActiveConversationId(convResult.id);
      if (context) ChatState.setContext(context);
      return convResult;
    } catch (err) {
      ConversationState.setError(err.message || "Failed to create conversation");
      return null;
    }
  }, []);

  const deleteConversation = React.useCallback(async (id) => {
    try {
      await conv.deleteConversation(id);
      ConversationState.removeConversation(id);
      if (ConversationState.activeId === id) {
        ChatState.reset();
      }
    } catch (err) {
      ConversationState.setError(err.message || "Failed to delete conversation");
    }
  }, []);

  const renameConversation = React.useCallback(async (id, title) => {
    try {
      await conv.renameConversation(id, title);
      ConversationState.updateConversation(id, {title});
    } catch (err) {
      ConversationState.setError(err.message || "Failed to rename conversation");
    }
  }, []);

  React.useEffect(() => {
    conv.init().then(() => loadConversations());
  }, [loadConversations]);

  return {
    state,
    conversations: state.conversations,
    activeId: state.activeId,
    isLoading: state.isLoading,
    error: state.error,
    loadConversations,
    selectConversation,
    createConversation,
    deleteConversation,
    renameConversation,
  };
}
