

const ChatState = {
  _listeners: new Set(),
  _state: {
    messages: [],
    isStreaming: false,
    streamingMessage: null,
    error: null,
    isLoading: false,
    isProcessing: false,
    suggestedQuestions: [],
    context: null,
    activeConversationId: null,
    toolExecutions: [],
  },

  getState() {
    return {...this._state};
  },

  get messages() { return [...this._state.messages]; },
  get isStreaming() { return this._state.isStreaming; },
  get streamingMessage() { return this._state.streamingMessage; },
  get error() { return this._state.error; },
  get isLoading() { return this._state.isLoading; },
  get isProcessing() { return this._state.isProcessing; },
  get suggestedQuestions() { return [...this._state.suggestedQuestions]; },
  get activeConversationId() { return this._state.activeConversationId; },
  get toolExecutions() { return [...this._state.toolExecutions]; },

  _setState(update) {
    this._state = {...this._state, ...update};
    this._notify();
  },

  _notify() {
    this._listeners.forEach((fn) => fn(this.getState()));
  },

  subscribe(fn) {
    this._listeners.add(fn);
    return () => this._listeners.delete(fn);
  },

  reset() {
    this._setState({
      messages: [],
      isStreaming: false,
      streamingMessage: null,
      error: null,
      isLoading: false,
      isProcessing: false,
      suggestedQuestions: [],
      toolExecutions: [],
    });
  },

  setMessages(messages) { this._setState({messages: [...messages]}); },

  addMessage(msg) {
    this._setState({messages: [...this._state.messages, msg]});
  },

  updateLastMessage(update) {
    const msgs = [...this._state.messages];
    if (msgs.length > 0) {
      msgs[msgs.length - 1] = {...msgs[msgs.length - 1], ...update};
      this._setState({messages: msgs});
    }
  },

  setStreaming(isStreaming, streamingMessage = null) {
    this._setState({isStreaming, streamingMessage});
  },

  appendStreamingContent(chunk) {
    const msg = this._state.streamingMessage;
    if (msg) {
      this._setState({
        streamingMessage: {...msg, content: msg.content + chunk},
      });
    }
  },

  finalizeStreaming() {
    if (this._state.streamingMessage) {
      this._state.streamingMessage.isStreaming = false;
      this.addMessage(this._state.streamingMessage);
    }
    this._setState({isStreaming: false, streamingMessage: null});
  },

  setError(error) { this._setState({error}); },
  clearError() { this._setState({error: null}); },
  setLoading(isLoading) { this._setState({isLoading}); },
  setProcessing(isProcessing) { this._setState({isProcessing}); },
  setSuggestedQuestions(questions) { this._setState({suggestedQuestions: [...questions]}); },
  setActiveConversationId(id) { this._setState({activeConversationId: id}); },
  setContext(context) { this._setState({context}); },
  setToolExecutions(executions) { this._setState({toolExecutions: [...executions]}); },

  addToolExecution(execution) {
    this._setState({
      toolExecutions: [...this._state.toolExecutions, execution],
    });
  },

  updateToolExecution(id, update) {
    this._setState({
      toolExecutions: this._state.toolExecutions.map((e) =>
        e.id === id ? {...e, ...update} : e
      ),
    });
  },

  submitMessage(content) {
    this.addMessage({role: "user", content, timestamp: Date.now()});
    this._setState({isProcessing: true, error: null});
  },
};

export default ChatState;
