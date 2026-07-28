const ConversationState = {
  _listeners: new Set(),
  _state: {
    conversations: [],
    activeId: null,
    isLoading: false,
    error: null,
  },

  getState() { return {...this._state}; },
  get conversations() { return [...this._state.conversations]; },
  get activeId() { return this._state.activeId; },
  get isLoading() { return this._state.isLoading; },
  get error() { return this._state.error; },

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

  setConversations(conversations) { this._setState({conversations: [...conversations]}); },
  addConversation(conv) { this._setState({conversations: [conv, ...this._state.conversations]}); },

  updateConversation(id, update) {
    this._setState({
      conversations: this._state.conversations.map((c) =>
        c.id === id ? {...c, ...update} : c
      ),
    });
  },

  removeConversation(id) {
    this._setState({
      conversations: this._state.conversations.filter((c) => c.id !== id),
      activeId: this._state.activeId === id ? null : this._state.activeId,
    });
  },

  setActiveId(id) { this._setState({activeId: id}); },
  setLoading(isLoading) { this._setState({isLoading}); },
  setError(error) { this._setState({error}); },
  clearError() { this._setState({error: null}); },

  reset() {
    this._setState({conversations: [], activeId: null, isLoading: false, error: null});
  },
};

export default ConversationState;
