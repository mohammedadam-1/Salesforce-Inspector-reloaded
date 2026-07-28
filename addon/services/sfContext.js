/* ──────────────────────────────────────────────
   sfContext — Salesforce Context Extraction Script
   ──────────────────────────────────────────────
   Injected into Salesforce pages to extract:
   - Current page URL and type
   - Current object/record
   - Setup area
   - User and org info (from localStorage)
   
   Communicates with the side panel via
   chrome.runtime.sendMessage.
   
   No API calls to Salesforce. Pure extraction.
   ────────────────────────────────────────────── */

import { extractPageContext, getRecordNameFromDom, isSalesforcePage } from "../context/PageContext.js";

let lastContext = null;
let lastContextStr = null;
let debounceTimer = null;
let pollingTimer = null;
let domObserver = null;
let urlObserver = null;
let destroyed = false;

function getSfHost() {
  return location.hostname;
}

function getCachedOrgInfo() {
  const host = getSfHost();
  const orgId = localStorage.getItem(host + "_orgId");
  const userId = localStorage.getItem(host + "_userId");
  const orgName = localStorage.getItem(host + "_orgName");
  return { orgId, userId, orgName };
}

function buildContext() {
  const url = location.href;
  const pageContext = extractPageContext(url);
  const recordName = getRecordNameFromDom();
  const orgInfo = getCachedOrgInfo();

  return {
    type: "ai_context_update",
    context: {
      ...pageContext,
      recordName,
      orgId: orgInfo.orgId,
      userId: orgInfo.userId,
      orgName: orgInfo.orgName,
      sfHost: getSfHost(),
    },
  };
}

function sendContext() {
  if (destroyed) return;
  const context = buildContext();
  const str = JSON.stringify(context);
  if (str === lastContextStr) return;

  lastContext = context;
  lastContextStr = str;
  try {
    if (typeof chrome !== "undefined" && chrome.runtime?.id) {
      chrome.runtime.sendMessage(context).catch(() => {});
    }
  } catch (e) {
    /* Extension context may be invalidated */
  }
}

function debouncedSend() {
  if (destroyed) return;
  if (debounceTimer) clearTimeout(debounceTimer);
  debounceTimer = setTimeout(sendContext, 300);
}

function watchUrlChanges() {
  let previousUrl = location.href;
  urlObserver = new MutationObserver(() => {
    const currentUrl = location.href;
    if (currentUrl !== previousUrl) {
      previousUrl = currentUrl;
      debouncedSend();
    }
  });

  urlObserver.observe(document.querySelector("head") || document.documentElement, {
    childList: true,
    subtree: true,
    attributes: false,
  });

  window.addEventListener("popstate", debouncedSend);
  window.addEventListener("pushstate", debouncedSend);
  window.addEventListener("hashchange", debouncedSend);

  pollingTimer = setInterval(() => {
    if (destroyed) return;
    const current = location.href;
    if (current !== previousUrl) {
      previousUrl = current;
      debouncedSend();
    }
  }, 2000);
}

function watchDomChanges() {
  const recordNameSelector = [
    ".recordName h1",
    ".slds-page-header__title",
    "[data-aura-class='forceDetailPanelDesktop'] h1",
    ".uiOutputText",
  ].join(",");

  domObserver = new MutationObserver((mutations) => {
    for (const m of mutations) {
      if (m.type === "childList" && m.addedNodes.length > 0) {
        for (const node of m.addedNodes) {
          if (node.nodeType === 1 && (node.matches?.(recordNameSelector) || node.querySelector?.(recordNameSelector))) {
            debouncedSend();
            return;
          }
        }
      }
    }
  });

  domObserver.observe(document.body, {
    childList: true,
    subtree: true,
  });
}

function cleanup() {
  destroyed = true;
  if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null; }
  if (pollingTimer) { clearInterval(pollingTimer); pollingTimer = null; }
  if (urlObserver) { urlObserver.disconnect(); urlObserver = null; }
  if (domObserver) { domObserver.disconnect(); domObserver = null; }
  window.removeEventListener("popstate", debouncedSend);
  window.removeEventListener("pushstate", debouncedSend);
  window.removeEventListener("hashchange", debouncedSend);
  lastContext = null;
  lastContextStr = null;
}

function init() {
  if (!isSalesforcePage(location.href)) return;

  setTimeout(sendContext, 500);
  watchUrlChanges();
  watchDomChanges();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}

window.__sfContextCleanup = cleanup;
