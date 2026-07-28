/* global chrome */

const STORAGE_KEY = "ai_conversations";
const MAX_CONVERSATIONS = 50;

let _conversations = [];
let _activeId = null;
let _loaded = false;
let _listeners = new Set();
let _msgIdCounter = 0;

function _notify() {
  for (const fn of _listeners) {
    try { fn(); } catch (e) { /* ignore */ }
  }
}

function _now() {
  return new Date().toISOString();
}

function _generateId() {
  return "msg_" + Date.now() + "_" + (++_msgIdCounter) + "_" + Math.random().toString(36).slice(2, 6);
}

export function getConversations() {
  return _conversations;
}

export function getActiveConversation() {
  if (!_activeId) return null;
  return _conversations.find((c) => c.id === _activeId) || null;
}

export function getActiveMessages() {
  const conv = getActiveConversation();
  return conv ? conv.messages : [];
}

export function getActiveConversationId() {
  return _activeId;
}

export function getConversation(id) {
  return _conversations.find((c) => c.id === id) || null;
}

export function onChange(fn) {
  _listeners.add(fn);
  return () => _listeners.delete(fn);
}

export async function init() {
  if (_loaded) return;
  try {
    const data = await _load();
    if (data && Array.isArray(data.conversations)) {
      _conversations = data.conversations;
      _activeId = data.activeId || null;
      if (_activeId && !_conversations.find((c) => c.id === _activeId)) {
        _activeId = _conversations[0]?.id || null;
      }
    }
  } catch (e) {
    console.warn("conversationService.init failed:", e);
  }
  if (!_activeId && _conversations.length === 0) {
    const c = _createConversationInternal("New conversation");
    _activeId = c.id;
  }
  _loaded = true;
  _notify();
}

function _createConversationInternal(title) {
  const conv = {
    id: "conv_" + Date.now() + "_" + Math.random().toString(36).slice(2, 6),
    title: title || "New conversation",
    messages: [],
    createdAt: _now(),
    updatedAt: _now(),
    backendConversationId: null,
  };
  _conversations.unshift(conv);
  return conv;
}

export async function createConversation(title) {
  const conv = _createConversationInternal(title);
  _activeId = conv.id;
  await _persist();
  _notify();
  return conv;
}

export async function deleteConversation(id) {
  _conversations = _conversations.filter((c) => c.id !== id);
  if (_activeId === id) {
    _activeId = _conversations[0]?.id || null;
    if (!_activeId) {
      const c = _createConversationInternal("New conversation");
      _activeId = c.id;
    }
  }
  await _persist();
  _notify();
}

export async function setActiveConversation(id) {
  if (_activeId === id) return;
  const conv = _conversations.find((c) => c.id === id);
  if (!conv) return;
  _activeId = id;
  await _persist();
  _notify();
}

export async function renameConversation(id, title) {
  const conv = _conversations.find((c) => c.id === id);
  if (!conv) return;
  conv.title = title;
  conv.updatedAt = _now();
  await _persist();
  _notify();
}

export async function addMessage(convId, msg) {
  const conv = _conversations.find((c) => c.id === convId);
  if (!conv) return null;
  const message = {
    id: msg.id || _generateId(),
    role: msg.role || "user",
    content: msg.content || "",
    time: msg.time || _now(),
    error: msg.error || null,
  };
  conv.messages.push(message);
  conv.updatedAt = _now();
  if (conv.messages.length === 1 && conv.title === "New conversation") {
    conv.title = msg.content?.slice(0, 60) || "New conversation";
  }
  await _persist();
  _notify();
  return message;
}

export async function updateMessage(convId, msgId, updates) {
  const conv = _conversations.find((c) => c.id === convId);
  if (!conv) return;
  const msg = conv.messages.find((m) => m.id === msgId);
  if (!msg) return;
  Object.assign(msg, updates);
  conv.updatedAt = _now();
  await _persist();
  _notify();
}

export async function deleteLastUserAndAssistant(convId) {
  const conv = _conversations.find((c) => c.id === convId);
  if (!conv) return;
  for (let i = conv.messages.length - 1; i >= 0; i--) {
    if (conv.messages[i].role === "assistant") {
      conv.messages.splice(i, 1);
    } else if (conv.messages[i].role === "user") {
      conv.messages.splice(i, 1);
      break;
    }
  }
  conv.updatedAt = _now();
  await _persist();
  _notify();
}

function _load() {
  return new Promise((resolve) => {
    if (typeof chrome !== "undefined" && chrome.storage?.local) {
      chrome.storage.local.get(STORAGE_KEY, (result) => {
        resolve(result[STORAGE_KEY] || null);
      });
    } else {
      try {
        const raw = localStorage.getItem(STORAGE_KEY);
        resolve(raw ? JSON.parse(raw) : null);
      } catch (e) {
        resolve(null);
      }
    }
  });
}

function _persist() {
  while (_conversations.length > MAX_CONVERSATIONS) {
    _conversations.pop();
  }
  const data = { conversations: _conversations, activeId: _activeId };
  return new Promise((resolve) => {
    if (typeof chrome !== "undefined" && chrome.storage?.local) {
      chrome.storage.local.set({ [STORAGE_KEY]: data }, resolve);
    } else {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
      } catch (e) { /* ignore */ }
      resolve();
    }
  });
}

export function streamUpdateContent(convId, msgId, content, isDone) {
  const conv = _conversations.find((c) => c.id === convId);
  if (!conv) return;
  const msg = conv.messages.find((m) => m.id === msgId);
  if (!msg) return;
  msg.content = content;
  conv.updatedAt = _now();
  _notify();
  if (isDone) {
    _persist().catch(() => {});
  }
}

export function streamUpdateMeta(convId, msgId, updates, isDone) {
  const conv = _conversations.find((c) => c.id === convId);
  if (!conv) return;
  const msg = conv.messages.find((m) => m.id === msgId);
  if (!msg) return;
  let changed = false;
  for (const [key, value] of Object.entries(updates)) {
    const strVal = JSON.stringify(value);
    const strCur = JSON.stringify(msg[key]);
    if (strVal !== strCur) {
      msg[key] = value;
      changed = true;
    }
  }
  if (!changed) return;
  conv.updatedAt = _now();
  _notify();
  if (isDone) {
    _persist().catch(() => {});
  }
}

export async function clearAllConversations() {
  _conversations = [];
  _activeId = null;
  const c = _createConversationInternal("New conversation");
  _activeId = c.id;
  await _persist();
  _notify();
}
