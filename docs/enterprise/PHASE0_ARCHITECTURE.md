# Phase 0 — Enterprise Intelligence Workspace Architecture

**Status:** Draft — Awaiting Approval  
**Date:** 2026-07-16  
**Author:** Principal Architect  
**Scope:** Architecture only — no implementation, no UI code, no existing file modifications

---

## Table of Contents

1. [Current Architecture Summary](#1-current-architecture-summary)
2. [Enterprise Workspace Architecture](#2-enterprise-workspace-architecture)
3. [Integration Strategy](#3-integration-strategy)
4. [Folder Structure](#4-folder-structure)
5. [Module Boundaries](#5-module-boundaries)
6. [Routing Strategy](#6-routing-strategy)
7. [State Management Strategy](#7-state-management-strategy)
8. [API Strategy](#8-api-strategy)
9. [WebSocket Strategy](#9-websocket-strategy)
10. [Styling Strategy](#10-styling-strategy)
11. [Testing Strategy](#11-testing-strategy)
12. [Build & Deployment Strategy](#12-build--deployment-strategy)
13. [Upgrade Strategy](#13-upgrade-strategy)
14. [Future Plugin Strategy](#14-future-plugin-strategy)
15. [Risks](#15-risks)
16. [Trade-offs](#16-trade-offs)
17. [Recommendations](#17-recommendations)
18. [Architecture Decision Records](#18-architecture-decision-records)

---

## 1. Current Architecture Summary

### 1.1 Existing Extension Structure

```
addon/
├── manifest.json                  # Chrome MV3 manifest
├── background.js                  # Service worker (API proxy, session, commands)
├── button.js                      # Content script (floating button + iframe injection)
├── inject.js                      # Page-injected script (Lightning navigation)
├── inspector.js                   # Salesforce REST/SOAP client (shared)
├── utils.js                       # Utilities, caching, OAuth (shared)
├── popup.html + popup.js          # Main popup (React SPA in iframe overlay)
├── data-export.html + .js         # Feature pages (individual HTML documents)
├── data-import.html + .js         #   18 feature pages, each is a full HTML file
├── rest-explore.html + .js        #   loaded via chrome.tabs.create() or <a href>
├── ... (15 more feature pages)
├── components/                    # Reusable React components (plain JS)
├── styles/slds/slds.css          # Salesforce Lightning Design System
├── styles/sfir.css               # Custom extension styles
├── react.js + react-dom.js       # Vendored React (no npm, no build step)
├── lib/                           # CometD, Prism, Flow Scanner
└── images/ + fonts/               # Static assets
```

### 1.2 Key Architectural Properties

| Property | Current State |
|----------|---------------|
| **Language** | Plain JavaScript (ES modules), **no TypeScript** |
| **Build system** | **None** — files are copied directly to `target/` via `scripts/release-build.js` |
| **Package manager** | npm (devDependencies only: Playwright, ESLint, build scripts) |
| **Runtime deps** | Vendored React (no npm packages in production) |
| **Routing** | Multi-page HTML architecture — no client-side router |
| **React usage** | `React.createElement()` / `h()` alias — **no JSX** |
| **State management** | Component-local state + `localStorage` + `chrome.storage.local` |
| **API client** | `inspector.js` — XMLHttpRequest-based Salesforce REST/SOAP client |
| **Styling** | SLDS v2 + custom `sfir.css` — global CSS, no CSS modules |
| **Testing** | Playwright E2E tests only — no unit tests |
| **Packaging** | `scripts/release-build.js` copies `addon/` → `target/{browser}/dist/` |

### 1.3 How the Extension Loads

```
User visits Salesforce page
  │
  ▼
button.js (content script)
  │── Detects Salesforce page
  │── chrome.runtime.sendMessage → background.js (session resolution)
  │── Creates floating toggle button div#insext
  │── On click: creates iframe → popup.html?host=<sfHost>
  │
  ▼
popup.js (in iframe)
  │── postMessage to parent page (context: recordId, sobject)
  │── sfConn.getSession(sfHost) via background.js
  │── Renders React in #root with 5 tab views (state machine, no router)
  │── Links to other pages: "<a href='data-export.html?host=...'>"
  │
  ▼
Individual feature pages (e.g., data-export.html)
  │── Each is a separate full HTML document
  │── Loaded in new tab or same tab
  │── Each imports inspector.js + utils.js for Salesforce API access
  └── Renders its own React tree
```

---

## 2. Enterprise Workspace Architecture

### 2.1 High-Level Design

The Enterprise Intelligence Workspace is designed as a **co-located, independently-built SPA** that lives inside the `addon/` directory but shares **only** the Chrome extension runtime (manifest, service worker, content script, vendored React).

```
addon/
├── manifest.json                  ← SHARED (extension manifest)
├── background.js                  ← SHARED (service worker — extended with workspace routes)
├── button.js                      ← SHARED (content script — extended with workspace button)
├── commons/                       ← NEW: shared extension utilities (documented contract)
│   ├── bridge.js                  ← Messaging protocol between legacy ↔ workspace
│   └── workspace-launcher.js      ← Opens workspace in iframe/new tab
├── ... (all existing files unchanged)
│
└── enterprise/                    ← NEW: entire workspace isolated here
    ├── index.html                  ← Single entry point for the SPA
    ├── src/
    │   ├── main.tsx               ← React entry point
    │   ├── App.tsx                 ← Root component with router
    │   ├── layouts/               ← Application shell
    │   ├── routes/                ← Route definitions
    │   ├── features/              ← Feature modules
    │   ├── shared/                ← Shared UI, hooks, utilities
    │   ├── api/                   ← API clients (isolated from inspector.js)
    │   ├── websocket/             ← WebSocket clients
    │   ├── state/                 ← State management
    │   ├── theme/                 ← Design system tokens
    │   └── assets/                ← Icons, images, fonts
    ├── package.json               ← Workspace dependencies (React, Router, etc.)
    ├── tsconfig.json              ← TypeScript configuration
    ├── vite.config.ts             ← Build configuration
    └── tests/                     ← Unit + integration tests
```

### 2.2 Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                     Chrome Extension Runtime                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────────┐│
│  │ manifest.json│  │ background.js│  │ button.js (content script)   ││
│  └──────────────┘  └──────┬───────┘  └──────────────┬───────────────┘│
│                           │                          │                │
│                    ┌──────▼───────┐         ┌────────▼───────────┐  │
│                    │ chrome.runtime│         │ iframe / new tab   │  │
│                    │ .sendMessage  │         │ creation           │  │
│                    └──────────────┘         └────────────────────┘  │
└───────────────────────────────────┬──────────────────────────────────┘
                                    │
    ┌───────────────────────────────┼───────────────────────────────┐
    │                               │                               │
    ▼                               ▼                               ▼
┌──────────────────┐     ┌──────────────────────┐     ┌──────────────────┐
│  LEGACY INSPECTOR │     │  ENTERPRISE WORKSPACE │     │ BACKEND SERVER  │
│  (no build step)  │     │  (Vite + React + TS)  │     │ (FastAPI)       │
├──────────────────┤     ├──────────────────────┤     ├──────────────────┤
│ popup.html       │     │ enterprise/          │     │ /api/v1/health   │
│ data-export.html │     │  index.html ← SPA    │     │ /api/v1/sync     │
│ rest-explore.html│     │  ↓                   │     │ /api/v1/graph    │
│ ...              │     │  App.tsx             │     │ /api/v1/search   │
│                  │     │  - Router            │     │ /api/v1/ai       │
│ SHARES:          │     │  - State             │     │ ...              │
│ inspector.js     │     │  - API Clients       │     └──────────────────┘
│ utils.js         │     │  - WebSocket         │
│                  │     │                      │
│ Uses:            │     │ USES:                │
│ chrome.runtime   │     │ chrome.runtime       │
│ → Salesforce API │     │ → Bridge API         │
└──────────────────┘     │ → Backend API        │
                         └──────────────────────┘
```

### 2.3 Workspace Entry Points

The Workspace provides **three entry modes**, mirroring the legacy extension's patterns:

| Mode | Trigger | Implementation |
|------|---------|---------------|
| **Overlay** | Click workspace button in content script | Creates an iframe pointing to `enterprise/index.html` (same as legacy popup) |
| **Tab** | Keyboard shortcut or context menu | `chrome.tabs.create({url: chrome.runtime.getURL('enterprise/index.html')})` |
| **Side Panel** | Chrome 120+ side panel API | `chrome.sidePanel.setOptions({path: 'enterprise/index.html'})` |

### 2.4 Workspace Layout Shell

```
┌──────────────────────────────────────────────────────────────────┐
│  GLOBAL HEADER                                                    │
│  ┌──────────┬──────────┬──────────┬───────────┬─────────────────┐ │
│  │ ☰ Menu  │ Logo     │ Org      │ 🔍 Search │  👤 User  ⚙️   │ │
│  └──────────┴──────────┴──────────┴───────────┴─────────────────┘ │
├──────┬───────────────────────────────────────────────────────────┤
│      │                                                           │
│ SIDE │                    WORKSPACE                              │
│ BAR  │                                                           │
│      │   ┌─────────────────────────────────────────────────┐     │
│ 📊   │   │                                                 │     │
│ Dash │   │                                                 │     │
│      │   │                                                 │     │
│ 📦   │   │         Main Content Area                       │     │
│ Meta │   │                                                 │     │
│      │   │                                                 │     │
│ 🔗   │   │                                                 │     │
│ Deps │   │                                                 │     │
│      │   └─────────────────────────────────────────────────┘     │
│ 🔍   │                                                           │
│ Srch │                                                           │
│      │                                                           │
│ ⚡   │                                                           │
│ Impct│                                                           │
│      │                                                           │
│ 📄   │                                                           │
│ Docs │                                                           │
│      │                                                           │
│ 🤖   │                                                           │
│ AI   │                                                           │
│      │                                                           │
│ 🔄   │                                                           │
│ Jobs │                                                           │
│      │                                                           │
├──────┴───────────────────────────────────────────────────────────┤
│  STATUS BAR  │  Connection  │  Sync Status  │  Version  │   🌐  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. Integration Strategy

### 3.1 What Is Shared

| Component | Shared? | How |
|-----------|---------|-----|
| Chrome extension manifest | ✅ Yes | Single `manifest.json` — workspace pages added as `web_accessible_resources` |
| Service worker (`background.js`) | ✅ Yes | Extended with workspace route handlers via a **non-invasive plugin pattern** |
| Content script (`button.js`) | ✅ Yes | Extended with workspace launch button via a **config addition**, no logic changes |
| Vendored React | ✅ Yes | Workspace can use the same `react.js`/`react-dom.js` OR bundle its own via Vite |
| `inspector.js` (Salesforce API) | ❌ **No** | Workspace has its own API client layer that communicates with the backend |
| `utils.js` | ❌ **No** | Workspace has its own utilities; may reuse small pure functions via `commons/` |
| Styles (`slds.css`, `sfir.css`) | ❌ **No** | Workspace uses its own design system with CSS modules (avoids conflicts) |
| State | ❌ **No** | Workspace has its own state management |
| Routing | ❌ **No** | Workspace has its own SPA router |

### 3.2 Content Script Integration

The existing content script (`button.js`) creates a floating toggle button. To integrate the workspace:

**Strategy: Extension Point, Not Modification**

Add a **single configuration constant** at the top of `button.js`:

```javascript
// ENTERPRISE WORKSPACE INTEGRATION POINT — single source of truth
// To enable: uncomment the line below or set via options
// const WORKSPACE_ENABLED = true;
```

When enabled, the content script adds a **second toggle button** (or a sub-menu on the existing button) that opens `enterprise/index.html` in the same iframe overlay pattern. This is the **only modification** to `button.js`.

### 3.3 Service Worker Integration

The service worker (`background.js`) currently handles:
- Session resolution (`getSfHost`, `getSession`)
- Salesforce API proxy (`salesforceRestRequest`)
- AI proxy (`userInsightAiRequest`)
- Backend proxy (`backendRequest`)
- Keyboard commands

**Strategy: Message Routing Extension**

Add a **message router** at the end of `background.js`:

```javascript
// ENTERPRISE WORKSPACE INTEGRATION POINT — message routing
// import './enterprise/background-handlers.js';  // (loaded as module)
```

When a message prefix matches the workspace namespace (`workspace:*`), it routes to workspace handlers. Otherwise, it falls through to the existing handlers. This is a **non-breaking addition**.

### 3.4 Iframe Isolation

The workspace loads in its own iframe (or tab), providing **complete runtime isolation**:

| Concern | Isolation Mechanism |
|---------|-------------------|
| **DOM** | Separate iframe — no DOM conflicts with legacy or Salesforce |
| **JavaScript** | Separate execution context — no variable collisions |
| **CSS** | Shadow DOM on workspace root + CSS modules — no style leaks |
| **localStorage** | Separate keyspace with `sfir:enterprise:` prefix |
| **chrome.storage** | Separate keyspace with `enterprise:` prefix |
| **React tree** | Separate `ReactDOM.createRoot()` call — independent component tree |

### 3.5 Messaging Protocol

Communication between workspace ↔ legacy ↔ service worker uses a typed message protocol:

```
Workspace ──┐
             ├── postMessage → parent window (Salesforce context)
             │     { type: "workspace:get-context", requestId: "..." }
             │     { type: "workspace:context", orgId, userId, sfHost }
             │
             ├── chrome.runtime.sendMessage → background.js
             │     { type: "workspace:api:request", endpoint, method, body }
             │     { type: "workspace:session:refresh" }
             │
             └── chrome.runtime.connect (long-lived port) → WebSocket relay
                   { type: "workspace:ws:subscribe", channel }
```

### 3.6 Authentication Bridge

The workspace does NOT re-implement Salesforce authentication. Instead, it uses a **bridge pattern**:

1. Workspace sends `{ type: "workspace:session:get" }` via `chrome.runtime.sendMessage`
2. `background.js` resolves session from existing cookie + refresh token flow (unchanged)
3. Returns `{ sfHost, accessToken, orgId, userId }` to the workspace
4. Workspace uses the session for backend API calls (not direct Salesforce calls)

---

## 4. Folder Structure

### 4.1 Complete Structure

```
addon/
├── manifest.json                     ← Unchanged (workspace URL added to web_accessible_resources)
├── background.js                     ← Unchanged (+ 3-line message router appended)
├── button.js                         ← Unchanged (+ 1 constant + 5 lines for workspace button)
├── inject.js                         ← Unchanged
├── inspector.js                      ← Unchanged
├── utils.js                          ← Unchanged
├── ... (all existing files)          ← Absolutely no changes to any file
│
├── commons/                          ← NEW: shared cross-boundary utilities
│   ├── bridge.js                     ←   Typed messaging protocol
│   ├── workspace-launcher.js         ←   Opens workspace iframe/tab
│   └── constants.js                  ←   Shared message types, event names
│
└── enterprise/                       ← NEW: entire workspace (INDEPENDENT BUILD)
    ├── index.html                    ← Single SPA entry point
    ├── vite.config.ts                ← Vite build configuration
    ├── tsconfig.json                 ← TypeScript configuration
    ├── package.json                  ← Workspace dependencies (separate from root)
    ├── eslint.config.mjs             ← Workspace-specific lint rules
    │
    ├── public/
    │   ├── favicon.svg               ← Workspace icon
    │   └── manifest-assets/          ← Icons for standalone mode
    │
    ├── src/
    │   ├── main.tsx                  ← Entry point (polyfills, root render)
    │   ├── App.tsx                   ← Root component (providers, router, layout)
    │   │
    │   ├── layouts/
    │   │   ├── AppShell.tsx          ←   Main layout (header, sidebar, content, status bar)
    │   │   ├── AppShell.module.css   ←   Scoped styles
    │   │   ├── Header.tsx            ←   Global header
    │   │   ├── Sidebar.tsx           ←   Navigation sidebar
    │   │   ├── StatusBar.tsx         ←   Bottom status bar
    │   │   ├── ContextPanel.tsx      ←   Right context panel (resizable)
    │   │   └── WorkspaceErrorBoundary.tsx  ← Error boundary for the app
    │   │
    │   ├── routes/
    │   │   ├── index.tsx             ←   Route definitions (createBrowserRouter)
    │   │   ├── guards.ts             ←   Auth guards, org guards
    │   │   └── lazy.ts              ←   Lazy-loaded route helpers
    │   │
    │   ├── features/
    │   │   ├── dashboard/
    │   │   │   ├── pages/
    │   │   │   │   └── DashboardPage.tsx
    │   │   │   ├── components/
    │   │   │   │   ├── StatCard.tsx
    │   │   │   │   └── RecentSyncs.tsx
    │   │   │   ├── hooks/
    │   │   │   │   └── useDashboard.ts
    │   │   │   ├── api/
    │   │   │   │   └── dashboardApi.ts
    │   │   │   ├── state/
    │   │   │   │   └── dashboardSlice.ts
    │   │   │   ├── types/
    │   │   │   │   └── index.ts
    │   │   │   └── index.ts          ←   Feature barrel export
    │   │   │
    │   │   ├── metadata/
    │   │   │   ├── pages/
    │   │   │   │   ├── MetadataExplorerPage.tsx
    │   │   │   │   └── MetadataDetailPage.tsx
    │   │   │   ├── components/
    │   │   │   │   ├── MetadataTree.tsx
    │   │   │   │   ├── ComponentCard.tsx
    │   │   │   │   └── TypeFilter.tsx
    │   │   │   ├── hooks/
    │   │   │   │   └── useMetadata.ts
    │   │   │   ├── api/
    │   │   │   │   └── metadataApi.ts
    │   │   │   ├── state/
    │   │   │   │   └── metadataSlice.ts
    │   │   │   ├── types/
    │   │   │   │   └── index.ts
    │   │   │   └── index.ts
    │   │   │
    │   │   ├── dependencies/
    │   │   │   ├── pages/
    │   │   │   │   ├── DependencyExplorerPage.tsx
    │   │   │   │   └── DependencyGraphPage.tsx
    │   │   │   ├── components/
    │   │   │   │   ├── DependencyGraph.tsx
    │   │   │   │   ├── DependencyTree.tsx
    │   │   │   │   └── ImpactBadge.tsx
    │   │   │   ├── hooks/
    │   │   │   │   ├── useDependencies.ts
    │   │   │   │   └── useGraph.ts
    │   │   │   ├── api/
    │   │   │   │   └── dependenciesApi.ts
    │   │   │   ├── state/
    │   │   │   │   └── dependenciesSlice.ts
    │   │   │   ├── types/
    │   │   │   │   └── index.ts
    │   │   │   └── index.ts
    │   │   │
    │   │   ├── search/
    │   │   │   ├── pages/
    │   │   │   │   └── SearchPage.tsx
    │   │   │   ├── components/
    │   │   │   │   ├── SearchBar.tsx
    │   │   │   │   ├── SearchResults.tsx
    │   │   │   │   └── SearchFilters.tsx
    │   │   │   ├── hooks/
    │   │   │   │   └── useSearch.ts
    │   │   │   ├── api/
    │   │   │   │   └── searchApi.ts
    │   │   │   ├── state/
    │   │   │   │   └── searchSlice.ts
    │   │   │   ├── types/
    │   │   │   │   └── index.ts
    │   │   │   └── index.ts
    │   │   │
    │   │   ├── impact/
    │   │   │   ├── pages/
    │   │   │   │   └── ImpactAnalysisPage.tsx
    │   │   │   ├── components/
    │   │   │   │   ├── ImpactReport.tsx
    │   │   │   │   ├── BlastRadius.tsx
    │   │   │   │   └── RiskBadge.tsx
    │   │   │   ├── hooks/
    │   │   │   │   └── useImpact.ts
    │   │   │   ├── api/
    │   │   │   │   └── impactApi.ts
    │   │   │   ├── state/
    │   │   │   │   └── impactSlice.ts
    │   │   │   ├── types/
    │   │   │   │   └── index.ts
    │   │   │   └── index.ts
    │   │   │
    │   │   ├── documentation/
    │   │   │   ├── pages/
    │   │   │   │   ├── DocumentationPage.tsx
    │   │   │   │   └── DocExportPage.tsx
    │   │   │   ├── components/
    │   │   │   │   ├── DocViewer.tsx
    │   │   │   │   └── DocTree.tsx
    │   │   │   ├── hooks/
    │   │   │   │   └── useDocumentation.ts
    │   │   │   ├── api/
    │   │   │   │   └── documentationApi.ts
    │   │   │   ├── state/
    │   │   │   │   └── documentationSlice.ts
    │   │   │   ├── types/
    │   │   │   │   └── index.ts
    │   │   │   └── index.ts
    │   │   │
    │   │   ├── ai/
    │   │   │   ├── pages/
    │   │   │   │   ├── AIChatPage.tsx
    │   │   │   │   ├── AIExplainPage.tsx
    │   │   │   │   └── AISummaryPage.tsx
    │   │   │   ├── components/
    │   │   │   │   ├── ChatWindow.tsx
    │   │   │   │   ├── ProviderSelector.tsx
    │   │   │   │   └── CitationBadge.tsx
    │   │   │   ├── hooks/
    │   │   │   │   ├── useAIChat.ts
    │   │   │   │   └── useAIStream.ts
    │   │   │   ├── api/
    │   │   │   │   └── aiApi.ts
    │   │   │   ├── state/
    │   │   │   │   └── aiSlice.ts
    │   │   │   ├── types/
    │   │   │   │   └── index.ts
    │   │   │   └── index.ts
    │   │   │
    │   │   ├── sync/
    │   │   │   ├── pages/
    │   │   │   │   ├── SyncJobsPage.tsx
    │   │   │   │   └── SyncDetailPage.tsx
    │   │   │   ├── components/
    │   │   │   │   ├── SyncJobCard.tsx
    │   │   │   │   ├── SyncProgress.tsx
    │   │   │   │   └── SyncHistory.tsx
    │   │   │   ├── hooks/
    │   │   │   │   └── useSync.ts
    │   │   │   ├── api/
    │   │   │   │   └── syncApi.ts
    │   │   │   ├── state/
    │   │   │   │   └── syncSlice.ts
    │   │   │   ├── types/
    │   │   │   │   └── index.ts
    │   │   │   └── index.ts
    │   │   │
    │   │   ├── organizations/
    │   │   │   ├── pages/
    │   │   │   │   ├── OrganizationsPage.tsx
    │   │   │   │   └── OrgDetailPage.tsx
    │   │   │   ├── components/
    │   │   │   │   ├── OrgCard.tsx
    │   │   │   │   ├── OrgSwitcher.tsx
    │   │   │   │   └── MemberList.tsx
    │   │   │   ├── hooks/
    │   │   │   │   └── useOrganizations.ts
    │   │   │   ├── api/
    │   │   │   │   └── organizationsApi.ts
    │   │   │   ├── state/
    │   │   │   │   └── organizationSlice.ts
    │   │   │   ├── types/
    │   │   │   │   └── index.ts
    │   │   │   └── index.ts
    │   │   │
    │   │   └── settings/
    │   │       ├── pages/
    │   │       │   ├── SettingsPage.tsx
    │   │       │   └── ApiKeysPage.tsx
    │   │       ├── components/
    │   │       │   ├── SettingsSection.tsx
    │   │       │   └── ApiKeyInput.tsx
    │   │       ├── hooks/
    │   │       │   └── useSettings.ts
    │   │       ├── api/
    │   │       │   └── settingsApi.ts
    │   │       ├── state/
    │   │       │   └── settingsSlice.ts
    │   │       ├── types/
    │   │       │   └── index.ts
    │   │       └── index.ts
    │   │
    │   ├── shared/
    │   │   ├── ui/                   ← Design system primitives
    │   │   │   ├── Button/
    │   │   │   │   ├── Button.tsx
    │   │   │   │   ├── Button.module.css
    │   │   │   │   └── index.ts
    │   │   │   ├── Input/
    │   │   │   ├── Modal/
    │   │   │   ├── Table/
    │   │   │   ├── Card/
    │   │   │   ├── Badge/
    │   │   │   ├── Spinner/
    │   │   │   ├── Toast/
    │   │   │   ├── Tooltip/
    │   │   │   ├── Tabs/
    │   │   │   ├── Tree/
    │   │   │   ├── Dropdown/
    │   │   │   ├── Pagination/
    │   │   │   └── EmptyState/
    │   │   │
    │   │   ├── hooks/
    │   │   │   ├── useDebounce.ts
    │   │   │   ├── useLocalStorage.ts
    │   │   │   ├── useMediaQuery.ts
    │   │   │   ├── useKeyboard.ts
    │   │   │   ├── usePolling.ts
    │   │   │   └── useWorkspaceBridge.ts  ← Communication with legacy extension
    │   │   │
    │   │   ├── utils/
    │   │   │   ├── format.ts
    │   │   │   ├── validation.ts
    │   │   │   ├── date.ts
    │   │   │   └── constants.ts
    │   │   │
    │   │   └── types/
    │   │       ├── api.ts                ← Generic API response types
    │   │       ├── pagination.ts         ← Paginated response types
    │   │       └── workspace.ts          ← Workspace context types
    │   │
    │   ├── api/
    │   │   ├── client.ts              ← Axios/fetch instance with auth interceptor
    │   │   ├── interceptor.ts         ← Auth token injection, error handling
    │   │   └── endpoints.ts           ← Backend URL constants
    │   │
    │   ├── websocket/
    │   │   ├── client.ts              ← WebSocket connection manager
    │   │   ├── channels.ts            ← Channel subscriptions
    │   │   └── reconnector.ts         ← Reconnection with exponential backoff
    │   │
    │   ├── state/
    │   │   ├── store.ts               ← Zustand store configuration
    │   │   ├── authSlice.ts           ← Auth/session state
    │   │   ├── orgSlice.ts            ← Organization state
    │   │   └── notifications.ts       ← Global notification state
    │   │
    │   ├── theme/
    │   │   ├── tokens.css             ← Design tokens (CSS custom properties)
    │   │   ├── light.css              ← Light theme
    │   │   ├── dark.css               ← Dark theme
    │   │   ├── ThemeProvider.tsx       ← Theme context provider
    │   │   └── useTheme.ts
    │   │
    │   └── assets/
    │       ├── icons/                 ← SVG icons (optimized via Vite plugin)
    │       └── images/                ← Static images
    │
    ├── tests/
    │   ├── unit/                      ← Vitest unit tests
    │   │   ├── setup.ts               ← Test setup (mocks for chrome API)
    │   │   ├── features/              ← Feature-specific unit tests
    │   │   └── shared/                ← Shared component/hook tests
    │   │
    │   ├── integration/               ← Component integration tests
    │   │   └── flows/                 ← Multi-feature flow tests
    │   │
    │   └── e2e/                       ← Playwright tests for workspace
    │       ├── workspace.spec.ts      ← Workspace-specific tests
    │       └── fixtures.ts            ← Test fixtures
    │
    ├── vitest.config.ts               ← Test configuration
    └── playwright.config.ts           ← E2E test configuration
```

### 4.2 Feature Module Convention

Every feature in `src/features/<name>/` follows a **strict internal structure**:

```
features/<name>/
├── pages/           ← Route-level page components (one per route)
│   └── FeaturePage.tsx
├── components/      ← Feature-specific UI components
│   └── FeatureTable.tsx
├── hooks/           ← Feature-specific hooks
│   └── useFeature.ts
├── api/             ← Feature-specific API calls
│   └── featureApi.ts
├── state/           ← Feature-specific state (Zustand slice)
│   └── featureSlice.ts
├── types/           ← Feature-specific TypeScript types
│   └── index.ts
└── index.ts         ← Barrel export (public API of the feature)
```

**Rules:**
- A feature must NOT import from another feature's internal modules
- A feature MAY import from `shared/`, `api/`, `websocket/`, `state/`
- A feature's public API is its `index.ts` barrel export

---

## 5. Module Boundaries

### 5.1 Dependency Graph

```
enterprise/src/
│
├── main.tsx
│     │
│     ├── App.tsx
│     │     │
│     │     ├── layouts/          ← AppShell, Header, Sidebar, StatusBar
│     │     ├── routes/           ← Route definitions (lazy-loads feature pages)
│     │     └── shared/ui/        ← Design system components
│     │
│     ├── api/client.ts           ← Shared HTTP client
│     ├── websocket/client.ts     ← Shared WebSocket client
│     ├── state/store.ts          ← Global state store
│     └── theme/ThemeProvider.tsx ← Theme provider
│
├── features/<name>/              ← Feature modules (ISOLATED)
│     ├── pages/                  ← Depends on: shared/ui, state, api
│     ├── components/             ← Depends on: shared/ui, types
│     ├── hooks/                  ← Depends on: state, api
│     ├── api/                    ← Depends on: api/client, types
│     └── state/                  ← Depends on: state/store
│
└── shared/                       ← Shared utilities (ZERO deps on features)
      ├── ui/                     ← Depends on: theme
      ├── hooks/                  ← Depends on: shared/utils
      └── utils/                  ← ZERO internal dependencies
```

### 5.2 Prohibited Dependencies

```
❌ Feature → Another feature's components
❌ Feature → Another feature's hooks
❌ Feature → Another feature's state (except through shared store)
❌ Feature → api/ directly (must use its own api/ sub-module)
❌ Feature → websocket/ directly (must use its own WebSocket hook)
❌ shared/ui → features/
❌ shared/hooks → features/
```

### 5.3 Allowed Dependencies

```
✅ Feature → shared/ui/
✅ Feature → shared/hooks/
✅ Feature → shared/utils/
✅ Feature → shared/types/
✅ Feature → theme/
✅ Feature → api/client.ts
✅ Feature → state/store.ts (for cross-cutting concerns)
✅ Feature → websocket/client.ts
✅ Feature → commons/bridge.js (for extension communication)
```

---

## 6. Routing Strategy

### 6.1 Router Selection

**Choice:** React Router v7 with `createBrowserRouter`

**Rationale:**
- Standard for React SPAs — excellent developer experience
- Nested layouts via `<Outlet>` (matches AppShell design)
- Lazy loading via `React.lazy()` + `Suspense` (critical for extension performance)
- Type-safe route params with TypeScript
- No external dependencies beyond `react-router-dom`

### 6.2 Route Structure

```typescript
// routes/index.tsx
createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    errorElement: <WorkspaceErrorBoundary />,
    children: [
      { index: true, element: <Navigate to="/dashboard" /> },
      {
        path: "dashboard",
        lazy: () => import("../features/dashboard/pages/DashboardPage"),
      },
      {
        path: "metadata",
        children: [
          { index: true, lazy: () => import("../features/metadata/pages/MetadataExplorerPage") },
          { path: ":type/:name", lazy: () => import("../features/metadata/pages/MetadataDetailPage") },
        ],
      },
      {
        path: "dependencies",
        children: [
          { index: true, lazy: () => import("../features/dependencies/pages/DependencyExplorerPage") },
          { path: "graph", lazy: () => import("../features/dependencies/pages/DependencyGraphPage") },
        ],
      },
      {
        path: "search",
        lazy: () => import("../features/search/pages/SearchPage"),
      },
      {
        path: "impact",
        lazy: () => import("../features/impact/pages/ImpactAnalysisPage"),
      },
      {
        path: "documentation",
        children: [
          { index: true, lazy: () => import("../features/documentation/pages/DocumentationPage") },
          { path: "export", lazy: () => import("../features/documentation/pages/DocExportPage") },
        ],
      },
      {
        path: "ai",
        children: [
          { path: "chat", lazy: () => import("../features/ai/pages/AIChatPage") },
          { path: "explain", lazy: () => import("../features/ai/pages/AIExplainPage") },
          { path: "summarize", lazy: () => import("../features/ai/pages/AISummaryPage") },
        ],
      },
      {
        path: "sync",
        children: [
          { index: true, lazy: () => import("../features/sync/pages/SyncJobsPage") },
          { path: ":jobId", lazy: () => import("../features/sync/pages/SyncDetailPage") },
        ],
      },
      {
        path: "organizations",
        children: [
          { index: true, lazy: () => import("../features/organizations/pages/OrganizationsPage") },
          { path: ":orgId", lazy: () => import("../features/organizations/pages/OrgDetailPage") },
        ],
      },
      {
        path: "settings",
        children: [
          { index: true, lazy: () => import("../features/settings/pages/SettingsPage") },
          { path: "api-keys", lazy: () => import("../features/settings/pages/ApiKeysPage") },
        ],
      },
    ],
  },
]);
```

### 6.3 Sidebar Navigation

The sidebar is **generated from a route configuration array**, not hardcoded. Each entry specifies:
- `path` — Route path
- `label` — Display name
- `icon` — Icon component
- `badge` — Optional count/notification badge
- `children` — Sub-navigation items

```typescript
// layout/Sidebar.tsx — navigation config
const NAV_ITEMS = [
  { path: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { path: "/metadata", label: "Metadata Explorer", icon: Database, badge: useMetadataCount() },
  { path: "/dependencies", label: "Dependencies", icon: GitBranch, children: [
    { path: "/dependencies", label: "Explorer", icon: Search },
    { path: "/dependencies/graph", label: "Graph View", icon: Share2 },
  ]},
  { path: "/search", label: "Search", icon: Search },
  { path: "/impact", label: "Impact Analysis", icon: Activity },
  { path: "/documentation", label: "Documentation", icon: FileText },
  { path: "/ai", label: "AI Assistant", icon: Bot },
  { path: "/sync", label: "Sync Jobs", icon: RefreshCw },
  { path: "/organizations", label: "Organizations", icon: Building2 },
  { path: "/settings", label: "Settings", icon: Settings },
];
```

### 6.4 Route Isolation

The workspace SPA uses `createBrowserRouter` with its **own isolated `window.location` path**. Since it runs in its own iframe, the workspace's URL is:

```
chrome-extension://<id>/enterprise/index.html#/dashboard
```

When running in a tab (via `chrome.tabs.create`), the URL is:

```
chrome-extension://<id>/enterprise/index.html#/dashboard
```

**This means every route in the workspace SPA has its own fully-qualified extension URL**, completely separate from the legacy extension's HTML pages. There is zero route collision.

---

## 7. State Management Strategy

### 7.1 Library Selection

**Choice:** Zustand v5

**Rationale:**
- Minimal boilerplate — no reducers, no actions, no dispatch
- TypeScript-first with excellent type inference
- No provider wrapping needed (works outside React trees for WebSocket callbacks)
- Built-in middleware for persist, devtools, immer
- Subscriptions with selectors — components only re-render when their slice changes
- Tiny bundle size (~1KB gzipped)
- Works well with extension storage (`persist` middleware with `chrome.storage.local` adapter)

### 7.2 Store Architecture

```
state/
├── store.ts                  ← Combined store (create via Zustand)
├── authSlice.ts              ← Session, user, permissions
├── orgSlice.ts               ← Active org, org list
├── notifications.ts          ← Toast notifications
│
├── persistence.ts            ← chrome.storage.local adapter
└── middleware.ts             ← Logging, performance tracking
```

Each feature's state is a **separate Zustand slice** stored within that feature's module:

```
features/metadata/state/metadataSlice.ts
features/dependencies/state/dependenciesSlice.ts
features/search/state/searchSlice.ts
...
```

### 7.3 Slice Pattern

```typescript
// features/metadata/state/metadataSlice.ts
import { createStore } from "zustand/vanilla";
import { persist } from "zustand/middleware";

interface MetadataState {
  // Data
  components: Record<string, MetadataComponent[]>;
  selectedType: string | null;
  selectedComponent: MetadataComponent | null;

  // Loading
  isLoading: boolean;
  error: string | null;

  // Actions
  fetchComponents: (orgId: string, type: string) => Promise<void>;
  selectComponent: (component: MetadataComponent | null) => void;
  clearComponents: () => void;
}

const useMetadataStore = create<MetadataState>()(
  persist(
    (set, get) => ({
      components: {},
      selectedType: null,
      selectedComponent: null,
      isLoading: false,
      error: null,

      fetchComponents: async (orgId, type) => { /* ... */ },
      selectComponent: (component) => set({ selectedComponent: component }),
      clearComponents: () => set({ components: {} }),
    }),
    {
      name: "sfir:enterprise:metadata",
      storage: chromeStorageAdapter, // chrome.storage.local for persistence
      partialize: (state) => ({ selectedType: state.selectedType }),
    },
  ),
);
```

### 7.4 Cross-Cutting State

Only **three slices** are globally shared:

| Slice | Purpose | Persisted? |
|-------|---------|------------|
| `authSlice` | Session token, user info, permissions | Yes (`chrome.storage.local`) |
| `orgSlice` | Active organization, org list | Yes (`chrome.storage.local`) |
| `notifications` | Global toast/alert queue | No |

Feature slices are **local to their feature**. Cross-feature communication happens through:
1. Shared state (`authSlice`, `orgSlice`)
2. Navigation (route params)
3. Custom events (via `commons/bridge.js`)

### 7.5 Extension Storage Adapter

```typescript
// state/persistence.ts
const chromeStorageAdapter: PersistStorage<unknown> = {
  getItem: async (name) => {
    const result = await chrome.storage.local.get(name);
    return result[name] ?? null;
  },
  setItem: async (name, value) => {
    await chrome.storage.local.set({ [name]: value });
  },
  removeItem: async (name) => {
    await chrome.storage.local.remove(name);
  },
};
```

---

## 8. API Strategy

### 8.1 Architecture

The workspace uses a **two-layer API architecture**:

```
Feature Component
    │
    ▼
Feature API module (features/<name>/api/<name>Api.ts)
    │  ┌── Calls typed endpoint functions
    │  └── Returns typed domain objects
    ▼
Shared API Client (api/client.ts)
    │  ┌── Axios/fetch instance
    │  ├── Auth token injection
    │  ├── Error handling
    │  ├── Request/response interceptors
    │  └── Base URL configuration
    ▼
Backend (FastAPI)
```

### 8.2 Client Configuration

```typescript
// api/client.ts
import axios from "axios";

const apiClient = axios.create({
  baseURL: BACKEND_URL, // chrome.storage.local or defaults to localhost:8000
  timeout: 30_000,
  headers: { "Content-Type": "application/json" },
});

// Request interceptor — inject auth token
apiClient.interceptors.request.use(async (config) => {
  const session = await getSession(); // via bridge to background.js
  if (session?.accessToken) {
    config.headers.Authorization = `Bearer ${session.accessToken}`;
  }
  // Add workspace identifier header
  config.headers["X-Workspace-Version"] = WORKSPACE_VERSION;
  return config;
});

// Response interceptor — handle 401, 403, 5xx
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      // Attempt token refresh via bridge
      await refreshSession();
      // Retry original request
      return apiClient(error.config);
    }
    return Promise.reject(error);
  },
);
```

### 8.3 Endpoint Pattern

Each feature API module defines typed functions:

```typescript
// features/metadata/api/metadataApi.ts
import apiClient from "../../../api/client";
import type { MetadataComponent, MetadataType } from "../types";

const BASE = "/api/v1";

export const metadataApi = {
  listTypes: async (orgId: string): Promise<MetadataType[]> => {
    const { data } = await apiClient.get(`${BASE}/metadata/types`, {
      params: { org_id: orgId },
    });
    return data;
  },

  listComponents: async (
    orgId: string,
    type: string,
    params?: PaginationParams,
  ): Promise<PaginatedResponse<MetadataComponent>> => {
    const { data } = await apiClient.get(`${BASE}/metadata/${type}`, {
      params: { org_id: orgId, ...params },
    });
    return data;
  },

  getComponent: async (
    orgId: string,
    type: string,
    name: string,
  ): Promise<MetadataComponent> => {
    const { data } = await apiClient.get(`${BASE}/metadata/${type}/${name}`, {
      params: { org_id: orgId },
    });
    return data;
  },
};
```

### 8.5 API Client Isolation

The workspace API client is **completely independent** from the legacy extension's `inspector.js`:

| Concern | Legacy (`inspector.js`) | Workspace (`api/client.ts`) |
|---------|------------------------|---------------------------|
| **Target** | Salesforce REST API directly | Backend (FastAPI) |
| **Auth** | Salesforce session cookie | JWT from backend |
| **HTTP client** | XMLHttpRequest | Axios/fetch |
| **Error handling** | Inline callbacks | Interceptors + React Query |
| **Types** | None (plain JS) | Full TypeScript |

---

## 9. WebSocket Strategy

### 9.1 Architecture

```
Workspace SPA
    │
    ├── websocket/client.ts ← Connection manager
    │     └── Maintains WebSocket connection to backend
    │         URL: ws://<backend>/api/v1/ws?token=<jwt>
    │
    ├── websocket/channels.ts ← Channel subscriptions
    │     └── Sync job progress, AI streaming, notifications
    │
    └── Feature hooks consume WebSocket events
          └── useSyncWebSocket(), useAIStream(), useNotifications()
```

### 9.2 Connection Manager

```typescript
// websocket/client.ts
interface WsOptions {
  url: string;
  token: string;
  onMessage: (event: WsEvent) => void;
  onError?: (error: Event) => void;
  onClose?: () => void;
}

class WorkspaceWebSocket {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private subscribers = new Map<string, Set<(event: WsEvent) => void>>();

  connect(options: WsOptions): void { /* ... */ }
  disconnect(): void { /* ... */ }

  // Typed channel subscription
  subscribe<T extends WsEvent>(
    channel: string,
    handler: (event: T) => void,
  ): () => void;

  // Heartbeat ping every 30s
  private heartbeat: NodeJS.Timeout;
}
```

### 9.3 Channel Design

| Channel | Event Types | Consumer |
|---------|-------------|----------|
| `org:{orgId}:sync` | `sync.progress`, `sync.complete`, `sync.failed` | Sync feature |
| `org:{orgId}:ai` | `ai.chunk`, `ai.complete`, `ai.error` | AI feature |
| `org:{orgId}:notifications` | `notification.toast`, `notification.alert` | Global |
| `org:{orgId}:jobs` | `job.started`, `job.progress`, `job.completed` | Jobs feature |

---

## 10. Styling Strategy

### 10.1 Design Principles

1. **Complete visual isolation** from the legacy extension's CSS
2. **No style conflicts** — workspace CSS must NEVER leak to Salesforce pages or legacy pages
3. **Modern design system** — not SLDS-bound; can use any design language
4. **Theme support** — light and dark mode as first-class citizens
5. **CSS Modules** — scoped by default, no class name collisions

### 10.2 Isolation Mechanism

**Primary: Iframe isolation** — the workspace runs in its own iframe (or tab), which provides a completely separate DOM and CSS cascade.

**Secondary: CSS Modules** — all component styles use CSS Modules (`*.module.css`) with Vite's build-time class name hashing:

```css
/* Component.module.css */
.root { /* unique hash */ }
.header { /* unique hash */ }
```

**Tertiary: Shadow DOM** — the workspace root element uses `attachShadow({ mode: "open" })` to prevent any style leakage from the host page.

### 10.3 Design Tokens

```css
/* theme/tokens.css */
:root {
  /* Colors */
  --color-primary: #0070d2;
  --color-primary-hover: #005fb2;
  --color-primary-active: #004a8f;
  --color-background: #ffffff;
  --color-background-secondary: #f3f3f3;
  --color-text: #080707;
  --color-text-secondary: #444444;
  --color-border: #dddbda;
  --color-danger: #c23934;
  --color-warning: #ffb75d;
  --color-success: #027e46;

  /* Typography */
  --font-family: "Salesforce Sans", system-ui, sans-serif;
  --font-size-xs: 0.75rem;
  --font-size-sm: 0.8125rem;
  --font-size-base: 0.875rem;
  --font-size-lg: 1rem;
  --font-size-xl: 1.25rem;

  /* Spacing */
  --space-xs: 0.25rem;
  --space-sm: 0.5rem;
  --space-md: 1rem;
  --space-lg: 1.5rem;
  --space-xl: 2rem;

  /* Layout */
  --sidebar-width: 240px;
  --header-height: 48px;
  --context-panel-width: 320px;
  --status-bar-height: 28px;

  /* Shadows */
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.1);
  --shadow-md: 0 4px 8px rgba(0, 0, 0, 0.12);

  /* Transitions */
  --transition-fast: 150ms ease;
  --transition-normal: 250ms ease;

  /* Border radius */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
}
```

### 10.4 Dark Theme

```css
/* theme/dark.css */
[data-theme="dark"] {
  --color-background: #181818;
  --color-background-secondary: #222222;
  --color-text: #e0e0e0;
  --color-text-secondary: #a0a0a0;
  --color-border: #333333;
  /* ... other dark overrides */
}
```

### 10.5 Component Style Pattern

```css
/* Component.module.css */
.root {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  padding: var(--space-lg);
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.title {
  font-size: var(--font-size-xl);
  font-weight: 600;
  color: var(--color-text);
}
```

---

## 11. Testing Strategy

### 11.1 Test Layers

| Layer | Tool | Target | Location |
|-------|------|--------|----------|
| **Unit tests** | Vitest | Pure functions, hooks, state logic | `enterprise/tests/unit/` |
| **Component tests** | Vitest + React Testing Library | Shared UI components | `enterprise/tests/unit/shared/` |
| **Integration tests** | Vitest + MSW | Feature workflows with API mocking | `enterprise/tests/integration/` |
| **E2E tests** | Playwright | Full workspace flows in Chrome | `enterprise/tests/e2e/` |

### 11.2 Chrome API Mocking

```typescript
// tests/unit/setup.ts
import { vi } from "vitest";

// Mock chrome.* API
globalThis.chrome = {
  runtime: {
    sendMessage: vi.fn(),
    connect: vi.fn(),
    id: "test-extension-id",
  },
  storage: {
    local: {
      get: vi.fn(),
      set: vi.fn(),
      remove: vi.fn(),
    },
  },
  // ... other chrome API mocks
};
```

### 11.3 Test Isolation

All tests run in **isolation**:
- Unit tests: No chrome API, no DOM, no network — pure logic
- Component tests: RTL with mocked chrome API
- Integration tests: MSW for API mocking, chrome API mocked
- E2E tests: Actual Chrome with unpacked extension + mocked Salesforce

---

## 12. Build & Deployment Strategy

### 12.1 Build Pipeline

```
Workspace Source (enterprise/src/)
    │  TypeScript (.ts, .tsx)
    │  CSS Modules (.module.css)
    │  Static assets (SVG, PNG)
    │
    ▼
Vite Build (vite.config.ts)
    │  ┌── @vitejs/plugin-react (JSX transform)
    │  ├── vite-plugin-css-modules (CSS Modules)
    │  ├── vite-plugin-svgr (SVG as React components)
    │  ├── vite-plugin-chrome-extension (manifest-aware)
    │  └── rollup-plugin-visualizer (bundle analysis)
    │
    ▼
Dist (enterprise/dist/)
    │  ┌── index.html (hashed assets)
    │  ├── assets/index-abc123.js
    │  ├── assets/index-def456.css
    │  └── assets/icon-ghi789.svg
    │
    ▼
Copy to addon/enterprise-dist/ (via release build script)
    │
    ▼
Packaged into extension ZIP (via existing release-build.js)
```

### 12.2 Vite Configuration

```typescript
// enterprise/vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "./", // Relative paths for chrome-extension:// protocol
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: "index.html",
      output: {
        entryFileNames: "assets/[name]-[hash].js",
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]",
      },
    },
    target: "es2020",
    minify: "esbuild",
    cssMinify: true,
    sourcemap: false,
  },
  resolve: {
    alias: {
      "@": "/src",
      "@features": "/src/features",
      "@shared": "/src/shared",
    },
  },
});
```

### 12.3 Integration with Existing Build Script

The existing `scripts/release-build.js` copies `addon/` to `target/{browser}/dist/`. The workspace build integrates via a **pre-build step**:

```bash
# Phase 1: Build workspace SPA
cd addon/enterprise
npx vite build    # → enterprise/dist/

# Phase 2: Copy workspace build output to addon
cp -r dist/ ../enterprise-dist/

# Phase 3: Existing build (unchanged)
cd ../..
node scripts/release-build.js chrome
```

The `enterprise-dist/` directory is **gitignored** and only exists after build.

### 12.4 Workspace Package.json

```json
{
  "name": "@sfir/enterprise-workspace",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "test": "vitest",
    "test:coverage": "vitest --coverage",
    "test:e2e": "playwright test",
    "lint": "eslint src/",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "react-router-dom": "^7.0.0",
    "zustand": "^5.0.0",
    "axios": "^1.7.0"
  },
  "devDependencies": {
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^4.3.0",
    "typescript": "^5.6.0",
    "vite": "^6.0.0",
    "vitest": "^2.1.0",
    "@testing-library/react": "^16.0.0",
    "@playwright/test": "^1.48.0",
    "eslint": "^9.0.0",
    "msw": "^2.4.0"
  }
}
```

---

## 13. Upgrade Strategy

### 13.1 Principle: Zero Modifications to Inherited Code

When the upstream Salesforce Inspector Reloaded project releases updates, the workspace must merge with **zero conflicts on existing files**. This is achieved through:

1. **All workspace code lives in `addon/enterprise/`** — a single directory that doesn't exist upstream
2. **The 3 integration points** (`button.js`, `background.js`, `manifest.json`) require only **additive changes** (no line modifications, only appends)
3. **`commons/` directory** is new and won't conflict (upstream doesn't have it)
4. **`enterprise-dist/`** is gitignored — never checked in

### 13.2 Integration Point Documentation

The **three files** that require modifications for workspace integration:

#### File 1: `manifest.json` — Add workspace URL to `web_accessible_resources`

```jsonc
// Integration: APPEND to web_accessible_resources array
{
  "web_accessible_resources": [
    // ... existing entries ...
    {
      "resources": ["enterprise-dist/*"],
      "matches": ["https://*.salesforce.com/*", "https://*.force.com/*"]
    }
  ]
}
```

**Conflict risk:** Low — this is an append to an array. Only conflicts if upstream also appends at the same position.

#### File 2: `button.js` — Add workspace launch button

```javascript
// Integration: APPEND at end of file or at a marked section
// === ENTERPRISE WORKSPACE INTEGRATION ===
// const WORKSPACE_ENABLED = true; // <-- uncomment to enable
//
// This section adds a workspace launch button to the existing floating menu.
// If this section is removed, the workspace simply won't be accessible.
```

**Conflict risk:** Very low — this is appended at the end of the file. Upstream changes to the rest of the file don't conflict.

#### File 3: `background.js` — Add workspace message router

```javascript
// Integration: APPEND at end of file
// === ENTERPRISE WORKSPACE INTEGRATION ===
// Routes workspace:* messages to workspace handlers
```

**Conflict risk:** Very low — appended at end of file.

### 13.3 Merge Strategy

When upstream releases a new version:

```bash
# 1. Fetch upstream changes
git remote add upstream https://github.com/upstream/Salesforce-Inspector-reloaded.git
git fetch upstream

# 2. Merge with strategy
git checkout main
git merge upstream/main --strategy-option=ours
# → The 'ours' strategy automatically keeps our versions of any conflicted files
# → Since we only ADDED files (enterprise/, commons/, enterprise-dist/),
#   there are NO conflicts

# 3. Verify integration points
# Check that manifest.json, button.js, background.js have the integration markers
# If upstream changed these files, the markers may need re-adding
```

**Expected conflict rate:** < 5% of upstream updates will touch the 3 integration points. When they do, re-appending the integration code takes < 5 minutes.

### 13.4 Release Process

```
┌─────────────────────────────────────────────────────────────┐
│                     RELEASE PROCESS                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Build workspace:  cd addon/enterprise && npm run build   │
│                                                              │
│  2. Result: enterprise/dist/ → enterprise-dist/ (copied)     │
│                                                              │
│  3. Run existing extension build (unchanged):                │
│     node scripts/release-build.js chrome                     │
│     → Copies addon/ → target/chrome/dist/addon/              │
│     → enterprise-dist/ IS included in the copy               │
│                                                              │
│  4. ZIP the result (existing script handles this)            │
│                                                              │
│  5. Upload to Chrome Web Store (existing process)            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 14. Future Plugin Strategy

### 14.1 Plugin Architecture

The workspace is designed to support **future plugins** that can be installed independently:

```
enterprise/
├── src/
│   └── features/            ← Built-in features
├── plugins/                 ← NEW: third-party plugins (future)
│   ├── plugin-manifest.json ← Plugin registry
│   └── <plugin-name>/
│       ├── index.tsx        ← Plugin entry point
│       ├── manifest.json    ← Plugin metadata
│       └── ...              ← Plugin structure mirrors feature structure
```

### 14.2 Plugin Contract

```typescript
// shared/types/plugin.ts
interface WorkspacePlugin {
  id: string;
  name: string;
  version: string;
  description: string;

  // Route registration
  routes: PluginRoute[];

  // Navigation (sidebar items)
  navItems: PluginNavItem[];

  // Lifecycle
  onActivate?: (context: PluginContext) => void;
  onDeactivate?: () => void;

  // Extension points
  registerExtensionPoints?: (registry: ExtensionPointRegistry) => void;
}
```

### 14.3 Extension Points

The workspace provides extension points for plugins:

| Extension Point | Description | Hook |
|----------------|-------------|------|
| `sidebar:bottom` | Add items to sidebar bottom | `registerExtensionPoint('sidebar:bottom')` |
| `header:right` | Add items to header (actions, buttons) | `registerExtensionPoint('header:right')` |
| `context-panel:tabs` | Add tabs to right context panel | `registerExtensionPoint('context-panel:tabs')` |
| `metadata:detail-actions` | Add actions to metadata detail view | `registerExtensionPoint('metadata:detail-actions')` |
| `dashboard:widgets` | Add dashboard widgets | `registerExtensionPoint('dashboard:widgets')` |
| `search:providers` | Add custom search providers | `registerExtensionPoint('search:providers')` |

### 14.4 Plugin Isolation

Each plugin is isolated via:
- **Dynamic imports** — plugins are lazy-loaded
- **Sandboxed state** — plugins use their own Zustand slice
- **Shadow DOM** — plugins can opt into Shadow DOM for full style isolation
- **Limited API** — plugins only receive a restricted context object

---

## 15. Risks

| # | Risk | Probability | Impact | Mitigation |
|---|------|-------------|--------|------------|
| 1 | **Iframe performance overhead** | Medium | Medium | Workspace iframe is hidden when not in use; lazy loading of feature bundles |
| 2 | **Storage key conflicts** | Low | High | All workspace keys prefixed with `sfir:enterprise:` |
| 3 | **Vendored React version mismatch** | Low | Medium | Workspace bundles its own React (not using the extension's vendored copy) |
| 4 | **`chrome-extension://` CSP restrictions** | Low | High | Vite config uses `base: "./"` and relative paths |
| 5 | **Upstream manifest changes** | Low | Medium | Git merge conflict on `web_accessible_resources` — easy to resolve |
| 6 | **Backend API changes** | Medium | High | Feature API modules provide a single point of change |
| 7 | **Firefox compatibility** | Low | Medium | Firefox manifest uses different patterns; may need separate workspace build |
| 8 | **Bundle size growth** | Medium | Low | Route-level code splitting keeps initial load small |
| 9 | **Memory pressure from two React apps** | Medium | Low | Workspace is only in memory when active; can be unloaded |
| 10 | **`chrome.storage` quota limits** (10KB per item, ~5MB total) | Medium | Medium | Use `storage.local` with chunking for large data; prefer backend for persistence |

---

## 16. Trade-offs

| Decision | Chosen | Alternative | Rationale |
|----------|--------|-------------|-----------|
| **Language** | TypeScript | Plain JS (legacy choice) | Type safety for a large SPA; compiles to JS for extension |
| **Build tool** | Vite | Webpack, esbuild, tsc | Fastest dev experience; native ESM; excellent plugin ecosystem |
| **State management** | Zustand | Redux, Jotai, Context | Minimal boilerplate; works outside React; tiny bundle |
| **Styling** | CSS Modules | Tailwind, styled-components, SLDS | Scoped by default; no runtime cost; no framework lock-in |
| **Routing** | React Router | TanStack Router, wouter | Industry standard; excellent lazy loading support |
| **Component library** | Custom design system | MUI, Ant Design, Chakra | No dependency on SLDS; full control over bundle size; extension-appropriate |
| **API client** | Axios | fetch, ky | Interceptors for auth; better error handling; wider ecosystem |
| **Testing** | Vitest | Jest, mocha | Native ESM support; Vite-compatible config; faster than Jest |
| **Iframe vs tab** | Both (configurable) | Iframe-only, tab-only | User preference; iframe for overlay mode, tab for full-screen |
| **React version** | React 19 (bundled) | Legacy React 16 (vendored) | Modern features (Suspense, Server Components, Actions); no conflict with legacy |

---

## 17. Recommendations

### 17.1 Phase 1: Foundation (2 weeks)

1. Create `addon/enterprise/` directory structure
2. Set up Vite + TypeScript + React configuration
3. Implement `AppShell` layout (header, sidebar, status bar)
4. Implement routing with lazy-loaded feature stubs
5. Set up Zustand store with `authSlice` and `orgSlice`
6. Create bridge module (`commons/bridge.js`)
7. Create workspace launcher (`commons/workspace-launcher.js`)
8. Add integration points to `button.js`, `background.js`, `manifest.json`
9. Set up CI for workspace build

### 17.2 Phase 2: Design System (1 week)

10. Implement design tokens and theme system
11. Build core UI components (Button, Input, Table, Card, Modal, Toast, etc.)
12. Implement dark mode support
13. Create shared hooks library

### 17.3 Phase 3: Features (4-6 weeks)

14. API client layer with auth interceptor
15. Dashboard feature
16. Metadata Explorer feature
17. Dependency Explorer feature
18. Search feature
19. Impact Analysis feature
20. Documentation feature
21. AI Assistant feature
22. Sync Jobs feature
23. Organizations feature
24. Settings feature

### 17.4 Phase 4: Polish (1 week)

25. E2E tests for critical flows
26. Performance optimization (bundle analysis, lazy loading audit)
27. Accessibility audit
28. Extension manifest compliance check
29. Documentation

### 17.5 Architectural Must-Haves

1. **Never modify existing extension logic** — only append at marked integration points
2. **Always use CSS Modules** — never write global CSS
3. **Always use TypeScript** — never use `any` on API boundaries
4. **Always feature-scaffold with the 6-directory pattern** — pages, components, hooks, api, state, types
5. **Never import across feature boundaries** — use shared state or routing for cross-feature communication
6. **Always lazy-load feature pages** — never import a page statically if it's behind a route

---

## 18. Architecture Decision Records

### ADR-WS-001: Workspace as Co-Located Independent Build

**Status:** Proposed  
**Context:** The Enterprise Workspace must live inside the existing extension but cannot modify its architecture.  
**Decision:** The workspace is built independently with Vite + TypeScript and its output is copied into the extension's build output.  
**Consequences:** Clean separation; upstream merges are trivial; workspace has its own dependency tree.

### ADR-WS-002: Iframe-Based Runtime Isolation

**Status:** Proposed  
**Context:** The workspace must not interfere with the legacy extension's DOM, CSS, or JavaScript.  
**Decision:** The workspace loads in its own iframe (or tab), providing complete runtime isolation.  
**Consequences:** No CSS conflicts; no JS conflicts; independent React tree; slight performance overhead from iframe.

### ADR-WS-003: Backend-Only API Strategy

**Status:** Proposed  
**Context:** The workspace needs metadata, graph, search, and AI data.  
**Decision:** The workspace communicates exclusively with the backend (FastAPI), never directly with Salesforce.  
**Consequences:** Clean API contracts; backend is the source of truth; workspace is decoupled from Salesforce API changes.

### ADR-WS-004: Zustand Over Redux for State

**Status:** Proposed  
**Context:** Need lightweight state management suitable for a Chrome extension context.  
**Decision:** Zustand v5 with persist middleware and `chrome.storage.local` adapter.  
**Consequences:** Minimal boilerplate; ~1KB bundle; works outside React (WebSocket callbacks); built-in persistence.

### ADR-WS-005: CSS Modules Over SLDS

**Status:** Proposed  
**Context:** The legacy extension uses SLDS. The workspace needs visual independence.  
**Decision:** Custom design system with CSS Modules and CSS custom properties for theming.  
**Consequences:** No style conflicts with legacy; full design control; smaller bundle than SLDS; dark mode support.

### ADR-WS-006: Route-Level Code Splitting

**Status:** Proposed  
**Context:** Chrome extensions have limited memory and bandwidth.  
**Decision:** Every route uses `React.lazy()` + `Suspense` for on-demand loading.  
**Consequences:** Initial load is ~100KB (shell + dashboard); each feature loads on demand (~20-50KB each).

---

## Appendix: Key Files Summary

| File | Type | Purpose | Modified? |
|------|------|---------|-----------|
| `addon/manifest.json` | Manifest | Chrome extension config | **Yes** — add workspace URL to `web_accessible_resources` |
| `addon/background.js` | Service Worker | Message routing, API proxy | **Yes** — append workspace message router |
| `addon/button.js` | Content Script | Iframe creation, toggle button | **Yes** — add workspace launch button |
| `addon/commons/bridge.js` | Bridge | Messaging protocol | **New** |
| `addon/commons/workspace-launcher.js` | Launcher | Opens workspace iframe/tab | **New** |
| `addon/enterprise/package.json` | Dependencies | Workspace npm dependencies | **New** |
| `addon/enterprise/vite.config.ts` | Build | Vite configuration | **New** |
| `addon/enterprise/tsconfig.json` | Config | TypeScript configuration | **New** |
| `addon/enterprise/index.html` | Entry | SPA entry point | **New** |
| `addon/enterprise/src/main.tsx` | Entry | React bootstrap | **New** |
| `addon/enterprise/src/App.tsx` | Root | Router + providers + layout | **New** |
| `scripts/release-build.js` | Build | Extension packaging | **No change** — workspace builds before it runs |
