/* global chrome */

const CONFIG_KEYS = {
  URL: "sfirBackendUrl",
  KEY: "sfirBackendApiKey",
  ORG: "sfirBackendOrgId",
};

const HEALTH_CHECK_INTERVAL = 30000;
const DEFAULT_TIMEOUT = 30000;
const MAX_RETRIES = 2;
const RETRY_BASE_DELAY = 1000;

let _listeners = new Set();
let _connectionStatus = "unknown";

export const ConnectionStatus = Object.freeze({
  UNKNOWN: "unknown",
  CONFIGURING: "configuring",
  CONNECTED: "connected",
  RECONNECTING: "reconnecting",
  OFFLINE: "offline",
  ERROR: "error",
});

export function getBackendConfig() {
  const url = localStorage.getItem(CONFIG_KEYS.URL);
  const apiKey = localStorage.getItem(CONFIG_KEYS.KEY);
  const organizationId = localStorage.getItem(CONFIG_KEYS.ORG);
  if (!url || !apiKey) return null;
  return { url: url.replace(/\/+$/, ""), apiKey, organizationId };
}

export function isConfigured() {
  return !!getBackendConfig();
}

export function getConnectionStatus() {
  return _connectionStatus;
}

export function onConnectionChange(fn) {
  _listeners.add(fn);
  return () => _listeners.delete(fn);
}

function _setStatus(status) {
  if (_connectionStatus === status) return;
  _connectionStatus = status;
  for (const fn of _listeners) {
    try { fn(status); } catch (e) { /* ignore listener errors */ }
  }
}

function buildUrl(baseUrl, path, queryParams) {
  let url = `${baseUrl}${path}`;
  if (queryParams) {
    const sp = new URLSearchParams();
    for (const [k, v] of Object.entries(queryParams)) {
      if (v !== undefined && v !== null) {
        if (Array.isArray(v)) v.forEach(x => sp.append(k, x));
        else sp.set(k, v);
      }
    }
    const qs = sp.toString();
    if (qs) url += `?${qs}`;
  }
  return url;
}

function buildHeaders(config) {
  const hdrs = {
    "X-API-Key": config.apiKey,
    "Accept": "application/json",
  };
  if (config.organizationId) hdrs["X-Organization-ID"] = config.organizationId;
  return hdrs;
}

async function retryWithBackoff(fn, retries = MAX_RETRIES) {
  let lastError;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      return await fn();
    } catch (e) {
      lastError = e;
      if (attempt < retries) {
        const delay = RETRY_BASE_DELAY * Math.pow(2, attempt);
        await new Promise(r => setTimeout(r, delay));
      }
    }
  }
  throw lastError;
}

async function sendBackgroundRequest(method, path, opts = {}) {
  const config = getBackendConfig();
  if (!config) throw new Error("Backend not configured.");

  const url = buildUrl(config.url, path, opts.query);
  const headers = buildHeaders(config);
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";

  return new Promise((resolve, reject) => {
    const timeout = opts.timeout || DEFAULT_TIMEOUT;
    let timer = setTimeout(() => {
      timer = null;
      reject(new Error("Request timed out"));
    }, timeout);

    chrome.runtime.sendMessage({
      message: "aiBackendRequest",
      method: method || "GET",
      url,
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    }, (response) => {
      if (timer) clearTimeout(timer);
      if (!response) {
        reject(new Error("No response from background"));
        return;
      }
      if (!response.success) {
        reject(new Error(response.error || "Request failed"));
        return;
      }
      resolve(response.data);
    });
  });
}

function parseSSEStream(reader, decoder, onEvent, onDone, onError) {
  let buffer = "";

  function processBuffer() {
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    let currentEvent = "";
    let currentData = "";

    for (const line of lines) {
      if (line.startsWith("event: ")) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith("data: ")) {
        currentData += line.slice(6);
      } else if (line === "") {
        if (currentData) {
          try {
            onEvent(currentEvent || "message", JSON.parse(currentData));
          } catch (e) {
            onEvent(currentEvent || "message", currentData);
          }
        }
        currentEvent = "";
        currentData = "";
      }
    }
  }

  function pump() {
    reader.read().then(({ done, value }) => {
      if (done) {
        processBuffer();
        onDone();
        return;
      }
      buffer += decoder.decode(value, { stream: true });
      processBuffer();
      pump();
    }).catch((err) => {
      onError(err);
    });
  }

  pump();
}

