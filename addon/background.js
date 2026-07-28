
let sfHost;

function cookiesGet(details) {
  return new Promise(resolve => chrome.cookies.get(details, resolve));
}

async function resolveSessionCookie(sfHost, sender) {
  if (!sfHost) {
    throw new Error("Salesforce host is required.");
  }
  const storeId = sender?.tab?.cookieStoreId;
  const details = {url: "https://" + sfHost, name: "sid"};
  if (storeId) {
    details.storeId = storeId;
  }
  return cookiesGet(details);
}

async function parseResponseBody(response) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response.text();
}

function extractErrorMessage(data, fallbackMessage) {
  if (!data) {
    return fallbackMessage;
  }
  if (typeof data === "string") {
    return data || fallbackMessage;
  }
  if (data.error?.message) {
    return data.error.message;
  }
  if (data.error_description) {
    return data.error_description;
  }
  if (Array.isArray(data) && data.length > 0) {
    return data.map(entry => entry.message || entry.errorCode).filter(Boolean).join(", ") || fallbackMessage;
  }
  return fallbackMessage;
}

async function performSalesforceRestRequest(request, sender) {
  const sessionCookie = request.sessionId
    ? {value: request.sessionId}
    : await resolveSessionCookie(request.sfHost, sender);

  if (!sessionCookie?.value) {
    throw new Error("Salesforce session not found.");
  }

  const url = new URL(request.path, "https://" + request.sfHost);
  const headers = {
    Accept: request.accept || "application/json",
    Authorization: "Bearer " + sessionCookie.value,
    ...(request.headers || {})
  };
  let body = request.body;
  if (body !== undefined && body !== null && request.method !== "GET" && request.method !== "HEAD") {
    if (request.bodyType === "raw") {
      body = request.body;
    } else {
      headers["Content-Type"] = headers["Content-Type"] || "application/json";
      body = JSON.stringify(request.body);
    }
  } else {
    body = undefined;
  }

  const response = await fetch(url.toString(), {
    method: request.method || "GET",
    headers,
    body
  });
  const data = await parseResponseBody(response);

  if (!response.ok) {
    throw new Error(extractErrorMessage(data, `Salesforce request failed (${response.status})`));
  }

  return {
    success: true,
    status: response.status,
    data
  };
}

async function performAiBackendRequest(request) {
  const { method, url, headers, body, timeout } = request;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout || 30000);

  try {
    const response = await fetch(url, {
      method: method || "GET",
      headers: headers || {},
      body: body || undefined,
      signal: controller.signal,
    });
    clearTimeout(timer);
    const data = await parseResponseBody(response);
    if (!response.ok) {
      throw new Error(extractErrorMessage(data, `Backend request failed (${response.status})`));
    }
    return { success: true, status: response.status, data };
  } catch (e) {
    clearTimeout(timer);
    if (e.name === "AbortError") {
      throw new Error("Request timed out");
    }
    throw e;
  }
}

const _streamControllers = new Map();

function handleStreamPort(port) {
  let controller = null;

  port.onMessage.addListener(async (msg) => {
    if (msg.type === "start") {
      try {
        controller = new AbortController();
        const streamId = port.name;
        _streamControllers.set(streamId, controller);

        const response = await fetch(msg.url, {
          method: msg.method || "POST",
          headers: msg.headers || {},
          body: msg.body || undefined,
          signal: controller.signal,
        });

        if (!response.ok) {
          const data = await parseResponseBody(response);
          port.postMessage({ type: "error", error: extractErrorMessage(data, `Backend stream failed (${response.status})`) });
          _streamControllers.delete(streamId);
          return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const text = decoder.decode(value, { stream: true });
          port.postMessage({ type: "chunk", data: text });
        }

        port.postMessage({ type: "done" });
      } catch (e) {
        if (e.name === "AbortError") return;
        try { port.postMessage({ type: "error", error: e.message }); } catch (e2) { /* port may be closed */ }
      } finally {
        if (port.name) _streamControllers.delete(port.name);
      }
    } else if (msg.type === "abort") {
      if (controller) controller.abort();
    }
  });

  port.onDisconnect.addListener(() => {
    if (controller) controller.abort();
    if (port.name) _streamControllers.delete(port.name);
  });
}

