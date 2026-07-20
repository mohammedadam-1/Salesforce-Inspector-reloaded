# Phase 1: Existing Extension Analysis

> **Status**: Complete  
> **Objective**: Comprehensive analysis of the `addon/` codebase to understand architecture, communication patterns, Salesforce integration points, session management, component reuse potential, and integration risks before building the Enterprise Workspace.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [File Inventory & Dependency Graph](#2-file-inventory--dependency-graph)
3. [Page Routing & Entry Points](#3-page-routing--entry-points)
4. [Message Flow Architecture](#4-message-flow-architecture)
5. [Salesforce Communication Points](#5-salesforce-communication-points)
6. [Session Management](#6-session-management)
7. [Component Inventory](#7-component-inventory)
8. [State Management Patterns](#8-state-management-patterns)
9. [Build & Release Pipeline](#9-build--release-pipeline)
10. [Legacy Patterns & Technical Debt](#10-legacy-patterns--technical-debt)
11. [Security Analysis](#11-security-analysis)
12. [Reusability Assessment](#12-reusability-assessment)
13. [Integration Points for Phase 2](#13-integration-points-for-phase-2)
14. [Risks & Trade-offs](#14-risks--trade-offs)
15. [Phase 2 Recommendations](#15-phase-2-recommendations)

---

## 1. Architecture Overview

### Extension Type
- **Chrome**: Manifest V3 (service worker, host_permissions, action)
- **Firefox**: Manifest V2 (background scripts, permissions)
- **Browser**: MV3 for Chrome, MV2 for Firefox via separate manifest

### High-Level Structure
```
addon/
├── manifest.json              # Chrome MV3 manifest
├── manifest-firefox.json      # Firefox MV2 manifest
├── *.html (21 pages)          # Each feature = standalone HTML page
├── *.js   (38 JS files)       # 21 feature modules + 17 shared/support
├── *.css  (20+ CSS files)     # Per-page CSS + shared SLDS/globals
├── components/                # 8 reusable React components
├── lib/                       # Vendored dependencies
│   ├── cometd/                # CometD streaming library (13 files)
│   └── prism/                 # Syntax highlighter (2 files)
└── styles/
    ├── slds/                  # Salesforce Lightning Design System
    └── sfir.css               # Global extension styles
```

### Key Properties
- **No bundler** — raw ES module `<script type="module">` + global scripts
- **No JSX** — `const h = React.createElement` throughout
- **No Router** — each HTML page is its own route; navigation via postMessage
- **No Framework State Management** — model-view pattern with manual `didUpdate()` callbacks
- **Singleton Pattern** — `sfConn` object in `inspector.js` shared across all pages
- **l10n via localStorage** — all user preferences, cache, API keys in localStorage

---

## 2. File Inventory & Dependency Graph

### 2.1 Page Modules (21 HTML → JS pairs)

| HTML Page | JS Module | Lines | Purpose |
|---|---|---|---|
| `popup.html` | `popup.js` | ~1,350 | Main popup SPA with 5 tabs |
| `data-export.html` | `data-export.js` | 2,213 | SOQL query builder & data export |
| `data-import.html` | `data-import.js` | 1,440 | CSV/Excel data import |
| `inspect.html` | `inspect.js` | 2,571 | SObject record inspector |
| `rest-explore.html` | `rest-explore.js` | 825 | REST API explorer |
| `field-creator.html` | `field-creator.js` | 1,636 | Custom field creation wizard |
| `flow-scanner.html` | `flow-scanner.js` | 2,168 | Flow metadata analysis |
| `debug-log.html` | `debug-log.js` | 1,871 | Apex debug log viewer |
| `event-monitor.html` | `event-monitor.js` | 1,297 | Platform event subscription (CometD) |
| `user-insight-ai.html` | `user-insight-ai.js` | 430 | AI-powered user search |
| `explore-api.html` | `explore-api.js` | 491 | API response explorer |
| `options.html` | `options.js` | ~1,100 | Settings (13 tabs) |
| `metadata-retrieve.html` | `metadata-retrieve.js` | ~1,500 | Metadata retrieval |
| `metadata-retrieve-legacy.html` | `metadata-retrieve-legacy.js` | ~800 | Legacy metadata view |
| `dependencies-explorer.html` | `dependencies-explorer.js` | 518 | Dep graph (backend service) |
| `limits.html` | `limits.js` | ~600 | Org limits |
| `api-statistics.html` | `api-statistics.js` | ~600 | API debug stats |
| `schema-explorer.html` | (dynamic bootstrap) | — | Schema browser |
| `field-analysis.html` | `field-analysis.js` | ~600 | AI field dependency analysis |
| `ai-console.html` | `ai-console.js` | ~500 | AI agent console |
| `test-popup.html` | `test-popup.js` | — | Test framework |

### 2.2 Shared Library Files

| File | Lines | Purpose |
|---|---|---|
| `background.js` | ~1,200 | Service worker — message router, session resolution, API proxy |
| `button.js` | ~600 | Content script — floating button, popup management |
| `inject.js` | 39 | Lightning navigation capture (injected into Salesforce) |
| `inspector.js` | ~800 | **Core singleton** — sfConn, session management, REST/Tooling/Query API proxy |
| `utils.js` | ~1,200 | Shared utilities — DataCache, UserInfoModel, OAuth PKCE, clipboard, etc. |
| `links.js` | ~600 | Static Salesforce setup navigation links |
| `setup-links.js` | ~45 | Dynamic setup link generation via Tooling API |
| `data-load.js` | ~800 | DescribeInfo, scroll table, enumerable utilities |
| `salesforce_service.js` | ~370 | Salesforce data layer for User Insight AI |
| `backend_service.js` | ~195 | External backend service client |
| `ai_service.js` | ~540 | Groq/OpenAI LLM API client |
| `csv-parse.js` | — | CSV parsing library |
| `flow-scanner-rules.js` | — | Flow scanner rule definitions |
| `inspect-inline.js` | — | Inline inspect content script |

### 2.3 Dependency Graph

```
All HTML pages
  ├── react.js / react-dom.js (dev) → react.min.js / react-dom.min.js (release)
  ├── button.js (loaded by all feature pages)
  │
  ├── Via <script type="module">:
  │   └── {page-module}.js
  │       ├── inspector.js (sfConn singleton)
  │       │   └── (uses chrome.runtime.sendMessage → background.js)
  │       ├── utils.js (shared utilities)
  │       ├── data-load.js (describe info, tables)
  │       ├── components/* (React components)
  │       └── (feature-specific imports)
  │
  ├── Via <script> (non-module):
  │   ├── lib/flow-scanner-core.js (Flow Scanner only)
  │   └── lib/prism/prism.js (syntax highlighting pages)
  │
  └── CSS:
      ├── styles/slds/slds.css (SLDS — all pages)
      ├── styles/sfir.css (global — most pages)
      ├── components/*.css (component-specific)
      └── {page}.css (page-specific)
```

---

## 3. Page Routing & Entry Points

### 3.1 Extension Routes

The extension uses a **flat HTML file routing** pattern — each feature is a standalone HTML page opened via:

1. **Popup**: `popup.html` — loaded in iframe by `button.js` content script
2. **`chrome-extension://` links**: Feature pages opened via `chrome.tabs.create({url: chrome.runtime.getURL("data-export.html")})`
3. **Keyboard shortcuts**: 18 shortcuts defined in manifest, handled in `background.js`
4. **Context menu**: Right-click → "Inspect in Salesforce Inspector"
5. **Options page**: `chrome.runtime.openOptionsPage()` → `options.html`

### 3.2 Popup Navigation (popup.js)

The popup is the main UI entry point. It uses a **manual tab system** (div show/hide, no router):

```
Popup Tabs:
├── Object Tab (sobject)     — search/select sObject, quick actions
├── Users Tab (users)        — user search, login-as, password reset
├── Shortcuts Tab (shortcuts) — Salesforce setup navigation links
├── Org Tab (org)            — org info, limits, API stats
└── Extensions Tab           — AI console link, etc.
```

Navigation between feature pages happens via:
- `window.open(chrome.runtime.getURL("feature.html"), "_blank")`
- `postMessage({message: "navigate", url: "..."})` from popup to parent

### 3.3 New Window vs Inline

Most features open in new tabs/windows (not inline in the popup). This means:
- Each feature page initializes its own `sfConn` session
- Session establishment happens on every page load
- Pages are isolated — no shared React tree, no shared state

---

## 4. Message Flow Architecture

### 4.1 Communication Layers

```
┌─────────────────────────────────────────────────────────────────┐
│                        Salesforce.com                           │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  REST / Tooling / Query API / Metadata API / CometD     │    │
│  └─────────────────────────────────────────────────────────┘    │
│                            ▲                                    │
│                            │ HTTPS (direct for CometD)          │
│                            │ HTTPS (proxied for REST)           │
└────────────────────────────┼────────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              │       Background SW          │
              │      (background.js)         │
              │                              │
              │  - Session resolution        │
              │  - REST/Tooling proxy        │
              │  - Keyboard shortcuts        │
              │  - Extension lifecycle       │
              │  - Message router (20+ msgs) │
              └──────────────┬──────────────┘
                             │
              chrome.runtime.sendMessage / onMessage
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
  ┌─────┴─────┐      ┌──────┴──────┐      ┌──────┴──────┐
  │   Popup   │      │  Feature    │      │  Content    │
  │ (popup.js)│      │  Pages      │      │  Scripts    │
  │  iframe   │      │  21 HTML    │      │ (button.js) │
  └───────────┘      │  pages      │      └─────────────┘
                     └─────────────┘
```

### 4.2 Message Types (background.js router)

The background service worker handles 20+ message types:

| Message | Source | Destination | Description |
|---|---|---|---|
| `getSfHost` | Any page | → background | Get current Salesforce hostname |
| `getSession` | Any page | → background | Resolve session (cookie or OAuth) |
| `salesforceRestRequest` | Feature pages | → background → SF | Salesforce REST/Tooling/Query API |
| `userInsightAiRequest` | AI features | → background → Groq | AI LLM API call |
| `backendRequest` | Feature pages | → background → Backend | Custom backend API call |
| `getApiUsageData` | Feature pages | → background → SF | API usage stats |
| `getUserInfo` | Feature pages | → background → SF | Current user info |
| `inspectSObject` | Content script | → background | Record inspection |
| `setIcon` | Feature pages | → background | Update extension icon |
| `openOptionsPage` | Any page | → background | Open options |
| `reloadExtension` | Any page | → background | Reload extension |

### 4.3 PostMessage Protocol (popup ↔ content script ↔ page)

```
Salesforce Page (top window)
  └── button.js (content script, injected via manifest)
       ├── Creates floating #insext button
       ├── Creates #insext-popup iframe → loads popup.html
       └── postMessage bridge:
           ├── popup → button: {message: "close", "resize", "init"}
           └── button → popup: {message: "init", context, url, recordId}
                └── Also forwards lightningNavigate events from inject.js
```

---

## 5. Salesforce Communication Points

### 5.1 Classification

| Category | Files | Description |
|---|---|---|
| **Proxy Only** (safe) | `data-export.js`, `data-import.js`, `rest-explore.js`, `inspect.js`, `field-creator.js`, `flow-scanner.js`, `debug-log.js`, `explore-api.js`, `setup-links.js`, `metadata-retrieve.js`, `limits.js`, `schema-explorer.js` | All requests go through `sfConn.rest()` → `chrome.runtime.sendMessage` → `background.js` → HTTPS to Salesforce |
| **Direct** (⚠ risk) | `event-monitor.js` | CometD streaming connects **directly** to Salesforce (bypasses background proxy) |
| **External Only** (no SF) | `backend_service.js`, `dependencies-explorer.js` | Uses `fetch()` to a customer-hosted backend server (no Salesforce calls) |
| **Hybrid** (SF + AI) | `user-insight-ai.js`, `salesforce_service.js`, `ai_service.js` | Salesforce via proxy, AI via `chrome.runtime.sendMessage` to background → Groq |

### 5.2 `sfConn` Singleton (inspector.js)

This is the critical integration point — every feature page imports it:

```javascript
import {sfConn, apiVersion} from "./inspector.js";

// Usage pattern:
sfConn.getSession(sfHost)       // Establish session (OAuth or cookie exchange)
sfConn.rest(url, options)       // REST API call (proxied)
sfConn.tooling(url, options)    // Tooling API call (proxied)
sfConn.query(soql)              // SOQL query (proxied)
sfConn.soap(payload)            // SOAP call (proxied)
sfConn.wsdl()                   // Retrieve WSDL
sfConn.streamApiQuery(query)    // Stream via Composite API
```

### 5.3 Three Salesforce Authentication Paths

| Path | How | When |
|---|---|---|
| **Cookie Exchange** | `chrome.cookies.get("sid")` → REST call to get OAuth token | When user is logged into Salesforce in browser |
| **OAuth PKCE** | Full OAuth PKCE flow via popup window | When cookie is not available (incognito, 3rd party) |
| **Refresh Token** | Stored access token reuse | Subsequent page loads |

---

## 6. Session Management

### 6.1 OAuth PKCE Flow (utils.js)

```
1. Generate code_verifier (Crypto.subtle) + code_challenge (SHA-256 base64url)
2. Store state in sessionStorage
3. Open popup to Salesforce authorize endpoint with:
   - response_type=code
   - client_id (from localStorage or hardcoded default)
   - redirect_uri = chrome.identity.getRedirectURL()
   - code_challenge (S256)
4. Popup callback page receives auth code in URL
5. Exchange code for tokens via POST to /services/oauth2/token
6. Store access_token + refresh_token in localStorage (per sfHost)
```

### 6.2 Session Resolution Flow (background.js)

```
1. Feature page opens
2. Page calls sfConn.getSession(sfHost)
3. sfConn sends chrome.runtime.sendMessage({message: "getSession", sfHost})
4. background.js:
   a. Check localStorage for existing access_token
   b. If valid → return sessionId + instanceUrl
   c. If expired → try refresh_token
   d. If no token → chrome.cookies.get({url: sfHost, name: "sid"})
   e. If cookie found → exchange for OAuth token
   f. If no cookie → trigger OAuth PKCE flow
5. Return sessionId to caller
```

### 6.3 Session Lifecycle Issues

- **No session persistence across page loads** — each feature page re-establishes session independently
- **`sfConn` singleton** — assumed to be initialized; no explicit initialization check
- **SessionId in chrome.runtime.sendMessage** — serialized in the message payload, visible to any extension listener
- **Tokens in localStorage** — access_token and refresh_token stored in plain text per sfHost key

---

## 7. Component Inventory

### 7.1 Existing Reusable Components (8 files)

| Component | Lines | Type | State | Dependencies |
|---|---|---|---|---|
| `AlertBanner.js` | 32 | PureComponent | None | React only |
| `ConfirmModal.js` | 236 | Component | Escape key listener | React only |
| `AgentforceModal.js` | 247 | Component | None (fully controlled) | React, ConfirmModal, utils.copyToClipboard |
| `Toast.js` | 64 | Component | None | React only |
| `Tooltip.js` | 74 | Component | Visibility state | React only |
| `ColorPicker.js` | 308 | Component | hue/sat/bright/hex | React only |
| `Spinner.js` | 62 | Function | None | React only |
| `PageHeader.js` | 195 | Function | Reads localStorage for colors | React only |

### 7.2 Component Patterns

- **No JSX** — all use `React.createElement` via `const h = ...`
- **SLDS classes** — consistent use of `slds-*` CSS classes
- **SVG sprites** — icons via `<svg><use xlinkHref="symbols.svg#iconName"/></svg>`
- **Global React** — `/* global React */` JSDoc, no ES import for React
- **Minimal internal state** — most are stateless/pure
- **No testing** — no component tests exist

### 7.3 Reusability for Enterprise Workspace

| Component | Reuse Option | Assessment |
|---|---|---|
| `AlertBanner` | **Full reuse** | Stateless, zero dependencies — copy as-is |
| `ConfirmModal` | **Full reuse** | No external deps — copy as-is |
| `AgentforceModal` | **Refactor needed** | Depends on `utils.copyToClipboard` — adapt import |
| `Spinner` | **Full reuse** | Pure function — copy as-is |
| `Toast` | **Full reuse** | Stateless — copy as-is |
| `Tooltip` | **Full reuse** | Self-contained — copy as-is |
| `ColorPicker` | **Full reuse** | Self-contained — copy as-is |
| `PageHeader` | **Rewrite** | Tightly coupled to localStorage + legacy org context |

---

## 8. State Management Patterns

### 8.1 Current Patterns

| Pattern | Used By | Description |
|---|---|---|
| **localStorage** | All pages | User preferences, cache, API keys, tokens, history |
| **React this.state** | All feature pages | UI state within page component |
| **Model class + didUpdate()** | All feature pages | Manual model-view binding pattern |
| **sfConn singleton** | All feature pages | Shared session state (global singleton) |
| **DataCache (utils.js)** | Most feature pages | TTL-based in-memory + localStorage cache |
| **StorageHistory** | Multiple pages | Query/event history in localStorage |

### 8.2 Model-View Pattern

```javascript
class Model {
  constructor(sfHost) {
    this.sfHost = sfHost;
    this.spinFor = createSpinForMethod(this);
    // ... business logic
  }
  didUpdate(cb) {
    if (this.reactCallback) this.reactCallback(cb);
  }
}

class App extends React.Component {
  constructor(props) {
    super(props);
    this.model = new Model(sfHost);
    this.model.reactCallback = (cb) => this.setState({}, cb);
  }
}
```

### 8.3 Issues with Current State Management

- **No unidirectional data flow** — model calls `setState` on React component
- **No immutability guarantees**
- **localStorage as database** — everything in localStorage with string keys (collision-prone)
- **No cross-page state sharing** — each page is fully isolated
- **No explicit initialization lifecycle** — `sfConn` assumed ready
- **No separation of concerns** — business logic mixed with rendering (2000+ line files)

---

## 9. Build & Release Pipeline

### 9.1 Build Script

```bash
npm run chrome-release-build
# → node scripts/release-build.js chrome
```

The build is a **copy + replace + zip** pipeline:

1. Empty `target/{browser}/dist/`
2. Copy `addon/` → `target/`, excluding tests, .zip, .xpi
3. Skip `react.js` and `react-dom.js` (dev editions)
4. For Firefox: overwrite manifest.json with manifest-firefox.json
5. Find-and-replace: `<script src="react.js">` → `<script src="react.min.js">` in all HTML
6. Optional: rename for BETA builds
7. Zip into `target/{browser}/{browser}-release-build-v{version}.zip`

### 9.2 Key Properties

- **No bundler** — no Webpack, Vite, Rollup, or Parcel
- **No transpilation** — ES modules used directly (no Babel)
- **No minification** — only react.min.js is pre-minified
- **No CSS processing** — raw CSS files
- **No tree-shaking** — entire files shipped even if partially used
- **No source maps**
- **No CI/CD pipeline** for extension builds

### 9.3 Dependencies

Zero runtime dependencies. Dev-only:
- `eslint` — linting
- `@playwright/test` — E2E testing
- `fs-extra`, `replace-in-file`, `zip-dir` — build script

---

## 10. Legacy Patterns & Technical Debt

### 10.1 Critical Issues

| Issue | Severity | Files Affected |
|---|---|---|
| **Monolithic files** (1,500-2,500 lines) | High | data-export (2,213), inspect (2,571), flow-scanner (2,168), debug-log (1,871), field-creator (1,636) |
| **Business logic mixed with rendering** | High | All feature pages — Model class and React App in same file |
| **No separation of concerns** | High | Model = data fetching + business logic + some view logic |
| **`sfConn` singleton coupling** | High | Every feature page; impossible to unit test without mocking entire module |
| **localStorage as database** | Medium | All pages — preference, cache, tokens, history all in string-keyed localStorage |
| **No error boundaries** | Medium | Uncaught exceptions crash the feature page |
| **Global React pattern** | Medium | `/* global React */` — no proper module imports |
| **No TypeScript** | Medium | 25,000+ lines of untyped JS |
| **No test coverage** | Medium | No unit tests for any feature page |
| **OAuth URL parsing in popup** | Medium | `popup.js` handles OAuth redirect in URL hash — fragile |
| **Random React key usage** | Low | `key: Math.random()` in some list renders — breaks reconciliation |

### 10.2 Code Smells

```javascript
// Pattern repeated across all pages:
sfConn.getSession(sfHost)
  .then(() => { /* start rendering */ });

// Manual state management:
model.reactCallback = (cb) => this.setState({}, cb);

// localStorage as global state:
localStorage.getItem(sfHost + Constants.CLIENT_ID)
localStorage.setItem("apiVersion", "62.0")

// No initialization check:
const session = sfConn.sessionId;  // Could be undefined

// Random keys for React lists:
key: Math.random()
```

---

## 11. Security Analysis

### 11.1 Findings

| Finding | Severity | Details |
|---|---|---|
| **API keys in localStorage** | **HIGH** | Groq API key, Backend API key stored in plain text in localStorage. Accessible to any JS running in an extension page context. |
| **Session token in message payloads** | **MEDIUM** | `sfConn.sessionId` serialized into `chrome.runtime.sendMessage` — visible to any extension with messaging permission. |
| **CometD direct connection** | **MEDIUM** | Events page connects directly to Salesforce with session token, bypassing background proxy. |
| **AI agent loop** | **MEDIUM** | `ai_service.js` runs up to 10 agent iterations with tool calls — potential for runaway queries or prompt injection. |
| **OAuth redirect URL** | **LOW** | OAuth PKCE flow uses `chrome.identity.getRedirectURL()` — unique per extension, but state in sessionStorage. |
| **CSV export** | **LOW** | BOM injection possible, but limited to download context. |
| **No HTTPS enforcement** | **LOW** | Backend URL is user-configured — no validation that it's HTTPS. |

### 11.2 Store Policies

The extension is a Chrome Web Store / Firefox Add-ons published extension. Compliance points:

- **Minimal host_permissions**: `*.salesforce.com/*` + `http://localhost:8000/` (explicit, not `<all_urls>`)
- **Storage**: Uses `storage` permission for `chrome.storage.local`
- **Cookies**: Uses `cookies` permission for session resolution
- **Side effects**: Passes review — no alarming patterns

---

## 12. Reusability Assessment

### 12.1 For Enterprise Workspace SPA

| Component/Module | Reuse Strategy | Effort |
|---|---|---|
| **React components** (8) | Copy + adapt imports | Low |
| **utils.js** | Copy selected functions (cache, clipboard, dates) | Medium |
| **data-load.js** | Copy DescribeInfo class | Medium |
| **inspector.js** (sfConn) | **Do not reuse** — replace with Axios + Zustand API layer | High |
| **background.js** router | **Do not reuse** — Enterprise uses direct API calls | High |
| **OAuth PKCE** | Reuse flow pattern, re-implement for workspace | Medium |
| **Salesforce service layer** | Build new — typed API client with Zustand | High |
| **UI styling (SLDS)** | **Full reuse** — SLDS will be workspace design system | Low |
| **CometD streaming** | Reuse cometd library, wrap in workspace service | Medium |
| **AI service** | Refactor — move API key handling to workspace config | Medium |
| **Backend service** | Refactor — type the API client | Medium |

### 12.2 Must Keep as Legacy (no migration)

These are fundamental to the existing extension and should be left untouched:
- `manifest.json` — the extension entry point
- `background.js` — service worker (minus the 3 additive hooks)
- `button.js` — content script creating the popup
- `inject.js` — Lightning navigation
- All 21 feature pages (continue to work as-is)
- Existing `inspector.js`, `utils.js`, etc.

### 12.3 Must Never Be in Enterprise Workspace

- Plain-text API key storage → must use workspace config encryption
- Direct `sfConn` singleton → use typed Zustand API layer
- localStorage as primary state → use Zustand stores
- `Math.random()` keys → use stable IDs
- Global React → use proper ES imports
- No error handling → use react-error-boundary

---

## 13. Integration Points for Phase 2

### 13.1 The 3 Additive Integration Points (from Phase 0)

| # | File | Change | Description |
|---|---|---|---|
| 1 | `manifest.json` | Add `"addon/enterprise/index.html"` to `web_accessible_resources` | Make the SPA accessible |
| 2 | `button.js` | Add navigation option in popup to open Enterprise Workspace | Entry point from existing extension |
| 3 | `background.js` | Add message handler for `openEnterpriseWorkspace` | Route open requests |

### 13.2 Additional Hooks Discovered During Analysis

| # | File | Potential Hook | Description |
|---|---|---|---|
| 4 | `manifest.json` | Add content_scripts or host_permissions | If workspace needs additional Salesforce access |
| 5 | `background.js` | Add message type for workspace ↔ Salesforce proxy | If workspace needs to reuse session resolution |
| 6 | `background.js` | Add message type for workspace ↔ backend proxy | If workspace needs backend API access |
| 7 | `popup.js` | Add link/button to open workspace | Alternative entry from popup |
| 8 | `chrome.runtime.onConnect` | Long-lived port for workspace ↔ background | Alternative to message-based communication |

### 13.3 Session Sharing Strategy

Since the workspace SPA runs in the same extension, it can:

1. **Reuse `chrome.runtime.sendMessage`** to `background.js` for session resolution (`getSession`)
2. **Direct OAuth PKCE** in the workspace if needed (self-contained)
3. **Cookie-based fallback** via `chrome.cookies.get` if workspace has `cookies` permission

**Recommendation**: Option 1 — leverage existing session resolution in `background.js` rather than duplicating OAuth logic.

---

## 14. Risks & Trade-offs

### 14.1 Technical Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Workspace breakage on extension update | High | No modification to legacy files; only additive changes |
| Session management duplication | Medium | Reuse background.js session resolution |
| Browser compatibility (MV2 vs MV3) | Medium | Workspace SPA is browser-agnostic (runs in page context) |
| SLDS version drift | Low | Pin SLDS version for workspace, independent of legacy |
| CometD direct connections | Medium | Wrap CometD in workspace service with proxy option |
| API key storage in workspace | Medium | Use chrome.storage.local (encrypted) or backend session |

### 14.2 Strategic Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Developer unfamiliarity with legacy code | Medium | Phase 1 documentation + strict additive-only policy |
| Scope creep — wanting to refactor legacy | High | Enforce "zero modifications" rule |
| Feature parity expectations | Medium | Workspace is independent — parity not a goal |
| Testing complexity | Medium | Workspace has its own test suite; legacy tests untouched |

### 14.3 Trade-offs

| Decision | Trade-off |
|---|---|
| Co-located SPA (same extension) | + Shared session, no new extension review | — Limited by extension CSP, single-thread background |
| Zero modifications to legacy | + No regression risk, isolated deployment | — More integration points needed (hooks vs direct coupling) |
| React-only (no Next.js/Remix) | + Simple static SPA, no build complexity | — No SSR, manual routing |
| SLDS design system | + Consistent with Salesforce, proven | — Large CSS bundle, not tree-shakable |

---

## 15. Phase 2 Recommendations

### 15.1 Architecture Decisions

1. **Session**: Reuse `background.js` session resolution via `chrome.runtime.sendMessage`
2. **API Layer**: Zustand store + Axios with typed API client (not `sfConn`)
3. **State**: Zustand stores (one per domain: auth, metadata, org, workspace)
4. **Routing**: React Router v7 (flat routes)
5. **Styling**: CSS Modules + SLDS design tokens
6. **Components**: Copy 8 existing components, rewrite PageHeader
7. **TypeScript**: Full TypeScript (migration from JS)
8. **Testing**: Vitest + React Testing Library from day 1

### 15.2 Implementation Order

1. Scaffold `addon/enterprise/` with Vite + React + TypeScript + Zustand
2. Build workspace shell (layout, navigation, routing)
3. Implement session management (reuse background proxy)
4. Implement core API stores (AuthStore, OrgStore)
5. Build first workspace landing page
6. Port 8 React components (with TypeScript)
7. Implement feature pages iteratively
8. Integration testing
9. Add 3 hooks to legacy extension (manifest, button, background)

### 15.3 Code to Preserve (copy to workspace)

```
addon/components/AlertBanner.js    → enterprise/src/components/AlertBanner.tsx
addon/components/ConfirmModal.js   → enterprise/src/components/ConfirmModal.tsx
addon/components/AgentforceModal.js → enterprise/src/components/AgentforceModal.tsx
addon/components/Toast.js           → enterprise/src/components/Toast.tsx
addon/components/Tooltip.js         → enterprise/src/components/Tooltip.tsx
addon/components/ColorPicker.js     → enterprise/src/components/ColorPicker.tsx
addon/components/Spinner.js         → enterprise/src/components/Spinner.tsx
addon/styles/slds/                  → enterprise/src/styles/slds/
addon/styles/sfir.css               → enterprise/src/styles/global.css (selective)
addon/lib/cometd/                   → enterprise/src/lib/cometd/
```

### 15.4 Code to Reference (study pattern, reimplement)

```
addon/utils.js           → Study DataCache, UserInfoModel pattern
addon/inspector.js       → Study sfConn.pattern (do NOT copy)
addon/background.js      → Study session resolution flow
addon/ai_service.js      → Study LLM communication pattern
addon/backend_service.js → Study external API client pattern
```

---

## Appendix A: Total Codebase Stats

| Metric | Value |
|---|---|
| Total JS files | 38 (21 feature + 17 shared) |
| Total HTML files | 21 |
| Total CSS files | 20+ |
| Total component files | 8 |
| Total vendor files | 15 (13 CometD + 2 Prism) |
| Total lines (feature JS) | ~22,000 |
| Total lines (shared JS) | ~5,000 |
| Largest file | inspect.js (2,571 lines) |
| Smallest file | inject.js (39 lines) |

## Appendix B: Message Flow Sequence Diagrams

### Popup Open Flow
```
User clicks extension icon
  → chrome.action.onClicked (background.js)
    → chrome.tabs.query({active: true, currentWindow: true})
      → chrome.scripting.executeScript({files: ["button.js"]})
        → button.js creates #insext button
          → User hovers button → button.js creates #insext-popup iframe
            → iframe loads popup.html → popup.js React app
              → postMessage({message: "init"}) to button.js
                → button.js replies {context, recordId, url}
                  → sfConn.getSession(sfHost) via chrome.runtime.sendMessage
```

### Salesforce REST Request Flow
```
Feature page (e.g. data-export.js)
  → sfConn.rest("/services/data/v62.0/query?q=SELECT+Id+FROM+Account")
    → chrome.runtime.sendMessage({
        message: "salesforceRestRequest",
        instanceUrl: "https://na1.salesforce.com",
        sessionId: "00D...!....",
        url: "/services/data/v62.0/query?q=SELECT+Id+FROM+Account",
        headers: {...}
      })
        → background.js: fetch(url, {headers: {Authorization: "Bearer ..."}})
          → HTTPS to Salesforce REST API
            → Response back through the chain
```

### OAuth PKCE Flow
```
Feature page opens
  → sfConn.getSession(sfHost)
    → chrome.runtime.sendMessage({message: "getSession", sfHost})
      → background.js:
        1. Check localStorage for access_token
        2. If expired → try refresh_token
        3. If no token → chrome.cookies.get("sid")
        4. If no cookie → return {requiresAuth: true}
          → Feature page:
            1. Generate code_verifier + code_challenge
            2. Open popup to Salesforce authorize URL
            3. User logs in and authorizes
            4. Popup receives auth code in URL hash
            5. Exchange code for tokens via POST to Salesforce
            6. Store tokens in localStorage
            7. Retry session establishment
```

## Appendix C: localStorage Key Inventory

| Key Pattern | Purpose | Used By |
|---|---|---|
| `{sfHost}_access_token` | OAuth access token | All pages |
| `{sfHost}_refresh_token` | OAuth refresh token | All pages |
| `{sfHost}_client_id` | OAuth client ID | Options > API tab |
| `{sfHost}_customFavicon` | Custom favicon color | Options, PageHeader |
| `apiVersion` | API version override | All pages |
| `sfirBackendUrl` | Backend server URL | backend_service.js |
| `sfirBackendApiKey` | Backend API key | backend_service.js |
| `sfirBackendOrgId` | Default org ID | Dependencies explorer |
| `USER_INSIGHT_AI_API_KEY` | Groq API key | ai_service.js |
| `USER_INSIGHT_AI_ENDPOINT` | Groq endpoint | ai_service.js |
| `displayInspectTableBorders` | UI preference | Options |
| `popupDarkTheme` | Dark theme toggle | Options, popup.js |
| `queryTemplates` | Saved query templates | data-export.js |
| `cacheDuration_*` | Cache TTL overrides | DataCache |
| `flowScannerHistorySize` | Flow scanner config | Options |
| `{sfHost}_exportAgentForcePrompt` | AI prompt template | data-export.js |
| `hideButtonsOption` | Button visibility | Options |
| `defaultPopupTab` | Default popup tab | popup.js |
| `debugLogFetchBodies` | Debug log pref | debug-log.js |
| `useBomForCsvExport` | CSV export pref | data-export.js |
