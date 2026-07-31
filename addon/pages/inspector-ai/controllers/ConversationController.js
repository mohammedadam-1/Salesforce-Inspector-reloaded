import ConversationState from "../state/conversationState.js";
import ChatState from "../state/chatState.js";
import * as conv from "../../../services/conversationService.js";

const ConversationController = {
  loadConversations() {
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
  },

  async selectConversation(id) {
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
  },

  async createConversation(title, context) {
    try {
      const convResult = await conv.createConversation(title || "New Conversation");
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
  },

  async deleteConversation(id) {
    try {
      await conv.deleteConversation(id);
      ConversationState.removeConversation(id);
      if (ConversationState.activeId === id) {
        ChatState.reset();
      }
    } catch (err) {
      ConversationState.setError(err.message || "Failed to delete conversation");
    }
  },

  async renameConversation(id, title) {
    try {
      await conv.renameConversation(id, title);
      ConversationState.updateConversation(id, {title});
    } catch (err) {
      ConversationState.setError(err.message || "Failed to rename conversation");
    }
  },

  init() {
    conv.init().then(() => {
      this.loadConversations();
    });
  },
};

export default ConversationController;