async function openStream(method, path, opts = {}) {
  const config = getBackendConfig();
  if (!config) throw new Error("Backend not configured.");

  const url = buildUrl(config.url, path, opts.query);
  const headers = buildHeaders(config);
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";

  const portName = "aiBackendStream:" + Date.now() + ":" + Math.random().toString(36).slice(2, 8);
  const port = chrome.runtime.connect({ name: portName });
  const abortController = new AbortController();

  const streamPromise = new Promise((resolve, reject) => {
    const chunks = [];

    port.onMessage.addListener((msg) => {
      if (msg.type === "chunk") {
        if (opts.onRawChunk) opts.onRawChunk(msg.data);
        chunks.push(msg.data);
      } else if (msg.type === "event") {
        if (opts.onEvent) opts.onEvent(msg.event, msg.data);
      } else if (msg.type === "done") {
        if (opts.onDone) opts.onDone();
        resolve(chunks.join(""));
      } else if (msg.type === "error") {
        if (opts.onError) opts.onError(new Error(msg.error));
        reject(new Error(msg.error));
      }
    });

    port.onDisconnect.addListener(() => {
      if (abortController.signal.aborted) return;
      reject(new Error("Stream disconnected"));
    });

    port.postMessage({
      type: "start",
      method: method || "POST",
      url,
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
  });

  return {
    port,
    abort: () => {
      abortController.abort();
      port.postMessage({ type: "abort" });
      port.disconnect();
    },
    result: streamPromise,
  };
}

export async function health() {
  const config = getBackendConfig();
  if (!config) return { status: "unconfigured" };

  try {
    _setStatus(ConnectionStatus.CONFIGURING);
    const data = await retryWithBackoff(() =>
      sendBackgroundRequest("GET", "/api/v1/health", { timeout: 10000 })
    );
    _setStatus(ConnectionStatus.CONNECTED);
    return { status: "ok", data };
  } catch (e) {
    if (e.message?.includes("timed out")) {
      _setStatus(ConnectionStatus.RECONNECTING);
      return { status: "timeout", error: e.message };
    }
    _setStatus(ConnectionStatus.OFFLINE);
    return { status: "error", error: e.message };
  }
}

export async function chat(messages, opts = {}) {
  const body = { messages };
  if (opts.context) body.context = opts.context;
  if (opts.conversationId) body.conversation_id = opts.conversationId;
  return sendBackgroundRequest("POST", "/api/v1/ai/chat", { body, timeout: opts.timeout });
}

export function streamChat(messages, opts = {}) {
  const body = { messages, stream: true };
  if (opts.context) body.context = opts.context;
  if (opts.conversationId) body.conversation_id = opts.conversationId;
  return openStream("POST", "/api/v1/ai/chat", { body, ...opts });
}

export async function analyze(query, opts = {}) {
  const body = { query };
  if (opts.context) body.context = opts.context;
  if (opts.componentId) body.component_id = opts.componentId;
  return sendBackgroundRequest("POST", "/api/v1/ai/analyze", { body, timeout: opts.timeout });
}

export async function getConversations(limit) {
  return sendBackgroundRequest("GET", "/api/v1/ai/conversations", {
    query: { limit: limit || 20 },
  });
}

export async function getConversation(id) {
  return sendBackgroundRequest("GET", `/api/v1/ai/conversations/${id}`);
}

export async function deleteConversation(id) {
  return sendBackgroundRequest("DELETE", `/api/v1/ai/conversations/${id}`);
}

export async function updateSettings(settings) {
  return sendBackgroundRequest("PUT", "/api/v1/ai/settings", { body: settings });
}

export async function getCapabilities() {
  const config = getBackendConfig();
  if (!config) return { available: false, tools: [], version: null };
  try {
    const data = await sendBackgroundRequest("GET", "/api/v1/ai/tools");
    return { available: true, tools: data.tools || data, version: null };
  } catch (e) {
    return { available: false, tools: [], version: null, error: e.message };
  }
}

let _healthTimer = null;

export function startHealthMonitor() {
  stopHealthMonitor();
  health().catch(() => {});
  _healthTimer = setInterval(() => {
    health().catch(() => {});
  }, HEALTH_CHECK_INTERVAL);
}

export function stopHealthMonitor() {
  if (_healthTimer) {
    clearInterval(_healthTimer);
    _healthTimer = null;
  }
}