async function performAiRequest(request) {
  if (!request.apiKey) {
    throw new Error("Groq API key is not configured.");
  }

  const response = await fetch(request.endpoint || "https://api.groq.com/openai/v1/responses", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer " + request.apiKey
    },
    body: JSON.stringify(request.payload || {})
  });

  const data = await parseResponseBody(response);

  if (!response.ok) {
    throw new Error(extractErrorMessage(data, `AI request failed (${response.status})`));
  }

  return {
    success: true,
    status: response.status,
    data
  };
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  // Perform cookie operations in the background page, because not all foreground pages have access to the cookie API.
  // Firefox does not support incognito split mode, so we use sender.tab.cookieStoreId to select the right cookie store.
  // Chrome does not support sender.tab.cookieStoreId, which means it is undefined, and we end up using the default cookie store according to incognito split mode.
  if (request.message == "getSfHost") {
    const currentDomain = new URL(request.url).hostname;
    // When on a *.visual.force.com page, the session in the cookie does not have API access,
    // so we read the corresponding session from *.salesforce.com page.
    // The first part of the session cookie is the OrgID,
    // which we use as key to support being logged in to multiple orgs at once.
    // http://salesforce.stackexchange.com/questions/23277/different-session-ids-in-different-contexts
    // There is no straight forward way to unambiguously understand if the user authenticated against salesforce.com or cloudforce.com
    // (and thereby the domain of the relevant cookie) cookie domains are therefore tried in sequence.
    chrome.cookies.get({url: request.url, name: "sid", storeId: sender?.tab?.cookieStoreId}, cookie => {
      if (!cookie || currentDomain.endsWith(".mcas.ms")) { //Domain used by Microsoft Defender for Cloud Apps, where sid exists but cannot be read
        sendResponse(currentDomain);
        return;
      }
      const [orgId] = cookie.value.split("!");
      const orderedDomains = ["salesforce.com", "cloudforce.com", "salesforce.mil", "cloudforce.mil", "sfcrmproducts.cn", "force.com"];

      orderedDomains.forEach(currentDomain => {
        chrome.cookies.getAll({name: "sid", domain: currentDomain, secure: true, storeId: sender.tab.cookieStoreId}, cookies => {

          let sessionCookie = cookies.find(c => c.value.startsWith(orgId + "!") && c.domain != "help.salesforce.com");
          if (sessionCookie) {
            sendResponse(sessionCookie.domain);
          }
        });
      });
    });
    return true; // Tell Chrome that we want to call sendResponse asynchronously.
  }
  if (request.message == "salesforceRestRequest") {
    performSalesforceRestRequest(request, sender)
      .then(sendResponse)
      .catch(error => sendResponse({success: false, error: error.message}));
    return true;
  }
  if (request.message == "userInsightAiRequest") {
    performAiRequest(request)
      .then(sendResponse)
      .catch(error => sendResponse({success: false, error: error.message}));
    return true;
  }
  if (request.message == "aiBackendRequest") {
    performAiBackendRequest(request)
      .then(sendResponse)
      .catch(error => sendResponse({success: false, error: error.message}));
    return true;
  }
  if (request.message == "getSession") {
    sfHost = request.sfHost;
    chrome.cookies.get({url: "https://" + request.sfHost, name: "sid", storeId: sender?.tab?.cookieStoreId}, sessionCookie => {
      if (!sessionCookie) {
        sendResponse(null);
        return;
      }
      let session = {key: sessionCookie.value, hostname: sessionCookie.domain};
      sendResponse(session);
    });
    return true; // Tell Chrome that we want to call sendResponse asynchronously.
  } else if (request.message == "createWindow") {
    const brow = typeof browser === "undefined" ? chrome : browser;
    brow.windows.create({
      url: request.url,
      incognito: request.incognito ?? false
    });
  } else if (request.message == "reloadPage") {
    chrome.tabs.query({active: true, currentWindow: true}, (tabs) => {
      chrome.tabs.reload(tabs[0].id);
    });
  }
  return false;
});
chrome.action.onClicked.addListener(() => {
  chrome.runtime.sendMessage({
    msg: "shortcut_pressed", sfHost, command: "open-popup"
  }).catch(() => {
    // No listener open yet — this is expected if popup isn't active
  });
});
chrome.commands?.onCommand.addListener((command) => {
  if (command.startsWith("link-")){
    let link;
    switch (command){
      case "link-setup":
        link = "/lightning/setup/SetupOneHome/home";
        break;
      case "link-home":
        link = "/";
        break;
      case "link-dev":
        link = "/_ui/common/apex/debug/ApexCSIPage";
        break;
    }
    chrome.tabs.create({
      url: `https:///${sfHost}${link}`
    });

  } else if (command.startsWith("open-")){
    chrome.runtime.sendMessage({
      msg: "shortcut_pressed", command, sfHost
    }).catch(() => {
    // No listener — expected
    });
  } else {
    chrome.tabs.create({
      url: `chrome-extension://${chrome.i18n.getMessage("@@extension_id")}/${command}.html?host=${sfHost}`
    });
  }
});

chrome.runtime.onInstalled.addListener(async (details) => {
  if (details.reason === "install") {
    chrome.tabs.create({
      url: "https://tprouvot.github.io/Salesforce-Inspector-reloaded/welcome/"
    });
  } else if (details.reason === "update" && details.previousVersion?.startsWith("2.0")) {
    //TODO delete clearSobjectsListCache after 2.0.1 release, only for upgrade from 2.0.0 to 2.0.1
    await clearSobjectsListCache();
  }
});

async function clearSobjectsListCache() {
  try {
    const storage = (typeof chrome !== "undefined" && chrome.storage) ? chrome.storage : browser.storage;
    if (!storage?.local) return;
    const allData = await storage.local.get(null);
    const keysToRemove = Object.keys(allData || {}).filter(key =>
      key === "cache_sobjectsList"
    );
    if (keysToRemove.length > 0) {
      await storage.local.remove(keysToRemove);
    }
  } catch (e) {
    console.error("Error clearing sobjectsList cache on update:", e);
  }
}
chrome.runtime.onConnect.addListener((port) => {
  if (port.name && port.name.startsWith("aiBackendStream:")) {
    handleStreamPort(port);
  }
});

chrome.runtime.setUninstallURL("https://forms.gle/y7LbTNsFqEqSrtyc6");
