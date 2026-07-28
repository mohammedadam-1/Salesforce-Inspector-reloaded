/* ──────────────────────────────────────────────
   PageContext — Salesforce URL & DOM Parser
   ──────────────────────────────────────────────
   Extracts current page context from URL and DOM.
   No API calls. No side effects. Pure extraction.
   ────────────────────────────────────────────── */

const SETUP_PATTERNS = {
  "ObjectManager": "object-manager",
  "FieldsAndRelationships": "field-definition",
  "ValidationRules": "validation-rule",
  "ApexClasses": "apex-class",
  "ApexTriggers": "apex-trigger",
  "Flows": "flow-builder",
  "PermissionSets": "permission-set",
  "Profiles": "profile",
  "LightningPages": "lightning-page",
  "StaticResources": "static-resource",
  "EmailTemplates": "email-template",
  "CustomTabs": "custom-tab",
  "CustomLabels": "custom-label",
  "RecordTypes": "record-type",
};

function getSetupArea(url) {
  for (const [pattern, type] of Object.entries(SETUP_PATTERNS)) {
    if (url.includes(pattern)) return type;
  }
  if (url.includes("/lightning/setup/")) return "setup-home";
  return null;
}

function getSObjectFromUrl(url) {
  const match = url.match(/ObjectManager\/([^/]+)/);
  return match ? match[1] : null;
}

function getRecordIdFromUrl(url) {
  const match = url.match(/\/r\/[^/]+\/([a-zA-Z0-9]{15,18})\/?/);
  if (match) return match[1];
  const queryMatch = url.match(/[?&]id=([a-zA-Z0-9]{15,18})/);
  if (queryMatch) return queryMatch[1];
  return null;
}

function getRecordIdFromDom() {
  const el = document.querySelector("[data-recordid], [data-record-id]");
  if (el) return el.getAttribute("data-recordid") || el.getAttribute("data-record-id");
  const input = document.querySelector("input[name='recordId']");
  if (input) return input.value;
  return null;
}

function getPageType(url) {
  if (url.includes("/lightning/setup/")) return "setup";
  if (url.match(/\/lightning\/r\/[^/]+\//)) return "record";
  if (url.includes("/lightning/page/")) return "app";
  if (url.includes("/lightning/n/")) return "app";
  return "home";
}

function getInstance(url) {
  const match = url.match(/https:\/\/([^.]+)/);
  return match ? match[1] : null;
}

export function extractPageContext(url) {
  if (!url) return null;

  const pageType = getPageType(url);
  const setupArea = getSetupArea(url);
  const sobject = getSObjectFromUrl(url);
  const instance = getInstance(url);
  const recordId = getRecordIdFromUrl(url) || getRecordIdFromDom();

  return {
    url,
    pageType,
    setupArea,
    sobject,
    recordId,
    instance,
  };
}

export function getRecordNameFromDom() {
  const selectors = [
    ".recordName h1",
    ".slds-page-header__title",
    "[data-aura-class='forceDetailPanelDesktop'] h1",
    ".uiOutputText",
    ".viewHeader h1",
    ".bBody h1.recordName",
    "h1.recordName",
  ];
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el && el.textContent.trim()) return el.textContent.trim();
  }
  return null;
}

export function isSalesforcePage(url) {
  if (!url) return false;
  return /\.(salesforce\.com|force\.com|cloudforce\.com|crmforce\.com|visualforce\.com|salesforce\.mil|crmforce\.mil)/.test(url);
}

export function isSetupPage(url) {
  return url ? url.includes("/lightning/setup/") : false;
}
