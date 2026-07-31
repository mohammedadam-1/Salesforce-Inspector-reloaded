import ChatState from "../state/chatState.js";

function getHostFromUrl() {
  const params = new URLSearchParams(location.search.slice(1));
  return params.get("host");
}

function buildContext(host) {
  if (!host) return null;
  return {
    orgId: null,
    userId: null,
    orgName: host ? host.split(".")[0].toUpperCase() : host,
    username: null,
    apiVersion: null,
    recordId: null,
    objectType: null,
    selectedText: null,
    pageUrl: null,
    sfHost: host,
  };
}

const ContextController = {
  _listeners: new Set(),
  _context: null,

  get context() {
    return this._context;
  },

  subscribe(fn) {
    this._listeners.add(fn);
    return () => this._listeners.delete(fn);
  },

  _notify() {
    for (const fn of this._listeners) {
      try { fn(this._context); } catch { /* ignore */ }
    }
  },

  refresh() {
    const host = getHostFromUrl();
    const ctx = buildContext(host);
    this._context = ctx;
    ChatState.setContext(ctx);
    this._notify();
    return ctx;
  },

  init() {
    this.refresh();
    if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.onMessage) {
      const handler = function(msg) {
        if (msg.type === "ai_context_update") {
          this._context = {...(this._context || {}), ...msg.context};
          ChatState.setContext(this._context);
          this._notify();
        }
      }.bind(this);
      chrome.runtime.onMessage.addListener(handler);
    }
  },
};

export default ContextController;
