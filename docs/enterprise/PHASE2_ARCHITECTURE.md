# Phase 2: Enterprise Frontend Architecture & Integration Blueprint

> **Status**: Complete  
> **Objective**: Design the complete frontend architecture for the Enterprise Intelligence Workspace — a co-located, isolated SPA inside Salesforce Inspector Reloaded.  
> **Mandate**: Architecture-only. No implementation. No React code. No components. No CSS. No hooks. No API clients. No placeholder code.  
> **Zero modifications** to existing Salesforce Inspector extension code. Only additive integration points.

---

## Table of Contents

1. [Frontend Architecture Blueprint](#1-frontend-architecture-blueprint)
2. [Application Shell Design](#2-application-shell-design)
3. [Feature Modules & Boundaries](#3-feature-modules--boundaries)
4. [Routing Architecture](#4-routing-architecture)
5. [State Architecture](#5-state-architecture)
6. [API Layer Design](#6-api-layer-design)
7. [WebSocket Architecture](#7-websocket-architecture)
8. [Design System Architecture](#8-design-system-architecture)
9. [Information Architecture](#9-information-architecture)
10. [Navigation Flow](#10-navigation-flow)
11. [Sequence Diagrams](#11-sequence-diagrams)
12. [Data Flow Diagrams](#12-data-flow-diagrams)
13. [Performance Strategy](#13-performance-strategy)
14. [Extensibility Strategy](#14-extensibility-strategy)
15. [Risks](#15-risks)
16. [Trade-offs](#16-trade-offs)
17. [Recommendations](#17-recommendations)

---

## 1. Frontend Architecture Blueprint

### 1.1 Layered Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ENTERPRISE WORKSPACE                                 │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                     APPLICATION SHELL                                 │   │
│  │  ┌─────────┐  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐ │   │
│  │  │ Header  │  │ Sidebar  │  │ Main Content  │  │ Context Panel    │ │   │
│  │  │         │  │          │  │              │  │                  │ │   │
│  │  │ Global  │  │ Nav      │  │ <Outlet />   │  │ Properties       │ │   │
│  │  │ Search  │  │ Favorites│  │ (React Router │  │ Quick Info       │ │   │
│  │  │ Notif.  │  │ Recent   │  │  child route) │  │ Related Links    │ │   │
│  │  │ User    │  │ Plugins  │  │              │  │                  │ │   │
│  │  └─────────┘  └──────────┘  └──────────────┘  └──────────────────┘ │   │
│  │  ┌──────────────────────────────────────────────────────────────┐   │   │
│  │  │                     Status Bar                               │   │   │
│  │  │  Connection Health | Sync Status | Version | Org Context     │   │   │
│  │  └──────────────────────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                │                                            │
│                                ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                     ROUTER (React Router v7)                         │   │
│  │  Protected → Lazy Loaded Feature Modules ← Plugin Registration      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                │                                            │
│                                ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                  FEATURE MODULES (12 domains)                        │   │
│  │                                                                      │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │   │
│  │  │Dashboard │ │ Metadata │ │Dependency│ │  Impact  │ │   AI     │  │   │
│  │  │          │ │ Explorer │ │ Explorer │ │ Analysis │ │ Workspace│  │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘  │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │   │
│  │  │  Search  │ │    Doc   │ │   Sync   │ │ Settings │ │   Auth   │  │   │
│  │  │          │ │  Viewer  │ │   Jobs   │ │          │ │          │  │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                │                                            │
│                                ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │               SHARED LAYER                                            │   │
│  │                                                                      │   │
│  │  ┌────────────────────┐  ┌────────────────────┐                     │   │
│  │  │  Design System     │  │  Shared Services   │                     │   │
│  │  │  ───────────       │  │  ───────────       │                     │   │
│  │  │  • Components      │  │  • Auth Service    │                     │   │
│  │  │  • Tokens          │  │  • WebSocket       │                     │   │
│  │  │  • Icons           │  │  • Theme           │                     │   │
│  │  │  • Layouts         │  │  • Event Bus       │                     │   │
│  │  │  • Utilities       │  │  • Command Palette │                     │   │
│  │  └────────────────────┘  └────────────────────┘                     │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                │                                            │
│                                ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                     API LAYER (Only HTTP-capable layer)               │   │
│  │                                                                      │   │
│  │  Axios Instance ← Interceptors (Auth, Error, Retry, Cancel)          │   │
│  │                                                                      │   │
│  │  auth  │ orgs  │ meta  │ deps  │ search  │ impact  │ docs  │ jobs  │   │
│  │  ai    │ config│ notif │       │         │         │       │       │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                │                                            │
│                                ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                      BACKEND SERVER                                   │   │
│  │  FastAPI │ PostgreSQL │ Redis │ Celery │ WebSocket │ REST + SSE      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Layer Responsibilities

| Layer | Responsibility | Can Import From |
|---|---|---|
| **Application Shell** | Layout, routing, providers, auth guard, theme, global services | Shared Layer only |
| **Feature Modules** | Feature-specific UI, business logic, routing, state | Shared Layer, API Layer |
| **Shared Components** | Reusable UI components, design system tokens | Nothing (self-contained) |
| **Shared Services** | Cross-cutting concerns (auth, WebSocket, theme, events) | API Layer, external deps |
| **API Layer** | All backend communication, typed clients, auth injection | Nothing (HTTP only) |
| **Backend** | Business logic, data storage, AI, sync | N/A |

### 1.3 Directional Constraints

```
Feature Module ─────► Shared Components     (allowed)
Feature Module ─────► Shared Services       (allowed)
Feature Module ─────► API Layer             (allowed)
Feature Module ─/──► Another Feature Module (FORBIDDEN)
Feature Module ─/──► Backend directly       (FORBIDDEN)

API Layer ──────────► Backend               (only allowed source)
API Layer ─/────────► React Component       (FORBIDDEN)

Shared Service ─────► API Layer             (allowed)
Shared Service ─/───► Feature Component     (FORBIDDEN)
```

### 1.4 File System Layout (Conceptual)

```
addon/enterprise/
├── index.html                     # SPA entry point
├── main.tsx                       # App bootstrap, providers, router
├── app.tsx                        # Application Shell
│
├── routes.tsx                     # Root route definitions
├── route-guards.tsx               # Auth guard, org guard
│
├── features/
│   ├── dashboard/                 # Module owns everything it needs
│   ├── auth/
│   ├── organizations/
│   ├── metadata-explorer/
│   ├── search/
│   ├── dependency-explorer/
│   ├── impact-analysis/
│   ├── documentation-viewer/
│   ├── ai-workspace/
│   ├── sync-jobs/
│   ├── settings/
│   └── notifications/
│
├── shared/
│   ├── components/                # Design system
│   ├── tokens/                    # Design tokens
│   ├── hooks/                     # Shared hooks (useDebounce, etc.)
│   ├── services/                  # Auth, WebSocket, EventBus, Theme
│   ├── utils/                     # Formatters, validators, constants
│   └── types/                     # Shared TypeScript types
│
├── api/                           # API layer
│   ├── client.ts                  # Axios instance
│   ├── interceptors.ts            # Auth, error, retry
│   ├── auth.ts                    # Named API modules
│   ├── organizations.ts
│   ├── metadata.ts
│   ├── dependencies.ts
│   ├── search.ts
│   ├── impact.ts
│   ├── documentation.ts
│   ├── ai.ts
│   ├── jobs.ts
│   ├── configuration.ts
│   └── notifications.ts
│
├── stores/                        # Zustand store definitions
│   ├── auth-store.ts
│   ├── org-store.ts
│   ├── workspace-store.ts
│   ├── notification-store.ts
│   └── theme-store.ts
│
├── plugins/                       # Plugin registration infrastructure
│   ├── registry.ts
│   ├── types.ts
│   └── slots.ts
│
└── config/
    ├── constants.ts               # App constants
    └── env.ts                     # Environment detection
```

---

## 2. Application Shell Design

### 2.1 Shell Anatomy

```
┌─────────────────────────────────────────────────────────────────────┐
│  HEADER                                                             │
│ ┌──────┐ ┌──────────────────────────────┐ ┌──────┐ ┌──────┐ ┌────┐│
│ │ Logo │ │ Global Search (Cmd+K)        │ │ Org  │ │ Bell │ │User││
│ │      │ │                              │ │Sel.  │ │ (n)  │ │Menu││
│ └──────┘ └──────────────────────────────┘ └──────┘ └──────┘ └────┘│
├─────────────────────────────────────────────────────────────────────┤
│ ┌──────────┐ ┌──────────────────────────────┐ ┌──────────────────┐ │
│ │ SIDEBAR  │ │        MAIN WORKSPACE        │ │  CONTEXT PANEL   │ │
│ │(w: 240px)│ │      (flex: 1)               │ │  (w: 320px)      │ │
│ │          │ │                               │ │                  │ │
│ │ Navigation│ │  Breadcrumb                   │ │ Properties       │ │
│ │ ├─Dashboard│ │  ──────────────────────────  │ │ ────────────    │ │
│ │ ├─Metadata │ │                              │ │ Name: Foo       │ │
│ │ ├─Deps     │ │  <Outlet />                  │ │ Type: CustomObj │ │
│ │ ├─Impact   │ │  (Feature Module Renders)    │ │ Modified: 2d ago│ │
│ │ ├─AI       │ │                              │ │                  │ │
│ │ ├─Jobs     │ │                              │ │ Quick Actions   │ │
│ │ ├─Settings │ │                              │ │ ────────────    │ │
│ │ │          │ │                              │ │ Show Deps       │ │
│ │ ├───────── │ │                              │ │ Analyze Impact  │ │
│ │ │Favorites │ │                              │ │ View Docs       │ │
│ │ │Recent    │ │                              │ │                  │ │
│ │ │Plugins   │ │                              │ │ Related Links   │ │
│ │ └──────────│ │                              │ │ ────────────    │ │
│ │            │ │                              │ │ Setup >         │ │
│ └────────────┘ │                              │ └──────────────────┘ │
├─────────────────────────────────────────────────────────────────────┤
│  STATUS BAR                                                        │
│ ● Connected  │  Org: MySandbox  │  Last Sync: 2m ago  │ v1.0.0    │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Why Each Element Exists

| Element | Rationale |
|---|---|
| **Header** | Contains global controls that must always be accessible: search (the primary navigation paradigm), org context (critical for multi-org workflows), notifications (async task completion), user menu (session management). Fixed position — never scrolls away. |
| **Sidebar** | Persistent navigation tree. Users must be able to jump between modules without losing context. Collapsible to reclaim screen space for focused work. Houses secondary navigation structures (favorites, recent) that require persistence. |
| **Main Workspace** | The rendering surface for feature modules. Single `<Outlet />` from React Router. Feature modules control their own content within this flex area. |
| **Context Panel** | Metadata-heavy workflows require inspecting details without navigating away. The context panel displays properties, relationships, and quick actions for the selected item. Resizable, collapsible, and context-aware (changes content based on what's selected in the workspace). |
| **Status Bar** | Backend connection health, sync progress, and org context provide critical-at-a-glance information. These are status signals, not navigation targets — belongs at the bottom. |
| **Breadcrumb** | Users navigating deep metadata hierarchies need to know where they are and be able to jump to any ancestor level. Breadcrumbs are rendered in the workspace header area (not in the shell header) so each module can customize its path. |
| **Command Palette** | Power users navigate via keyboard. Cmd+K/Ctrl+K opens a searchable palette of all commands, pages, and actions. This is the fastest navigation method for experienced users. |

### 2.3 Shell States

| State | Behavior |
|---|---|
| **Loading** | Skeleton shell renders (no flash of unstyled content). Header logo + spinner + status bar skeleton visible. Sidebar navigation items appear as gray bars. |
| **Authenticated** | Full shell with user session, org context loaded. All navigation enabled. |
| **Unauthenticated** | Minimal shell — logo only. Main workspace shows login form. No sidebar, no context panel. |
| **Error** | Shell renders but workspaces shows error boundary with retry. Status bar shows connection error. Header and sidebar remain functional for navigation. |
| **Offline** | Same as error but status bar shows offline indicator. Cached data accessible. Write operations disabled with explainer toast. |
| **Org Empty** (no orgs configured) | Workspace shows org setup wizard. Header shows "No orgs configured" badge. Sidebar shows limited nav. |

### 2.4 Responsive Breakpoints

| Breakpoint | Layout Adjustment |
|---|---|
| `> 1440px` | Full layout: sidebar + workspace + context panel. All visible. |
| `1025px - 1440px` | Context panel auto-collapses to a slide-over panel (triggered by an icon in workspace header). Sidebar remains. |
| `768px - 1024px` | Sidebar collapses to icon-only rail (narrow icons, labels hidden on hover). Context panel is a full-width slide-over or overlay. |
| `< 768px` | Sidebar becomes a hamburger-drawer overlay. Context panel becomes a bottom sheet. Workspace is full-width. |

### 2.5 Resizable Panels

| Panel | Min Width | Max Width | Default | Persistence |
|---|---|---|---|---|
| Sidebar | 56px (icon rail) | 320px | 240px | localStorage |
| Context Panel | 280px | 480px | 320px | localStorage |
| Split panes within workspace | Per module | Per module | 50/50 | Per-module preference |

---

## 3. Feature Modules & Boundaries

### 3.1 Module Definition

Every feature module is a **self-contained domain unit** with strict import boundaries:

```
features/{module}/
├── index.ts                 # Public API: exports routes, nav items, plugin slots
├── components/              # Module-specific components
│   ├── {Component}.tsx
│   └── ...
├── pages/                   # Page-level components (one per route)
│   ├── {Module}Page.tsx
│   ├── {Module}DetailPage.tsx
│   └── ...
├── hooks/                   # Module-specific hooks
│   ├── use{Module}Data.ts
│   └── ...
├── api/                     # Module-specific API extensions (optional)
│   └── {module}-api.ts      # Only if module has unique API needs beyond shared API layer
├── store/                   # Module state slice
│   └── {module}-store.ts
├── types/                   # Module-specific types
│   └── index.ts
├── utils/                   # Module-specific utilities
│   └── helpers.ts
└── tests/                   # Module tests
    ├── components/
    ├── hooks/
    └── integration/
```

### 3.2 Module Inventory

| # | Module | Primary Route | Purpose | Key Pages |
|---|---|---|---|---|
| 1 | **Dashboard** | `/dashboard` | Overview of org health, recent activity, quick actions | Overview, Recent Syncs, Pending Jobs |
| 2 | **Auth** | `/auth` | Authentication and session management | Login, Callback, Token Management |
| 3 | **Organizations** | `/organizations` | Multi-org management | Org List, Org Detail, Org Setup |
| 4 | **Metadata Explorer** | `/:orgId/metadata` | Browse, search, inspect org metadata | Type List, Type Detail, Component Inspector |
| 5 | **Search** | `/:orgId/search` | Global metadata search | Search Results, Advanced Filters |
| 6 | **Dependency Explorer** | `/:orgId/dependencies` | Visualize metadata dependencies | Graph View, Tree View, List View |
| 7 | **Impact Analysis** | `/:orgId/impact` | Change impact prediction | Impact Results, Comparison View |
| 8 | **Documentation Viewer** | `/:orgId/docs` | View generated documentation | Doc List, Doc Viewer, Version History |
| 9 | **AI Workspace** | `/:orgId/ai` | AI-assisted metadata analysis | Chat Interface, Analysis Results, Prompt Library |
| 10 | **Sync Jobs** | `/:orgId/jobs` | Metadata sync management | Job List, Job Detail, Job History |
| 11 | **Settings** | `/settings` | Global + per-org configuration | Global Settings, Org Settings, API Key Management |
| 12 | **Notifications** | `/notifications` | System notifications | Notification List, Preferences |

### 3.3 Module Boundaries & Constraints

```
STRICT BOUNDARIES (enforced via ESLint):
  Module A ────► Shared Components          ✅
  Module A ────► Shared Services            ✅
  Module A ────► API Layer                  ✅ (but prefer store-mediated access)
  Module A ────► Another Module             ❌ FORBIDDEN
  Module A ────► Backend (directly)         ❌ FORBIDDEN

CROSS-MODULE COMMUNICATION (when needed):
  Module A ───► Event Bus ──► Module B      ✅ (decoupled via events)
  Module A ───► Store (shared) ──► Module B ✅ (shared Zustand store)
```

### 3.4 Cross-Cutting Concerns

| Concern | Solution |
|---|---|
| Cross-module navigation | React Router `useNavigate` — navigate to any route from any module |
| Cross-module data sharing | Shared Zustand stores (org-store, auth-store) + TanStack Query cache |
| Cross-module events | Event Bus service (pub/sub) — modules emit and subscribe to domain events |
| Module-to-module deep links | URL-based — `/metadata/...?selectDependency=true` triggers dependency view |
| Module registration | Each module exports a manifest: `{ routes, navItems, commands, pluginSlots }` |

### 3.5 Module Lifecycle

```
App Initialization
  └── Module Registry loads module manifests
       ├── Routes registered (lazy-loaded via React.lazy)
       ├── Nav items inserted into sidebar
       ├── Command palette commands registered
       └── Plugin slots subscribed
            │
First Visit to Module Route
  └── React.lazy resolves → module chunk loaded
       ├── Module initializes its store slice
       ├── Module fetches initial data via TanStack Query
       └── Module renders into <Outlet />
            │
Subsequent Visits
  └── Route match → cached chunk served
       ├── TanStack Query serves cached data (stale-while-revalidate)
       └── Instant render
            │
Module Unload (navigate away / timeout)
  └── Store slice may be persisted or pruned
       └── Query cache maintained for future visits
```

---

## 4. Routing Architecture

### 4.1 Route Hierarchy

```
/                                   → Redirect to /dashboard (or last known route)
│
├── /auth                           → Auth module (no sidebar, minimal shell)
│   ├── /auth/login                 → Login page
│   ├── /auth/callback              → OAuth callback handler
│   └── /auth/tokens                → Token management
│
├── /dashboard                      → Dashboard module (authenticated)
│
├── /:orgId                         → Org-scoped routes (authenticated + org selected)
│   ├── /:orgId/metadata            → Metadata Explorer
│   │   ├── /:orgId/metadata        → Type list (default view)
│   │   ├── /:orgId/metadata/:type  → Component list by type
│   │   └── /:orgId/metadata/:type/:id → Component detail
│   │
│   ├── /:orgId/search              → Enterprise Search
│   │   └── /:orgId/search?q=&type=&... → Search results
│   │
│   ├── /:orgId/dependencies        → Dependency Explorer
│   │   ├── /:orgId/dependencies    → Graph view (default)
│   │   ├── /:orgId/dependencies/tree → Tree view
│   │   └── /:orgId/dependencies/:id → Component dependencies detail
│   │
│   ├── /:orgId/impact              → Impact Analysis
│   │   └── /:orgId/impact/:id     → Impact analysis for component
│   │
│   ├── /:orgId/docs                → Documentation Viewer
│   │   ├── /:orgId/docs           → Document list
│   │   └── /:orgId/docs/:id       → Document viewer
│   │
│   ├── /:orgId/ai                  → AI Workspace
│   │   ├── /:orgId/ai             → Chat / analysis interface
│   │   └── /:orgId/ai/history/:id → Previous analysis
│   │
│   ├── /:orgId/jobs                → Sync Jobs
│   │   ├── /:orgId/jobs           → Job list
│   │   └── /:orgId/jobs/:id       → Job detail + progress
│   │
│   └── /:orgId/settings            → Org settings
│
├── /settings                       → Global settings (authenticated)
│   ├── /settings/general           → General preferences
│   ├── /settings/api-keys          → API key management
│   ├── /settings/plugins           → Plugin management
│   └── /settings/notifications     → Notification preferences
│
├── /notifications                  → Notification center (authenticated)
│
└── /plugins/:pluginName/*          → Plugin routes (registered dynamically)
```

### 4.2 Route Guards

```
Route Request
  │
  ▼
Authentication Guard
  ├── Unauthenticated → redirect to /auth/login?returnTo={current}
  └── Authenticated
       │
       ▼
  Organization Guard (for /:orgId routes)
    ├── No orgs configured → redirect to /organizations/setup
    ├── orgId not found → redirect to /organizations?error=not_found
    └── Valid org
         │
         ▼
    Feature Guard (per-module, optional)
      ├── Feature not available → 404 page
      └── Feature available → render route
```

### 4.3 Route Registration (Module Manifest)

Each feature module exports a manifest that the router consumes:

```
ModuleManifest {
  name: string                    // Unique module identifier
  routes: RouteDefinition[]       // Route objects with path, element (lazy), children
  navItems: NavItem[]             // Sidebar navigation items
  commands: CommandPaletteEntry[] // Command palette entries
  order: number                   // Display order in sidebar
}
```

The app collects all manifests at bootstrap and constructs the route tree. This design enables:
- Feature modules to be developed in isolation
- Plugins to register routes at runtime
- Route tree to be a pure composition of manifests
- Routes to be dropped from builds if a module is excluded

### 4.4 Navigation Guards (Before Leave)

| Scenario | Guard Behavior |
|---|---|
| Unsaved AI analysis | Confirm dialog: "Leave? Your analysis will be lost." |
| Active sync job detail | Warning: "A sync is in progress. Navigating away won't cancel it." |
| Form with unsaved changes | Confirm dialog: "You have unsaved changes." |
| Deep link to external | Allow (workspace is the SPA) |
| Closing the extension tab | No guard (extension lifecycle handles this) |

### 4.5 Deep Linking

All routes are deep-linkable. The workspace reads initial route from URL on load. The extension can open the workspace at a specific route via:

```
chrome.tabs.create({
  url: chrome.runtime.getURL("enterprise/index.html#/00Dxxxxxxxx/metadata/ApexClass/01p...")
})
```

Deep links support:
- Cross-module links with context (`/metadata/:type/:id?showDependencies=true`)
- Shareable analysis results (`/impact/accepted?share=abc123`)
- Notification navigation (`/notifications?open=notif_456`)

---

## 5. State Architecture

### 5.1 State Categories

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         STATE ARCHITECTURE                               │
│                                                                          │
│  ┌─────────────────────┐    ┌─────────────────────┐                     │
│  │   SERVER STATE      │    │   APPLICATION STATE  │                     │
│  │  (TanStack Query)   │    │     (Zustand)        │                     │
│  │                     │    │                      │                     │
│  │  • Metadata list    │    │  • UI state          │                     │
│  │  • Dependency graph  │    │  • Navigation history │                     │
│  │  • Search results   │    │  • Sidebar collapsed  │                     │
│  │  • Job status       │    │  • Context panel open  │                     │
│  │  • Documentation    │    │  • Theme preference   │                     │
│  │  • Org list         │    │  • Active filters     │                     │
│  │  • AI responses     │    │  • Current selections  │                     │
│  │                     │    │  • Panel sizes        │                     │
│  │  Cache strategy:    │    │                      │                     │
│  │  stale-while-reval  │    │  Persistence:         │                     │
│  │  background refetch │    │  chrome.storage.local │                     │
│  └─────────────────────┘    └──────────────────────┘                     │
│                                                                          │
│  ┌─────────────────────┐    ┌─────────────────────┐                     │
│  │   SESSION STATE     │    │    URL STATE         │                     │
│  │  (Zustand + Storage) │    │  (React Router)      │                     │
│  │                     │    │                      │                     │
│  │  • Auth tokens      │    │  • Route params      │                     │
│  │  • Current user     │    │  • Search params     │                     │
│  │  • Active org       │    │  • Hash fragments    │                     │
│  │  • Permissions      │    │                      │                     │
│  │                     │    │  Source of truth for │                     │
│  │  Persistence:       │    │  current view.       │                     │
│  │  chrome.storage     │    │  Shareable,          │                     │
│  │  (survives restart) │    │  bookmarkable.       │                     │
│  └─────────────────────┘    └──────────────────────┘                     │
└─────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Why Each State Category Exists

| Category | Why Separate | Persistence |
|---|---|---|
| **Server State** | This is data owned by the backend. We are a consumer. TanStack Query provides caching, deduplication, background refetch, optimistic updates, stale management — all built-in. Re-implementing these features in Zustand would be redundant and error-prone. | In-memory + optional persisted cache |
| **Application State** | UI state (panel open/closed, active tab, scroll position) is ephemeral and client-only. Zustand provides the minimal API needed — no boilerplate, no providers, just hooks. | localStorage (preferences), session (transient) |
| **Session State** | Auth tokens and org context need to survive extension restarts (service worker lifecycle). chrome.storage.local provides async, extension-scoped persistence that non-extension code can't access. | chrome.storage.local |
| **URL State** | Route params and search params are the source of truth for the current view. They enable deep linking, browser back/forward, and shareable URLs. React Router manages this natively. | URL bar |

### 5.3 Zustand Store Design

```
┌────────────────────────────────────────────────────┐
│                   STORE MAP                        │
│                                                    │
│  auth-store.ts                                     │
│  ├── session: Session | null                       │
│  ├── user: User | null                            │
│  ├── login(credentials) → Promise                 │
│  ├── logout() → void                              │
│  └── refreshSession() → Promise                   │
│                                                    │
│  org-store.ts                                      │
│  ├── organizations: Organization[]                 │
│  ├── activeOrgId: string | null                   │
│  ├── setActiveOrg(id) → void                      │
│  ├── addOrg(org) → void                           │
│  └── removeOrg(id) → void                         │
│                                                    │
│  workspace-store.ts                                │
│  ├── sidebarCollapsed: boolean                     │
│  ├── contextPanelOpen: boolean                     │
│  ├── contextPanelWidth: number                     │
│  ├── currentModule: string                         │
│  ├── toggleSidebar() → void                       │
│  ├── setContextPanel(open, width?) → void          │
│  └── setCurrentModule(module) → void              │
│                                                    │
│  notification-store.ts                             │
│  ├── notifications: Notification[]                 │
│  ├── unreadCount: number                           │
│  ├── addNotification(notif) → void                │
│  ├── markRead(id) → void                          │
│  └── clearAll() → void                            │
│                                                    │
│  theme-store.ts                                    │
│  ├── mode: 'light' | 'dark' | 'system'            │
│  ├── setMode(mode) → void                         │
│  └── resolved: 'light' | 'dark' (derived)         │
└────────────────────────────────────────────────────┘
```

### 5.4 TanStack Query Design

```
┌────────────────────────────────────────────────────────────┐
│                   QUERY KEY CONVENTION                      │
│                                                             │
│  ['orgs']                     → Organization list           │
│  ['org', orgId]              → Single organization          │
│  ['metadata', orgId]         → Metadata type list           │
│  ['metadata', orgId, type]   → Components of type           │
│  ['metadata', orgId, type, id] → Single component detail    │
│  ['dependencies', orgId, id] → Dependencies for component   │
│  ['impact', orgId, id]       → Impact analysis results      │
│  ['search', orgId, query]    → Search results               │
│  ['docs', orgId]             → Documentation list           │
│  ['docs', orgId, docId]      → Single document              │
│  ['jobs', orgId]             → Sync job list                │
│  ['job', orgId, jobId]       → Single job detail            │
│  ['notifications']           → Notification list            │
│                                                             │
│  STALE TIMES (defaults, configurable per query):            │
│  ─────────────────────────────────────────                  │
│  Organizations:    5 minutes  (rarely changes)              │
│  Metadata types:  10 minutes  (static between syncs)        │
│  Component detail: 5 minutes                                │
│  Dependencies:     2 minutes  (changes during development)  │
│  Search results:   1 minute   (freshness matters)           │
│  Job status:       30 seconds (near real-time)              │
│  Notifications:    1 minute                                  │
└────────────────────────────────────────────────────────────┘
```

### 5.5 State Flow Patterns

```
PATTERN 1: User-initiated data fetch

  User clicks "Metadata Explorer"
    │
    ▼
  React Router loads metadata module
    │
    ▼
  useQuery(['metadata', orgId], () => api.metadata.getTypes(orgId))
    │
    ├── Cache hit & fresh → instant render from cache
    ├── Cache hit & stale → render cache + background refetch
    └── Cache miss → fetch from API
                          │
                          ▼
                      Loading skeleton
                      (Suspense fallback)

PATTERN 2: User mutation (action)

  User renames a component
    │
    ▼
  useMutation → api.metadata.rename(orgId, id, newName)
    │
    ├── Optimistic update → queryClient.setQueryData
    │   (UI updates immediately)
    │
    ├── On success → invalidate queries
    │   queryClient.invalidateQueries(['metadata', orgId, type])
    │
    └── On error → rollback optimistic update + show error toast

PATTERN 3: WebSocket-driven update

  WebSocket message: job.progress
    │
    ▼
  WebSocket service routes to subscribers
    │
    ▼
  Notifications store ← update job notification
    │
    ▼
  queryClient.invalidateQueries(['job', orgId, jobId])
    │
    ▼
  UI re-renders with updated data
```

### 5.6 Loading & Error State Design

| State | UI Pattern |
|---|---|
| **Initial load** | Suspense boundary with skeleton layout matching page structure |
| **Background refresh** | Subtle indicator (pulsing dot or thin progress bar at top of content area) — existing data remains visible |
| **Mutation loading** | Button-level spinner, disabled state. Block form submission. |
| **Error (fetch)** | Inline error banner with retry button. Previous data remains if available. |
| **Error (mutation)** | Toast notification + field-level errors (if form). Full mutation rollback. |
| **Offline** | Global offline indicator in status bar. All mutations disabled with tooltip. Cached data readable. |
| **Empty** | Empty state illustration + action button ("Sync metadata from Salesforce"). Never show a blank page. |

---

## 6. API Layer Design

### 6.1 Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         API LAYER                                    │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                   Axios Instance (api/client.ts)               │  │
│  │                                                                  │  │
│  │  baseURL: from config (localStorage → env → default)           │  │
│  │  timeout: 30s (configurable)                                   │  │
│  │                                                                  │  │
│  │  INTERCEPTORS:                                                   │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │  │
│  │  │ Auth Injects │  │ Error       │  │ Retry       │           │  │
│  │  │ X-API-Key    │  │ Normalizer  │  │ (5xx, 429)  │           │  │
│  │  │ X-Org-ID     │  │ (unify      │  │ exponential │           │  │
│  │  │              │  │  error fmt) │  │ backoff)    │           │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘           │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                    NAMED API MODULES                            │  │
│  │                                                                  │  │
│  │  api/auth.ts         │  api/search.ts                          │  │
│  │  api/organizations.ts│  api/impact.ts                          │  │
│  │  api/metadata.ts      │  api/documentation.ts                  │  │
│  │  api/dependencies.ts  │  api/ai.ts                             │  │
│  │  api/jobs.ts          │  api/configuration.ts                  │  │
│  │  api/notifications.ts │  api/health.ts                         │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  RULES:                                                              │
│  • Every function returns typed Promise<T>                          │
│  • Every function accepts AbortSignal for cancellation              │
│  • No UI logic in any API module                                    │
│  • No error handling (thrown errors caught by interceptor)          │
│  • No localStorage access (config injected at construction)         │
│  • Pure request/response translation only                           │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.2 Contract Definitions

Each API module has a strict contract:

```
Module: auth
────────────────────────────────────────────────────
login(credentials: LoginRequest)       → Session
logout()                               → void
refreshSession(refreshToken: string)   → Session
getSession()                           → Session | null

Module: organizations
────────────────────────────────────────────────────
list()                                 → Organization[]
get(id: string)                        → Organization
create(data: CreateOrgRequest)         → Organization
update(id: string, data: UpdateOrg)    → Organization
delete(id: string)                     → void
syncOrg(id: string)                    → SyncResult
testConnection(id: string)            → ConnectionStatus

Module: metadata
────────────────────────────────────────────────────
listTypes(orgId: string)               → MetadataType[]
listComponents(orgId: string, type: string)       → Component[]
getComponent(orgId: string, type: string, id: string) → ComponentDetail
search(orgId: string, query: string, filters?: SearchFilters) → SearchResults
getDifferences(orgId: string, baselineId: string)  → Diff[]

Module: dependencies
────────────────────────────────────────────────────
getUpstream(orgId: string, componentId: string, depth?: number) → DependencyGraph
getDownstream(orgId: string, componentId: string, depth?: number) → DependencyGraph
getFullGraph(orgId: string, componentId: string, depth?: number) → DependencyGraph
getShared(orgId: string, componentIds: string[])    → SharedDependencies
findPath(orgId: string, sourceId: string, targetId: string) → DependencyPath[]

Module: impact
────────────────────────────────────────────────────
analyze(orgId: string, componentIds: string[], options?: ImpactOptions) → ImpactResult
getHistory(orgId: string, componentId: string)      → ImpactHistory[]
compare(orgId: string, analysisId1: string, analysisId2: string) → ImpactComparison

Module: search
────────────────────────────────────────────────────
search(orgId: string, query: string, filters?: SearchFilters) → SearchResults
suggest(orgId: string, prefix: string)              → Suggestion[]
getFacets(orgId: string)                             → SearchFacets
saveSearch(orgId: string, query: SavedSearch)        → void
getSavedSearches(orgId: string)                      → SavedSearch[]

Module: documentation
────────────────────────────────────────────────────
list(orgId: string)                                  → DocSummary[]
get(orgId: string, docId: string)                    → Document
getVersions(orgId: string, docId: string)            → DocVersion[]
regenerate(orgId: string, componentIds: string[])    → JobResult

Module: ai
────────────────────────────────────────────────────
chat(orgId: string, messages: Message[], signal?: AbortSignal) → Stream<Chunk>
analyze(orgId: string, context: AIContext, signal?: AbortSignal) → Stream<Chunk>
getHistory(orgId: string)                             → Conversation[]
getConversation(orgId: string, id: string)            → Conversation

Module: jobs
────────────────────────────────────────────────────
list(orgId: string, filters?: JobFilters)             → Job[]
get(orgId: string, jobId: string)                     → JobDetail
cancel(orgId: string, jobId: string)                  → void
retry(orgId: string, jobId: string)                   → Job
getLogs(orgId: string, jobId: string)                 → LogEntry[]

Module: configuration
────────────────────────────────────────────────────
getGlobal()                                            → GlobalConfig
updateGlobal(config: Partial<GlobalConfig>)            → GlobalConfig
getOrgConfig(orgId: string)                            → OrgConfig
updateOrgConfig(orgId: string, config: Partial<OrgConfig>) → OrgConfig

Module: notifications
────────────────────────────────────────────────────
list(filters?: NotificationFilters)                    → Notification[]
markRead(id: string)                                   → void
markAllRead()                                          → void
dismiss(id: string)                                    → void
getPreferences()                                       → NotificationPrefs
updatePreferences(prefs: Partial<NotificationPrefs>)   → NotificationPrefs
```

### 6.3 Error Contract

Every API error follows a normalized shape:

```
ApiError {
  status: number
  code: string            // e.g. "AUTH_TOKEN_EXPIRED", "ORG_NOT_FOUND"
  message: string         // Human-readable, user-facing message
  details?: unknown       // Additional error context
  requestId?: string      // Server-side correlation ID
}
```

Error codes map to specific UI behaviors:

| Code | UI Behavior |
|---|---|
| `AUTH_TOKEN_EXPIRED` | Auto-trigger token refresh → retry original request |
| `AUTH_TOKEN_INVALID` | Redirect to /auth/login with return URL |
| `ORG_NOT_FOUND` | Show error with "Configure new org" action |
| `RATE_LIMITED` | Show toast with retry-after countdown, auto-retry |
| `SYNC_IN_PROGRESS` | Debounce and retry, show "sync ongoing" indicator |
| `VALIDATION_ERROR` | Surface field-level errors to form |
| `INTERNAL_ERROR` | Generic error boundary with "Report" action |
| `NETWORK_ERROR` | Offline state, queue mutations, retry on reconnect |

---

## 7. WebSocket Architecture

### 7.1 Design

```
┌─────────────────────────────────────────────────────────────────────┐
│                        WEBSOCKET SERVICE                            │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    Connection Manager                         │   │
│  │                                                                  │   │
│  │  connect(orgId) → Promise<WebSocket>                           │   │
│  │  disconnect() → void                                           │   │
│  │  reconnect() → Promise<WebSocket>     (exponential backoff)   │   │
│  │  getStatus() → 'connected' | 'disconnected' | 'connecting'    │   │
│  │                                                                  │   │
│  │  Triggers:                                                      │   │
│  │  • Org switch → disconnect old → connect new                   │   │
│  │  • Auth refresh → send new token                               │   │
│  │  • Connection drop → auto-reconnect (5s, 10s, 30s, 60s max)   │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                     Heartbeat                                  │   │
│  │                                                                  │   │
│  │  • Send ping every 30 seconds                                  │   │
│  │  • Expect pong within 10 seconds                               │   │
│  │  • Miss 3 pongs → trigger reconnect                            │   │
│  │  • Wire protocol: JSON { type: 'ping' | 'pong' }              │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                     Message Router                             │   │
│  │                                                                  │   │
│  │  Incoming message:                                              │   │
│  │  { type: "job.progress", payload: { jobId, progress, status } }│   │
│  │                                                                  │   │
│  │  Router dispatches by type prefix:                              │   │
│  │  ┌─────────────────┬──────────────────────┐                   │   │
│  │  │ job.*           │ → Job subscribers    │                   │   │
│  │  │ metadata.*      │ → Metadata subscribers│                   │   │
│  │  │ ai.*            │ → AI subscribers     │                   │   │
│  │  │ notification.*  │ → Notif subscribers  │                   │   │
│  │  │ system.*        │ → Connection manager │                   │   │
│  │  └─────────────────┴──────────────────────┘                   │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    Subscription API                            │   │
│  │                                                                  │   │
│  │  subscribe(type: string, handler: Handler) → UnsubscribeFn     │   │
│  │  subscribeToJob(jobId, handler) → UnsubscribeFn                │   │
│  │  subscribeToMetadataSync(handler) → UnsubscribeFn              │   │
│  │  subscribeToNotifications(handler) → UnsubscribeFn             │   │
│  │  subscribeToAI(handler) → UnsubscribeFn                        │   │
│  │                                                                  │   │
│  │  All subscriptions are cleaned up on unmount (React effect).   │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 7.2 Message Types

```
Type Prefix     │ Direction     │ Purpose
────────────────┼───────────────┼────────────────────────────
job.started     │ server → client │ Job has been accepted and started
job.progress    │ server → client │ Progress update (percentage + message)
job.completed   │ server → client │ Job completed successfully
job.failed      │ server → client │ Job failed with error message
job.cancelled   │ server → client │ Job cancelled by user or system
│
metadata.sync.started     │ server → client │ Metadata sync initiated
metadata.sync.progress    │ server → client │ Current sync item
metadata.sync.completed   │ server → client │ Sync summary (added, updated, removed)
metadata.sync.failed      │ server → client │ Sync error details
│
ai.chunk       │ server → client │ Streaming AI response chunk
ai.done        │ server → client │ AI response complete
ai.error       │ server → client │ AI processing error
│
notification.new          │ server → client │ New notification
notification.dismissed   │ server → client │ Notification dismissed (another session)
│
system.connection.status  │ bidirectional   │ Connection health
system.auth.expiring     │ server → client │ Token expires in <5 minutes
```

### 7.3 Wire Protocol

```
Client → Server:
  { type: "subscribe", channels: ["job.*", "notification.*"] }
  { type: "unsubscribe", channels: ["job.*"] }
  { type: "ping" }
  { type: "pong" }

Server → Client:
  { type: "job.progress", id: "msg_001", timestamp: "2026-07-16T10:30:00Z",
    payload: { jobId: "job_123", progress: 45, message: "Processing ApexClass..." } }
  { type: "notification.new", id: "msg_002", timestamp: "...",
    payload: { id: "notif_001", title: "Sync Complete", severity: "info" } }
  { type: "ai.chunk", id: "msg_003", timestamp: "...",
    payload: { conversationId: "conv_001", text: "The impact analysis shows..." } }
  { type: "pong" }
```

### 7.4 Connection Recovery Strategy

```
1. WebSocket 'close' event fires
2. Connection Manager transitions to 'reconnecting' state
3. Status bar updates to "Reconnecting..." (yellow indicator)
4. First reconnect attempt: 5 second delay
5. Second attempt: 10 second delay
6. Third attempt: 30 second delay
7. Subsequent attempts: 60 second delay (cap)
8. On each attempt, notify subscribers of connection state change
9. After successful reconnect:
   a. Re-subscribe to all active channels
   b. Notify subscribers: 'connected'
   c. Trigger data refresh for stale queries (TanStack Query invalidate)
   d. Status bar updates to "Connected" (green indicator)
10. After 5 consecutive failures:
    a. Notify user: "Connection lost. Retrying in background."
    b. Reduce retry frequency to every 5 minutes
    c. Allow manual retry button in status bar
11. After 30 minutes of disconnection:
    a. Stop retrying
    b. User must manually reconnect or reload
```

### 7.5 Connection Per Org

The WebSocket connection is scoped to the active organization. When the user switches orgs:

```
1. User selects different org in header
2. orgStore.setActiveOrg(newOrgId)
3. WebSocket service detects org change
4. disconnect() current WS → flush pending messages
5. connect(newOrgId) → establish new WS with new auth context
6. Re-subscribe to all active channels for new org
7. All subscribers notified of reconnection
```

---

## 8. Design System Architecture

### 8.1 Design Token Hierarchy

```
┌─────────────────────────────────────────────────────────────────────┐
│                       DESIGN TOKENS                                 │
│                                                                      │
│  CORE TOKENS (immutable primitives)                                 │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Color Palette: gray-50 through gray-950, blue-50-950,       │   │
│  │   green, red, orange, purple, teal, yellow                  │   │
│  │ Typography: font families (Inter, mono), size scale         │   │
│  │   (12/14/16/20/24/30/38/48), weights (400/500/600/700)     │   │
│  │ Spacing: 4px grid (0/1/2/3/4/5/6/8/10/12/16/20/24/32/40)  │   │
│  │ Elevation: shadow scale (sm/md/lg/xl/2xl)                  │   │
│  │ Border: radius scale (none/sm/md/lg/full), width scale     │   │
│  │ Breakpoints: sm(640)/md(768)/lg(1024)/xl(1280)/2xl(1536)  │   │
│  │ Motion: duration (fast/medium/slow), easing (in/out/in-out) │   │
│  │ Z-index: scale (dropdown/sticky/modal/toast/tooltip)       │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  SEMANTIC TOKENS (mapped to light/dark context)                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Background: page, surface, elevated, overlay, brand          │   │
│  │ Text: primary, secondary, tertiary, brand, link, inverse     │   │
│  │ Border: default, hover, focus, selected, error               │   │
│  │ Icon: default, brand, disabled, inverse                      │   │
│  │ Status: success, warning, error, info, neutral               │   │
│  │ Action: primary(default/hover/active/disabled)               │   │
│  │         secondary(default/hover/active/disabled)             │   │
│  │         ghost(default/hover/active/disabled)                 │   │
│  │         destructive(default/hover/active/disabled)           │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  COMPONENT TOKENS (derived, component-specific)                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Button: --btn-height-sm, --btn-height-md, --btn-height-lg    │   │
│  │   --btn-padding-x, --btn-font-weight                         │   │
│  │ Table: --table-cell-padding, --table-header-bg,             │   │
│  │   --table-row-hover-bg, --table-stripe-bg                   │   │
│  │ Card: --card-padding, --card-radius, --card-shadow          │   │
│  │ Dialog: --dialog-width-sm/md/lg, --dialog-padding           │   │
│  │ Tree: --tree-indent, --tree-item-height, --tree-icon-size   │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 8.2 Component Hierarchy

```
ATOMS (8)
├── Button, IconButton, ButtonGroup
├── Input, TextArea, Select, Checkbox, Radio, Toggle
├── Badge, Tag, StatusDot
├── Avatar, AvatarGroup
├── Spinner, Skeleton
├── Tooltip, Popover
├── Divider
└── VisuallyHidden

MOLECULES (12)
├── FormField, FormSection, FormGroup
├── Table, TableHeader, TableRow, TableCell
├── Dialog, ConfirmDialog, FullScreenDialog
├── Card, CardHeader, CardContent, CardFooter
├── Menu, MenuItem, MenuDivider, MenuGroup
├── Tabs, Tab, TabPanel
├── Breadcrumb, BreadcrumbItem
├── Pagination
├── Dropdown, DropdownTrigger, DropdownContent
├── Accordion, AccordionItem
├── ProgressBar, ProgressRing
├── Toast, ToastContainer

ORGANISMS (8)
├── Sidebar, SidebarItem, SidebarGroup, SidebarSection
├── Header, HeaderSearch, HeaderDropdown
├── ContextPanel, ContextPanelSection
├── DataTable (sortable, filterable, selectable)
├── TreeView, TreeNode
├── SplitPane, ResizablePanel
├── CommandPalette
├── NotificationCenter

TEMPLATES (4)
├── PageHeader (title, actions, breadcrumb)
├── PageLayout (sidebar + content + context panel)
├── EmptyState (illustration, message, action)
├── ErrorState (message, retry, report)

GRAPHICS (3)
├── GraphView (force-directed dependency graph)
├── TreeGraph (hierarchical tree layout)
├── JSONViewer (collapsible JSON tree)
```

### 8.3 Component Design Rules

| Rule | Rationale |
|---|---|
| Every component accepts `className` for composition | Enables parent-controlled styling without breaking encapsulation |
| Every component forwards `ref` via `forwardRef` | Enables imperative access (focus management, tooltip positioning) |
| Every interactive component has a `disabled` state | Required for form submission safety and loading states |
| Every component supports `data-testid` | Enables query-based testing without relying on CSS classes |
| Every component supports light and dark mode | Dark mode is a hard requirement for enterprise tools |
| No component depends on another component's internal state | All state is managed via props and callbacks |
| Every component has a TypeScript interface for its props | Self-documenting, compile-time safety |
| Components are pure — no side effects in render | Predictable rendering, easy testing |

### 8.4 Theme Architecture

```
ThemeProvider (React Context)
  ├── mode: 'light' | 'dark' | 'system'
  ├── resolved: 'light' | 'dark' (computed from mode + prefers-color-scheme)
  ├── tokens: SemanticTokens (resolved for current theme)
  └── setMode(mode) → void

CSS Variable strategy:
  :root { --color-bg-page: var(--color-gray-50); }
  [data-theme="dark"] { --color-bg-page: var(--color-gray-950); }

  .my-component {
    background: var(--color-bg-page);
  }
```

Components never reference raw color values — they always use semantic CSS variables. Theme switching is a single attribute change on `<html>`.

### 8.5 Icon System

```
SVG sprite sheet (single file, loaded once)
  └── <svg><use xlinkHref="#icon-search"/></svg>

Icon set:
  ├── Navigation: home, search, settings, folder, file, tree
  ├── Actions: plus, edit, delete, copy, download, upload, refresh, close
  ├── Status: check, alert, warning, info, question, spinner
  ├── Data: table, list, grid, graph, chart
  ├── Communication: chat, mail, bell, share
  └── Objects: code, book, cube, flag, star, clock
```

---

## 9. Information Architecture

### 9.1 Navigation Hierarchy

```
┌─────────────────────────────────────────────────────────────────┐
│                     NAVIGATION TREE                              │
│                                                                  │
│  WORKSPACE ROOT                                                 │
│  ├── Dashboard ◄ (default landing — org overview, metrics)      │
│  │                                                              │
│  ├── Metadata Explorer                                          │
│  │   ├── Browse by Type                                        │
│  │   ├── Recently Modified                                      │
│  │   ├── Component Detail                                       │
│  │   └── Schema Viewer                                          │
│  │                                                              │
│  ├── Dependency Explorer                                        │
│  │   ├── Graph View                                             │
│  │   ├── Tree View                                              │
│  │   ├── List View                                              │
│  │   └── Path Finder                                            │
│  │                                                              │
│  ├── Impact Analysis                                            │
│  │   ├── New Analysis                                           │
│  │   ├── Analysis History                                       │
│  │   └── Comparison View                                        │
│  │                                                              │
│  ├── Documentation Viewer                                       │
│  │   ├── All Documents                                          │
│  │   ├── By Component Type                                      │
│  │   └── Document Viewer                                        │
│  │                                                              │
│  ├── AI Workspace                                               │
│  │   ├── Chat Interface                                         │
│  │   ├── Analysis History                                       │
│  │   └── Prompt Library                                         │
│  │                                                              │
│  ├── Sync Jobs                                                  │
│  │   ├── Active Jobs                                            │
│  │   ├── Job History                                            │
│  │   └── Job Detail                                             │
│  │                                                              │
│  ├── Settings                                                   │
│  │   ├── Global Settings                                        │
│  │   ├── Organization Settings                                  │
│  │   ├── API Keys                                               │
│  │   ├── Notification Preferences                               │
│  │   └── Plugin Management                                      │
│  │                                                              │
│  └── [Plugin Items] ├── ...                                    │
│                                                                  │
│  UTILITY (accessible from anywhere)                              │
│  ├── Global Search (Cmd+K)                                      │
│  ├── Command Palette (Ctrl+Shift+K)                             │
│  ├── Notifications (bell icon)                                  │
│  ├── Organization Switcher (header dropdown)                    │
│  └── User Menu (header dropdown: profile, logout)              │
└─────────────────────────────────────────────────────────────────┘
```

### 9.2 Cross-Cutting Navigation Patterns

| Pattern | Mechanism |
|---|---|
| **Module to module** | Sidebar click → React Router navigate. Current module state preserved in cache. |
| **Context to module** | Context panel "Show Dependencies" → navigate to Dependency Explorer with selected component ID. |
| **Search to module** | Click search result → navigate to the appropriate module detail view. |
| **Notification to module** | Click notification → navigate to the relevant job/component/analysis. |
| **Breadcrumb navigation** | Click any breadcrumb segment → navigate to that level. |
| **Back/Forward** | Browser history — React Router manages the history stack. |
| **Deep link (external)** | URL contains full path → workspace loads at that route. |

### 9.3 Navigation Metadata

Every navigation target carries metadata for sidebar highlighting, breadcrumb generation, and context panel awareness:

```
NavigationTarget {
  id: string
  label: string
  icon: string
  route: string
  parentId?: string
  module: string
  isActive: (pathname) => boolean  // Route matching function
  breadcrumb: { label: string; route?: string }[]
  contextPanelConfig?: {
    defaultOpen: boolean
    sections: string[]
  }
}
```

### 9.4 Search-First Navigation

The Global Search is the primary navigation paradigm for experienced users:

```
Cmd+K pressed
  │
  ▼
Command Palette opens (overlay, centered)
  │
  ├── Recent items (from history)
  ├── Suggested actions (context-aware)
  │
  └── User types "apex class update"
       │
       ▼
  Results grouped by category:
  ├── Pages: Metadata Explorer > ApexClass, Settings
  ├── Components: ApexClass: OrderController, AccountService
  ├── Actions: Sync Metadata, Run Impact Analysis
  └── Commands: New Analysis, Generate Documentation
```

---

## 10. Navigation Flow

### 10.1 User Onboarding Flow

```
User opens Enterprise Workspace
  │
  ▼
App Shell renders (loading skeleton)
  │
  ▼
Auth check:
  ├── Not authenticated:
  │   │
  │   ▼
  │   Minimal shell → /auth/login
  │   │
  │   ├── User enters backend URL + API key
  │   ├── POST /api/v1/auth/login
  │   ├── Store tokens in chrome.storage
  │   └── Redirect to return URL or /dashboard
  │
  └── Authenticated:
      │
      ▼
  Load org list:
      ├── No orgs:
      │   │
      │   ▼
      │   /organizations/setup → Org setup wizard
      │   ├── Enter org ID + name
      │   ├── Test connection (GET /api/v1/health/org/{id})
      │   └── Save → navigate to /{orgId}/metadata
      │
      └── Has orgs:
          │
          ▼
      Load last active org (from preference) or first org
          │
          ▼
      Navigate to /{orgId}/dashboard
```

### 10.2 Typical User Session

```
1. User opens workspace → /dashboard
   ├── Dashboard shows:
   │   ├── Sync health (last sync: 2h ago — stale indicator)
   │   ├── Recent metadata changes (5 components modified today)
   │   ├── Recent jobs (2 completed, 1 failed)
   │   └── Quick actions: "Sync Metadata", "New Impact Analysis"

2. User clicks "Sync Metadata"
   │
   ▼
   POST /api/v1/orgs/{orgId}/sync → Job created
   ├── Status bar shows sync progress (WebSocket: job.progress)
   ├── /jobs → Job detail (live progress via WebSocket)
   └── Notification when sync completes

3. User clicks "Metadata Explorer" in sidebar
   │
   ▼
   /{orgId}/metadata → Type list
   ├── Browse: ApexClass, ApexTrigger, CustomObject, Flow...
   ├── Filter by type → component list
   ├── Search within type
   └── Click component → component detail

4. User clicks component → /{orgId}/metadata/ApexClass/OrderController
   ├── Context panel opens:
   │   ├── Properties: Name, Namespace, Status, ApiVersion
   │   ├── Metrics: 3 dependencies upstream, 12 downstream
   │   └── Quick Actions: Show Dependencies, Analyze Impact, View Docs
   │
   ├── User clicks "Show Dependencies"
   │   │
   │   ▼
   │   /{orgId}/dependencies/OrderController
   │   ├── Graph view loads (force-directed layout)
   │   ├── Context panel switches to "Dependency Details"
   │   └── User explores upstream/downstream tree

5. User clicks "Analyze Impact"
   │
   ▼
   /{orgId}/impact?component=OrderController
   ├── Impact analysis triggers (POST /api/v1/impact)
   ├── WebSocket streams progress
   └── Results display: 8 components affected, 2 high-risk

6. User opens AI Workspace
   │
   ▼
   /{orgId}/ai
   ├── Chat interface with context awareness
   ├── "Explain the impact of modifying OrderController"
   ├── AI streams response via WebSocket
   └── User can save analysis to history
```

### 10.3 Error Recovery Flow

```
User navigates to /{orgId}/metadata
  │
  ▼
Guard check:
  ├── Org not found → /organizations?error=not_found
  ├── Auth token expired:
  │   │
  │   ▼
  │   Auto-refresh token (axios interceptor)
  │   ├── Success → retry original request silently
  │   └── Failed → redirect to /auth/login?returnTo=/{orgId}/metadata
  │
  ├── Network error:
  │   │
  │   ▼
  │   Offline state:
  │   ├── Status bar: "Offline" (red indicator)
  │   ├── Show cached data if available (with "cached" badge)
  │   ├── Mutations disabled (buttons grayed with tooltip)
  │   └── Auto-retry on reconnect
  │
  └── Server error (5xx):
      │
      ▼
  Error boundary:
      ├── Show error state component
      ├── "Something went wrong. Retry? [Retry] [Go to Dashboard]"
      ├── Log correlation ID to console
      └── Auto-retry once after 5 seconds
```

---

## 11. Sequence Diagrams

### 11.1 Global Search

```
┌──────┐         ┌─────────┐        ┌────────┐        ┌────────┐        ┌──────────┐
│ User │         │  UI     │        │ Search │        │ Backend│        │  Search  │
│      │         │         │        │ Store  │        │        │        │  Engine  │
└──┬───┘         └────┬────┘        └───┬────┘        └───┬────┘        └────┬─────┘
   │                  │                 │                 │                  │
   │ Cmd+K            │                 │                 │                  │
   │─────────────────►│                 │                 │                  │
   │                  │                 │                 │                  │
   │                  │ Open palette    │                 │                  │
   │                  │◄────────────────│                 │                  │
   │                  │                 │                 │                  │
   │ Type "order"     │                 │                 │                  │
   │─────────────────►│                 │                 │                  │
   │                  │ setQuery("order")│                │                  │
   │                  │────────────────►│                 │                  │
   │                  │                 │                 │                  │
   │                  │                 │ Debounce 300ms  │                  │
   │                  │                 │                 │                  │
   │                  │                 │ fetchSuggestions│                 │
   │                  │                 │────────────────►│                  │
   │                  │                 │                 │ GET /search/suggest│
   │                  │                 │                 │──────────────────►│
   │                  │                 │                 │                  │
   │                  │                 │                 │   Results        │
   │                  │                 │                 │◄──────────────────│
   │                  │                 │                 │                  │
   │                  │                 │ Set suggestions │                  │
   │                  │                 │◄────────────────│                  │
   │                  │                 │                 │                  │
   │                  │ Show suggestions │                │                  │
   │                  │◄────────────────│                 │                  │
   │                  │                 │                 │                  │
   │ Select result    │                 │                 │                  │
   │─────────────────►│                 │                 │                  │
   │                  │ Navigate to     │                 │                  │
   │                  │ /{orgId}/metadata/ApexClass/OrderController         │
   │                  │────────────────────────────────────────────────────►│
   │                  │                 │                 │                  │
   │                  │ Close palette   │                 │                  │
   │                  │◄────────────────│                 │                  │
   │                  │                 │                 │                  │
   │   Detail View    │                 │                 │                  │
   │◄─────────────────│                 │                 │                  │
```

### 11.2 Dependency Lookup

```
┌──────┐    ┌────────────┐    ┌──────────┐    ┌────────┐    ┌────────────┐
│ User │    │ Dependency │    │  Store   │    │ Backend│    │ Dependency │
│      │    │ Explorer   │    │          │    │        │    │  Graph     │
└──┬───┘    └─────┬──────┘    └────┬─────┘    └───┬────┘    └──────┬─────┘
   │              │                │              │                │
   │ View deps for│                │              │                │
   │ OrderCtrl    │                │              │                │
   │─────────────►│                │              │                │
   │              │                │              │                │
   │              │ Check cache    │              │                │
   │              │───────────────►│              │                │
   │              │                │              │                │
   │              │◄── Cache miss ─│              │                │
   │              │                │              │                │
   │              │ fetchDeps()   │              │                │
   │              │───────────────►│              │                │
   │              │                │ GET /deps/{id}?depth=1       │
   │              │                │──────────────►               │
   │              │                │              │               │
   │              │                │              │ Graph query   │
   │              │                │              │──────────────►│
   │              │                │              │               │
   │              │                │              │   Graph data  │
   │              │                │              │◄──────────────│
   │              │                │              │               │
   │              │                │   Response   │               │
   │              │                │◄──────────────│               │
   │              │                │              │               │
   │              │ Update cache   │              │               │
   │              │◄───────────────│              │               │
   │              │                │              │               │
   │              │ Render graph   │              │               │
   │              │  (force-directed layout)     │               │
   │              │────────────────│              │               │
   │              │                │              │               │
   │  Graph view  │                │              │               │
   │◄─────────────│                │              │               │
   │              │                │              │               │
   │ Click node   │                │              │               │
   │─────────────►│                │              │               │
   │              │                │              │               │
   │              │ Expand depth   │              │               │
   │              │ fetchDeps(depth=2)            │               │
   │              │───────────────►│              │               │
   │              │                │──────────────►               │
```

### 11.3 AI Chat (Streaming)

```
┌──────┐    ┌───────────┐    ┌────────┐    ┌────────┐    ┌──────────┐    ┌───┐
│ User │    │ AI Worksp │    │ AI API │    │ Backend│    │  Prompt  │    │LLM│
│      │    │           │    │        │    │        │    │  Builder │    │   │
└──┬───┘    └─────┬─────┘    └───┬────┘    └───┬────┘    └────┬─────┘    └───┘
   │              │              │             │              │           │
   │ "Analyze the │              │             │              │           │
   │  impact of   │              │             │              │           │
   │  modifying   │              │             │              │           │
   │  OrderCtrl"  │              │             │              │           │
   │─────────────►│              │             │              │           │
   │              │              │             │              │           │
   │              │ POST /ai/chat│             │              │           │
   │              │─────────────►│             │              │           │
   │              │              │             │              │           │
   │              │              │ Enrich with │              │           │
   │              │              │ context     │              │           │
   │              │              │────────────►│              │           │
   │              │              │             │              │           │
   │              │              │             │ Build prompt │           │
   │              │              │             │─────────────►│           │
   │              │              │             │              │           │
   │              │              │             │              │ Prompt    │
   │              │              │             │              │──────────►│
   │              │              │             │              │           │
   │              │              │             │              │  Stream   │
   │              │              │             │              │◄──────────│
   │              │              │             │              │           │
   │              │              │             │ Stream chunks│           │
   │              │              │◄────────────│──────────────│           │
   │              │              │             │              │           │
   │              │ Stream chunk │             │              │           │
   │              │◄─────────────│             │              │           │
   │  Show chunk  │              │             │              │           │
   │◄─────────────│              │             │              │           │
   │              │              │             │              │           │
   │              │   (repeat for each chunk)                │           │
   │              │              │             │              │           │
   │              │              │ stream:done │             │           │
   │              │◄─────────────│             │              │           │
   │              │              │             │              │           │
   │              │ Save to      │             │              │           │
   │              │ history      │             │              │           │
```

### 11.4 Metadata Sync (with WebSocket)

```
┌──────┐    ┌────────┐    ┌────────┐    ┌────────┐    ┌────────────┐    ┌────────────┐
│ User │    │  UI    │    │  WS    │    │ Backend│    │   Worker   │    │ Salesforce  │
│      │    │        │    │ Service│    │        │    │   (Celery) │    │             │
└──┬───┘    └───┬────┘    └───┬────┘    └───┬────┘    └──────┬─────┘    └──────┬─────┘
   │            │            │            │             │                │
   │ Click Sync │            │            │             │                │
   │───────────►│            │            │             │                │
   │            │            │            │             │                │
   │            │ POST /jobs │            │             │                │
   │            │───────────►│            │             │                │
   │            │            │            │ Create job  │                │
   │            │            │            │────────────►│                │
   │            │            │            │             │                │
   │            │            │            │ Job created │                │
   │            │◄────────────│◄───────────│             │                │
   │            │            │            │             │                │
   │ Job "Processing"       │            │             │                │
   │◄───────────│            │            │             │                │
   │            │            │            │             │                │
   │            │            │            │   Job started               │
   │            │            │            │◄────────────│                │
   │            │            │            │             │                │
   │            │            │ WS: job.started          │                │
   │            │            │◄───────────│             │                │
   │            │            │            │             │                │
   │            │ Notify store            │             │                │
   │            │◄───────────│            │             │                │
   │            │            │            │             │                │
   │ Status: "Processing..."             │             │                │
   │            │            │            │             │                │
   │            │            │            │  Fetch metadata             │
   │            │            │            │────────────►│                │
   │            │            │            │             │ GET /tooling   │
   │            │            │            │             │──────────────►│
   │            │            │            │             │                │
   │            │            │            │             │   Components   │
   │            │            │            │             │◄───────────────│
   │            │            │            │             │                │
   │            │            │            │             │ Process batch  │
   │            │            │            │             │                │
   │            │            │ WS: job.progress(45%)   │                │
   │            │            │◄───────────│────────────►│                │
   │            │            │            │             │                │
   │            │ Notify store            │             │                │
   │            │◄───────────│            │             │                │
   │            │            │            │             │                │
   │ Progress: 45%           │            │             │                │
   │            │            │            │             │                │
   │            │            │            │  (repeat for each batch)    │
   │            │            │            │             │                │
   │            │            │            │  Sync complete              │
   │            │            │            │◄────────────│                │
   │            │            │            │             │                │
   │            │            │ WS: job.completed        │                │
   │            │            │◄───────────│             │                │
   │            │            │            │             │                │
   │            │ Notify + invalidate     │             │                │
   │            │◄───────────│            │             │                │
   │            │            │            │             │                │
   │ Status: "Sync complete (285 items)" │             │                │
   │◄───────────│            │            │             │                │
   │            │            │            │             │                │
   │ Toast: "Metadata sync complete"     │             │                │
```

### 11.5 Authentication Flow

```
┌──────┐    ┌───────────┐    ┌──────────┐    ┌────────┐    ┌──────────────┐
│ User │    │   Shell   │    │ Auth     │    │ Backend│    │ chrome.storage│
│      │    │           │    │ Store    │    │        │    │              │
└──┬───┘    └─────┬─────┘    └────┬─────┘    └───┬────┘    └──────┬───────┘
   │              │              │              │               │
   │ Open workspace              │              │               │
   │─────────────►│              │              │               │
   │              │              │              │               │
   │              │ Check stored │              │               │
   │              │ session      │              │               │
   │              │─────────────►│              │               │
   │              │              │              │               │
   │              │              │ GET from     │               │
   │              │              │ storage      │               │
   │              │              │───────────────│──────────────►│
   │              │              │              │               │
   │              │              │◄─── null ────│◄──────────────│
   │              │              │              │               │
   │              │ No session   │              │               │
   │              │◄─────────────│              │               │
   │              │              │              │               │
   │ Redirect to  │              │              │               │
   │ /auth/login  │              │              │               │
   │◄─────────────│              │              │               │
   │              │              │              │               │
   │ Enter API key│              │              │               │
   │─────────────►│              │              │               │
   │              │ POST /auth   │              │               │
   │              │─────────────►│              │               │
   │              │              │ POST /api/v1/auth/login      │
   │              │              │──────────────►               │
   │              │              │              │               │
   │              │              │  Validate API key            │
   │              │              │◄──────────────│               │
   │              │              │              │               │
   │              │              │ Set session   │              │
   │              │◄─────────────│              │               │
   │              │              │              │               │
   │              │ Save to      │              │               │
   │              │ storage      │              │               │
   │              │───────────────│─────────────│──────────────►│
   │              │              │              │               │
   │              │ Navigate to dashboard      │               │
   │              │───────────────────────────►│               │
   │              │              │              │               │
   │ Dashboard    │              │              │               │
   │◄─────────────│              │              │               │
```

---

## 12. Data Flow Diagrams

### 12.1 Unidirectional Data Flow

```
                    ┌─────────────────────┐
                    │     User Action      │
                    │  (click, type, nav)  │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   React Component   │  ← Event handler fires
                    │    (Event Handler)   │
                    └──────────┬──────────┘
                               │
                    ┌──────────┴──────────┐
                    │                     │
                    ▼                     ▼
          ┌─────────────────┐  ┌──────────────────┐
          │  Zustand Store  │  │ TanStack Query   │
          │  (UI action)    │  │ useMutation /    │
          │                 │  │ useQuery         │
          │  setState(...)  │  │                  │
          └────────┬────────┘  │ mutate(fn)       │
                   │           └────────┬─────────┘
                   │                    │
                   └────────┬───────────┘
                            │
                            ▼
                  ┌───────────────────┐
                  │    API Layer      │  ← Only HTTP-capable layer
                  │  api.module.fn()   │
                  └────────┬──────────┘
                           │
                    HTTP Request
                           │
                           ▼
                  ┌───────────────────┐
                  │     Backend       │
                  └───────────────────┘
                           │
                    HTTP Response
                           │
                           ▼
                  ┌───────────────────┐
                  │    API Layer      │  ← Parse, normalize, return
                  └────────┬──────────┘
                           │
                    ┌──────┴──────┐
                    │             │
                    ▼             ▼
           ┌────────────┐  ┌──────────┐
           │ Zustand    │  │TanStack  │
           │ Store      │  │ Query    │
           │ update     │  │ cache    │
           └──────┬─────┘  │ update   │
                  │        └────┬─────┘
                  │             │
                  └──────┬──────┘
                         │
                         ▼
                  ┌──────────────┐
                  │  Component   │  ← Re-renders with new state
                  │  (React)      │
                  └──────────────┘
                         │
                         ▼
                  ┌──────────────┐
                  │     DOM      │
                  └──────────────┘
```

### 12.2 Error Data Flow

```
                    ┌──────────────┐
                    │  API Call    │
                    │  fails       │
                    └──────┬───────┘
                           │
                           ▼
              ┌─────────────────────┐
              │ Axios Error         │
              │ Interceptor         │
              │                     │
              │ Normalize to ApiError│
              │                     │
              │ If 401: auto-refresh│
              │ If 429: enqueue retry│
              └──────────┬──────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │ TanStack Query      │
              │ onError callback    │
              │                     │
              │ Rollback optimistic │
              │ Notify error store  │
              └──────────┬──────────┘
                         │
              ┌──────────┴──────────┐
              │                     │
              ▼                     ▼
    ┌─────────────────┐  ┌────────────────────┐
    │ Notification    │  │ Component          │
    │ Store           │  │                    │
    │                 │  │ showInlineError()  │
    │ addToast(error) │  │ or showEmptyState()│
    └─────────────────┘  └────────────────────┘
```

### 12.3 WebSocket Data Flow

```
                    ┌─────────────────┐
                    │ WebSocket Server │
                    │  (Backend)       │
                    └────────┬─────────┘
                             │
                    WS Message (JSON)
                             │
                             ▼
                    ┌─────────────────┐
                    │ WebSocket       │
                    │ Service         │
                    │                 │
                    │ Parse message   │
                    │ Route by type   │
                    └────────┬─────────┘
                             │
                    ┌────────┴────────┐
                    │                 │
                    ▼                 ▼
          ┌─────────────────┐  ┌─────────────────┐
          │ Notification    │  │ TanStack Query  │
          │ Store           │  │ Cache Invalidation
          │                 │  │                 │
          │ addNotification │  │ invalidateQueries
          │ updateUnread    │  │ refetch         │
          └────────┬────────┘  └────────┬────────┘
                   │                    │
                   ▼                    ▼
          ┌─────────────────┐  ┌─────────────────┐
          │ React Component │  │ React Component │
          │ Bell icon (badge)│  │ Data table      │
          └─────────────────┘  └─────────────────┘
```

---

## 13. Performance Strategy

### 13.1 Loading Strategy

| Technique | Application | Target |
|---|---|---|
| **Route-level code splitting** | `React.lazy(() => import('./features/dashboard'))` | Each feature module is its own chunk |
| **Component-level splitting** | Dynamic import for heavy components (graph viz, JSON viewer) | Dependency graph, documentation viewer |
| **Library splitting** | Vendor chunks for React, Zustand, TanStack Query, D3 | Stable deps cached separately |
| **CSS code splitting** | Per-module CSS loaded with module | No unused CSS in initial bundle |
| **Font loading** | `font-display: swap` + preload | No FOIT |
| **Icon loading** | SVG sprite loaded on demand | No icon bloat in initial bundle |

### 13.2 Rendering Strategy

| Pattern | Application | Benefit |
|---|---|---|
| **Virtualized lists** | `@tanstack/virtual` for metadata lists, component lists, doc lists | DOM nodes = visible rows only |
| **Memoization** | `useMemo`, `React.memo`, `useCallback` for expensive computations | Graph layouts, filtered lists, sorted tables |
| **Debounced search** | 300ms debounce on search inputs | Avoid API call per keystroke |
| **Optimistic updates** | Immediate UI update before API confirmation | Perceived instant responses |
| **Skeleton loading** | Layout-matching skeleton for every page | No layout shift, perceived fast loading |
| **Progressive rendering** | Stream AI responses, render as chunks arrive | No waiting for full response |
| **Request deduplication** | TanStack Query `staleTime` + `queryKey` dedup | No duplicate API calls |

### 13.3 Data Strategy

| Pattern | Application |
|---|---|
| **Stale-while-revalidate** | Show cached data immediately, refresh in background |
| **Prefetching** | Prefetch metadata list on hover over sidebar nav item |
| **Pagination** | Server-side pagination for large lists (metadata components, jobs) |
| **Infinite scroll** | For search results, notification history |
| **Request cancellation** | Abort previous search request on new keystroke |
| **Batch requests** | Composite API calls for related data |
| **Persistent cache** | TanStack Query `persister` with chrome.storage for offline resilience |

### 13.4 Bundle Budget

| Asset | Budget | Monitoring |
|---|---|---|
| Initial JS (gzipped) | `< 150 KB` | `vite-bundle-analyzer` |
| Initial CSS (gzipped) | `< 30 KB` | CSS stats |
| Feature module chunk | `< 50 KB` each | CI bundle check |
| Vendor chunk | `< 80 KB` | `vite-bundle-analyzer` |
| Total extension size | `< 5 MB` | Build size check |
| Lighthouse Performance | `> 85` | CI Lighthouse check |

### 13.5 Cache Invalidation

| Trigger | Action |
|---|---|
| Metadata sync completes | `invalidateQueries(['metadata', orgId])` |
| Org switch | `resetQueries()` for previous org queries |
| User clicks "Refresh" | `refetchQueries()` for active module queries |
| WebSocket `metadata.sync.completed` | `invalidateQueries(['metadata', orgId])` |
| WebSocket `job.completed` | `invalidateQueries(['jobs', orgId])` |
| Theme change | No invalidation (CSS variables only) |

---

## 14. Extensibility Strategy

### 14.1 Plugin System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PLUGIN SYSTEM                                │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    Plugin Registry                            │   │
│  │                                                                  │   │
│  │  register(manifest: PluginManifest) → void                     │   │
│  │  unregister(id: string) → void                                 │   │
│  │  getManifests() → PluginManifest[]                             │   │
│  │  getById(id: string) → PluginManifest | undefined             │   │
│  │                                                                  │   │
│  │  PluginManifest {                                               │   │
│  │    id: string               // Unique plugin ID                │   │
│  │    name: string             // Display name                    │   │
│  │    version: string          // Plugin version                  │   │
│  │    description: string                                          │   │
│  │    routes: RouteDefinition[]  // Plugin routes                 │   │
│  │    navItems: NavItem[]        // Sidebar items                 │   │
│  │    commands: CommandDef[]     // Command palette entries       │   │
│  │    hooks: PluginHooks         // Lifecycle hooks               │   │
│  │    permissions: string[]      // Required permissions          │   │
│  │  }                                                              │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    Extension Slots                             │   │
│  │                                                                  │   │
│  │  SIDEBAR                                                        │   │
│  │  ├── sidebar.before        // Before core navigation           │   │
│  │  ├── sidebar.after         // After core navigation            │   │
│  │  └── sidebar.bottom        // Below navigation (utilities)     │   │
│  │                                                                  │   │
│  │  WORKSPACE                                                      │   │
│  │  ├── workspace.header.left   // Left side of header            │   │
│  │  ├── workspace.header.right  // Right side of header           │   │
│  │  ├── workspace.toolbar       // Context toolbar                │   │
│  │  └── workspace.footer        // Status bar area                │   │
│  │                                                                  │   │
│  │  CONTEXT                                                         │   │
│  │  ├── context.panel.top       // Top of context panel           │   │
│  │  ├── context.panel.bottom    // Bottom of context panel        │   │
│  │  └── context.menu            // Context menu entries           │   │
│  │                                                                  │   │
│  │  COMMANDS                                                       │   │
│  │  ├── commands.global         // Global command palette entries │   │
│  │  └── commands.contextual     // Context-aware commands         │   │
│  │                                                                  │   │
│  │  PROVIDERS                                                      │   │
│  │  ├── ai.provider             // Register AI LLM provider       │   │
│  │  ├── search.provider         // Register search backend        │   │
│  │  ├── graph.algorithm         // Register graph layout algo     │   │
│  │  └── theme.provider          // Register theme variant         │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 14.2 Plugin Lifecycle

```
Plugin Load
  │
  ├── validate(manifest) → true/false
  ├── checkPermissions(manifest.permissions) → grant/deny
  ├── registerRoutes(manifest.routes) → route entries added
  ├── injectNavItems(manifest.navItems) → sidebar updated
  ├── registerCommands(manifest.commands) → palette updated
  └── callHook(manifest.hooks.onLoad) → plugin initializes
       │
       ▼
Plugin Active
  │
  ├── Routes accessible under /plugins/{pluginId}/*
  ├── Commands available in palette
  ├── Context menus available on matching items
  └── WebSocket messages routed if subscribed
       │
       ▼
Plugin Unload
  ├── callHook(manifest.hooks.onUnload) → plugin cleans up
  ├── unregisterRoutes() → route entries removed
  ├── removeNavItems() → sidebar reverted
  ├── unregisterCommands() → palette cleaned
  └── cleanPluginStore() → plugin state garbage collected
```

### 14.3 Extension Points Defined

| Extension Point | Interface | Example Usage |
|---|---|---|
| **AI Provider** | `AIMessage → AsyncStream<AIChunk>` | Register OpenAI, Anthropic, or local LLM as AI backend |
| **Search Provider** | `SearchQuery → SearchResults` | Replace backend search with Salesforce SOSL |
| **Graph Algorithm** | `GraphData → LayoutConfig` | Register hierarchical, radial, or custom layout |
| **Metadata Type Handler** | `MetadataType → MetadataView` | Custom viewer for custom metadata types |
| **Theme Provider** | `→ ThemeTokens` | Custom brand theme for enterprise branding |
| **Command** | `Context → void` | Register custom commands in palette |
| **Context Action** | `SelectedItem → Action[]` | Add actions to context menu |
| **Dashboard Widget** | `→ React.Component` | Add widget to dashboard grid |
| **Notification Channel** | `→ Notification[]` | Receive notifications from external system |

### 14.4 Plugin Security

| Rule | Explanation |
|---|---|
| Plugins are restricted to their own store namespace | `stores.plugins.{pluginId}` — cannot access other stores directly |
| Plugins cannot access chrome.* APIs | Extension security boundary; must use exposed service interfaces |
| Plugins must declare permissions in manifest | Users see permission grants on plugin install |
| Plugins run in a sandboxed iframe (optional) | For untrusted third-party plugins |
| Plugins are subject to rate limits | API calls, WebSocket messages, storage writes |
| Dangerous APIs (eval, fetch to arbitrary origins) are blocked | Content Security Policy enforced |

---

## 15. Risks

### 15.1 Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Extension CSP blocks WebSocket** | Low | High | Test early. Use conditional WebSocket URL patterns. Fallback to SSE if blocked. |
| **Service worker lifecycle kills WebSocket** | Medium | Medium | SW wake lock + reconnection strategy. Use chrome.runtime.connect for long-lived port. |
| **backend_service.js localStorage keys conflict** | Low | Medium | Workspace uses its own key prefix (`enterprise.*`). Legacy keys untouched. |
| **Chrome extension CSP blocks fetch to non-HTTPS** | Medium | Low | Backend URL defaults to HTTPS. Document local dev setup (localhost exempt). |
| **Extension update kills workspace session** | High | Medium | Session stored in chrome.storage (survives SW restart). Reconnect on workspace load. |
| **Vite dev server CORS in extension context** | Medium | Low | Use Vite's HTTPS + cert for development. Extension pages have relaxed CORS. |
| **React Router v7 breaking changes** | Low | Medium | Pin version. Use stable APIs. Follow migration guide. |
| **Zustand v5 breaking changes** | Low | Low | Pin version. Zustand has minimal API surface — migration is trivial. |
| **SLDS v2.x breaking changes** | Low | Low | Pin SLDS version. Only CSS variables used — upgrade is isolated. |
| **Multiple Chrome extension messaging conflicts** | Low | Medium | Workspace uses its own message channel prefix. Listeners check message source. |

### 15.2 Integration Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Legacy extension update overwrites workspace** | Medium | High | Workspace lives in `addon/enterprise/` — same folder. Git merge handles this. CI checks workspace integrity. |
| **manifest.json merge conflicts** | Medium | High | The 3 additive changes are minimal and documented. Every release checks manifest for workspace entries. |
| **background.js message handler conflicts** | Low | Medium | Workspace handlers use distinct message types (`enterprise:*` prefix). No overlap with legacy `handleMessage` types. |
| **Legacy button.js changes break popup integration** | Low | Medium | Button integration is a single additive nav option. If legacy removes it, workspace link disappears (not breaks). |

### 15.3 User Experience Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Context switch between legacy and workspace** | High | Medium | Workspace is intentionally separate (new tab). Users don't context-switch mid-workflow. |
| **Learning curve for workspace navigation** | Medium | Low | Standard SPA patterns (sidebar, breadcrumb, search). Familiar to any enterprise tool user. |
| **Expectation of feature parity with legacy** | Medium | Medium | Workspace is additive, not a replacement. Document "what's different" in workspace. |
| **Backend dependency for all operations** | High | Medium | Some features require backend. Workspace cannot function without it. Show connection status always visible. |

---

## 16. Trade-offs

### 16.1 Architecture Trade-offs

| Decision A | Decision B | Chosen | Rationale |
|---|---|---|---|
| **Zustand + TanStack Query** | Single state manager (Redux, Jotai) | **Zustand + TanStack Query** | TanStack Query eliminates 70% of boilerplate (loading/error/caching/refetch). Zustand handles the remaining client state with minimal API. Redux would add ceremony without benefit. |
| **Route-level code splitting** | Component-level code splitting | **Route-level** | Feature modules are the natural split boundary. Component-level splitting adds complexity with marginal gain — chunks match user navigation patterns. |
| **Workspace in new tab** | Workspace in popup iframe | **New tab** | Full screen real estate. No iframe sandbox restrictions. Browser tabs are a familiar workspace metaphor. Popup iframe would be too constrained for data-heavy tools. |
| **WebSocket (persistent)** | SSE (server-sent events) | **WebSocket** | Bidirectional communication needed (user actions, subscriptions). SSE is unidirectional (server→client). WebSocket provides full duplex with lower overhead than polling. |
| **chome.storage for persistence** | localStorage | **chrome.storage** | Extension-scoped, survives SW restarts, not accessible to page JS. localStorage is per-origin and visible to all extension pages. chrome.storage is the correct choice for sensitive data. |
| **Pure TypeScript (no runtime validation)** | Zod / io-ts for runtime validation | **Pure TS + Zod at API boundary** | TypeScript provides compile-time safety. Zod validates API responses at runtime (the trust boundary). Reduces false confidence from "trusting" API types. |
| **CSS Modules** | Styled Components / CSS-in-JS | **CSS Modules** | Zero runtime cost. Static extraction. Predictable bundle size. Compatible with SLDS design tokens. CSS-in-JS adds runtime overhead unsuitable for a large SPA. |
| **React Router v7** | TanStack Router | **React Router v7** | More mature ecosystem. Simpler nested routing. TanStack Router is newer with fewer community resources. React Router v7 with loaders covers all needs. |
| **Feature modules in single repo** | Monorepo with separate packages | **Single repo** | Simpler tooling (Vite handles multi-entry). No cross-package versioning. Shared types are just imports. Monorepo overhead not justified for a single-SPA workspace. |

### 16.2 Integration Trade-offs

| Decision A | Decision B | Chosen | Rationale |
|---|---|---|---|
| **Reuse background.js session** | Independent OAuth in workspace | **Reuse background.js** | Avoids duplicating complex OAuth PKCE flow. Leverages existing, tested session resolution. Adds minimal coupling (single message type). |
| **Workspace as co-located SPA** | Workspace as separate Chrome extension | **Co-located** | Single extension install. Shared session. No cross-extension messaging complexity. Chrome Web Store review only for one extension. Trade-off: bundle size coupling. |
| **Zero modifications to legacy** | Refactor legacy to share code | **Zero modifications** | No regression risk. Legacy tests continue passing. Workspace can be developed independently. Trade-off: some code duplication (component porting). |

### 16.3 UX Trade-offs

| Decision A | Decision B | Chosen | Rationale |
|---|---|---|---|
| **Dashboard first** | Metadata Explorer first | **Dashboard** | Users need an overview: sync health, recent activity, quick actions. Starting in metadata would be disorienting without context. |
| **Context panel always visible** | Context panel as overlay | **Always visible (desktop)** | Metadata workers need persistent property inspection. Overlay pattern breaks flow. On small screens, overlay is acceptable trade-off. |
| **Dark mode day one** | Dark mode later | **Dark mode day one** | Enterprise developers work extended hours. Dark mode is not optional — it's a health and accessibility requirement. Designing it in later would require re-theming all components. |

---

## 17. Recommendations

### 17.1 Implementation Order

```
PHASE 3 — Foundation (Week 1-2)
├── Scaffold Vite + React + TypeScript project in addon/enterprise/
├── Implement design tokens (core + semantic + component)
├── Implement theme provider (light + dark)
├── Build API layer (Axios instance, interceptors, error normalization)
├── Implement auth service + auth store
├── Build login page
├── Implement route guards
└── Write integration tests for auth flow

PHASE 4 — Application Shell (Week 3-4)
├── Build Header (logo, global search trigger, org switcher, user menu)
├── Build Sidebar (navigation, favorites, recent, plugins)
├── Build Status Bar (connection health, sync status, version)
├── Build Context Panel (resizable, collapsible, context-aware)
├── Implement responsive layout + breakpoints
├── Implement panel persistence (sizes, collapse state)
└── Build Command Palette (search, navigate, actions)

PHASE 5 — Core Modules (Week 5-8)
├── Build Dashboard module (overview, quick actions, recent activity)
├── Build Organizations module (list, detail, setup wizard)
├── Build Metadata Explorer (type list, component list, component detail)
├── Build Search module (search UI, results, filters, saved searches)
├── Build Settings module (global + per-org, API key management)
└── Build Notifications module (list, preferences, WebSocket integration)

PHASE 6 — Advanced Modules (Week 9-12)
├── Build Dependency Explorer (graph view, tree view, path finder)
├── Build Impact Analysis (analysis trigger, results, comparison)
├── Build Documentation Viewer (list, viewer, version history)
├── Build AI Workspace (chat interface, streaming, history, prompt library)
├── Build Sync Jobs (list, detail, progress via WebSocket)
└── Write E2E tests for all modules

PHASE 7 — Integration (Week 13)
├── Add 3 hooks to legacy extension (manifest, button, background)
├── Integration testing (workspace ↔ legacy ↔ backend)
├── Performance optimization (bundle analysis, lazy loading audit)
├── Accessibility audit (keyboard navigation, screen reader, contrast)
└── Production readiness (error tracking, monitoring, docs)
```

### 17.2 Technology Choices (Recommended)

| Category | Choice | Why |
|---|---|---|
| **Build tool** | Vite 6 | Fast HMR, TypeScript native, plugin ecosystem |
| **UI framework** | React 19 | Team familiarity, ecosystem maturity |
| **Language** | TypeScript 5 | Type safety, IDE support, self-documenting |
| **Routing** | React Router v7 | Nested routes, loaders, mature ecosystem |
| **Client state** | Zustand 5 | Minimal boilerplate, no providers, React hooks |
| **Server state** | TanStack Query 5 | Caching, dedup, refetch, optimistic updates |
| **HTTP client** | Axios | Interceptors, cancellation, wide adoption |
| **Virtualization** | @tanstack/virtual | Performant large lists |
| **Design system** | Custom (CSS Modules + tokens) | SLDS-inspired, lightweight, zero runtime |
| **Testing** | Vitest + React Testing Library | Fast, Vite-native, component testing |
| **E2E** | Playwright | Cross-browser, reliable selectors |
| **Linting** | ESLint 9 + Prettier | Consistent code style |
| **Formatting** | Prettier | Automatic formatting |

### 17.3 Things to NOT Do

- **Do NOT** create a separate NPM package for shared types (single repo is simpler)
- **Do NOT** use CSS-in-JS (CSS Modules are sufficient and faster)
- **Do NOT** duplicate session management (reuse background.js)
- **Do NOT** build a custom virtualizer (@tanstack/virtual is battle-tested)
- **Do NOT** support IE11 or legacy browsers (enterprise Chrome extension)
- **Do NOT** use GraphQL (REST is sufficient for this API surface)
- **Do NOT** build a plugin system in Phase 3-6 (Phase 7 or later)
- **Do NOT** implement real-time collaboration (not in scope)
- **Do NOT** add drag-and-drop without proven need (adds complexity)
- **Do NOT** implement i18n in initial release (single-language enterprise tool)

### 17.4 Critical Success Factors

| Factor | How to Achieve |
|---|---|
| **Session reliability** | Reuse background.js session resolution. chrome.storage for persistence. Auto-refresh tokens. |
| **WebSocket reliability** | Exponential backoff, heartbeat, connection state in status bar (always visible). |
| **Performance** | Route-level code splitting, virtualized lists, debounced search, TanStack Query caching. |
| **Developer velocity** | Feature modules as independent units. Shared components as building blocks. Clear module boundaries. |
| **Testability** | API layer is pure functions. Stores are testable without React. Components testable with RTL. |
| **Enterprise UX** | Dark mode, keyboard shortcuts, command palette, responsive layout, resizable panels. |
| **Zero legacy regression** | No modifications to existing extension code. Only additive hooks. Workspace in its own directory. |

---

## Appendix A: Architecture Decision Records

### ADR-001: Workspace as Co-located SPA

**Context**: The workspace must live inside the Salesforce Inspector Reloaded extension but remain completely isolated.

**Decision**: The workspace will be built as a standalone Vite + TypeScript SPA in `addon/enterprise/`. It will be opened via `chrome.tabs.create` to its own HTML page. It will not share any JavaScript, React tree, or state with the legacy popup.

**Consequences**:
- Positive: Complete isolation. No regression risk. Independent development. Zero modification to legacy.
- Negative: Session must be re-established (reuses background.js proxy). No sharing of React components (must be copied/ported). Separate bundle loaded per workspace tab.

### ADR-002: Zustand + TanStack Query for State

**Context**: The workspace needs server state caching and client state management.

**Decision**: Use TanStack Query for all server-originated data (with automatic caching, refetching, stale management) and Zustand for all client-only state (UI state, workspace preferences, auth session).

**Consequences**:
- Positive: TanStack Query eliminates caching boilerplate (70% of state code). Zustand is minimal and hook-based. Separation of concerns is clear.
- Negative: Two state libraries instead of one. Mental model switch between "query" and "store" patterns.

### ADR-003: WebSocket for Real-time Updates

**Context**: The workspace needs real-time updates for sync jobs, notifications, and AI streaming.

**Decision**: Use a single WebSocket connection (per org) with a message router pub/sub pattern. Fall back to SSE if WebSocket is unavailable.

**Consequences**:
- Positive: Full duplex communication. Lower latency than polling. Single connection for all real-time needs.
- Negative: Connection management complexity (reconnect, heartbeat, org switch). Chrome extension CSP may need configuration.

### ADR-004: Design System via CSS Modules + Tokens

**Context**: The workspace needs a consistent, themable UI that supports light and dark mode.

**Decision**: Use CSS Modules with CSS custom properties (design tokens) for styling. Semantic tokens reference core tokens and map to light/dark themes via `[data-theme]` attribute.

**Consequences**:
- Positive: Zero runtime cost. Theme switching is a single attribute change. Tree-shakable. Compatible with SLDS.
- Negative: No runtime dynamic styling (not needed). Requires build step (Vite handles natively).

### ADR-005: Feature Module Isolation

**Context**: Multiple developers will work on different modules. Modules must not couple to each other.

**Decision**: Each feature module is a self-contained directory with its own components, hooks, store slice, API extensions, types, and tests. Modules cannot import from other modules. Cross-module communication happens via URL navigation, shared stores (auth, org), or the event bus.

**Consequences**:
- Positive: Team autonomy. Parallel development. Module can be removed without side effects. Testing is isolated.
- Negative: Some code duplication (shared utilities are extracted to shared/ level). Cross-module coordination requires explicit event contracts.

---

## Appendix B: Key Architectural Contracts

```
API Layer Interface   →   Backend
─────────────────────────────────────────────────────
  Request:  { method, path, headers?, body?, signal? }
  Response: { status, data, headers }
  Error:    { status, code, message, details?, requestId? }

State Store Interface   →   React Component
─────────────────────────────────────────────────────
  Read:     useStore(selector) → value
  Write:    store.action(payload) → void
  Subscribe: store.subscribe(listener) → unsubscribeFn

WebSocket Service Interface   →   Feature Module
─────────────────────────────────────────────────────
  Subscribe: ws.subscribe(type, handler) → unsubscribeFn
  Status:    ws.getStatus() → 'connected' | 'disconnected' | 'connecting'
  Connect:   ws.connect(orgId) → Promise<WebSocket>
  Disconnect: ws.disconnect() → void

Plugin System Interface   →   Plugin Developer
─────────────────────────────────────────────────────
  Register:  plugins.register(manifest) → void
  Slots:     plugins.slot(slotId).add(component) → void
  Events:    plugins.events.on(event, handler) → void
  Store:     plugins.getStore(pluginId) → ZustandStore
```

---

## Appendix C: Performance Budget Checklist

```
Initial Load
├── JS bundle < 150 KB gzipped         [ ] Verify with vite-bundle-analyzer
├── CSS bundle < 30 KB gzipped         [ ] Verify with CSS stats
├── No render-blocking resources       [ ] Lighthouse audit
├── First Contentful Paint < 1.5s      [ ] Lighthouse audit
└── Time to Interactive < 3s           [ ] Lighthouse audit

Runtime
├── 60fps scrolling in virtualized lists [ ] DevTools performance panel
├── No layout thrashing                  [ ] React DevTools profiler
├── AI streaming renders < 16ms per chunk [ ] Profiler
├── Search debounce 300ms                [ ] Verified in user testing
└── API response < 500ms (p95)          [ ] Backend monitoring

Build
├── No unused exports (tree-shaking)    [ ] Bundle analysis
├── No duplicate dependencies           [ ] npm dedupe check
├── CSS is tree-shaken                   [ ] PurgeCSS check
└── Chunks named predictably            [ ] Vite chunk naming config
```
