# FastAPI Backend Architecture Audit

Audit date: 2026-07-30

Scope: `backend/src/sfir_backend`, migrations, and backend tests. This is Phase 1 discovery only. No production code was changed.

## 1. Architecture Diagram

```text
Client / Chrome Extension
  |
  | HTTP, SSE, WebSocket
  v
FastAPI app: sfir_backend.main.create_app
  |
  +-- CORS middleware
  +-- security middleware
  |     +-- RequestValidationMiddleware
  |     +-- SecurityHeadersMiddleware
  |     +-- RateLimitMiddleware, only if explicitly injected
  +-- temporary print request middleware
  +-- RequestLoggingMiddleware
  +-- MetricsMiddleware
  +-- AuthContextMiddleware
  |
  v
API router: /api/v1
  |
  +-- auth, organizations, salesforce, sync, metadata, graph
  +-- dependencies, search, impact, documentation, ai
  +-- jobs, observability, security, admin, health
  |
  v
Dependencies: api.deps
  |
  +-- get_current_user_id -> JWTService.decode_access_token
  +-- get_current_org_id -> contextvar set by AuthContextMiddleware
  +-- get_db -> AsyncSession from Container
  +-- use-case factories -> repositories per request
  |
  v
Service / Use Case Layer
  |
  +-- AuthUseCase, OrganizationUseCase, SalesforceUseCase, RBACUseCase
  +-- SyncCoordinator, GraphService
  +-- AIOrchestrator, AgentService, ConversationManager
  +-- DocumentationEngine, JobEngine, SecurityManager
  |
  v
Metadata Layer
  |
  +-- SalesforceClient -> REST, SOQL, Tooling-like REST paths
  +-- MetadataDownloadManager -> metadata listings and component details
  +-- MetadataPipeline -> parse -> map -> validate -> normalize -> persist -> graph -> search
  +-- Parser systems:
        1. infrastructure.salesforce.parsers, wired into Container/GraphService
        2. infrastructure.parsers, broad but mostly not wired into runtime
  |
  v
AI Layer
  |
  +-- AIOrchestrator -> AIRequestCoordinator
  +-- ContextRetriever, PromptBuilder, provider registry
  +-- ToolRegistry -> metadata/dependency/impact/documentation/code tools
  +-- LLM providers: OpenAI, Anthropic, Ollama registered; Azure/Gemini/OpenRouter/Bedrock exist but not registered
  |
  v
Streaming Layer
  |
  +-- POST /api/v1/ai/chat stream=true -> text/event-stream
  +-- WebSocket /ws -> channel subscription and heartbeat
  |
  v
Persistence Layer
  |
  +-- SQLAlchemy async session
  +-- repositories over users, orgs, roles, sessions, refresh tokens
  +-- Salesforce connections, sync jobs, metadata versions, history, retry queue, stats
  +-- normalized metadata ORM tables exist but are not exported/wired through repositories
```

## 2. Folder Diagram

```text
sfir_backend/
  api/
    deps.py                 FastAPI dependency providers
    errors.py               RFC/problem-style exception handlers
    middleware.py           logging, metrics, auth context
    security_middleware.py  validation, headers, optional rate limit
    websocket.py            /ws connection manager
    dto/                    API DTOs
    v1/routes/              16 route modules
  application/
    use_cases/              auth, org, rbac, salesforce, sync, graph, AI
    pipeline/               metadata pipeline stages, mapper, normalizer, validator
    cache/                  cache service wrappers
    dto/                    application DTOs
  config/
    settings.py             Pydantic settings
    container.py            DI container and service wiring
    startup_validator.py    startup env validation
  domain/
    ai, cache, canonical, documentation, entities, graph, impact, jobs,
    metadata, observability, repositories, search, security, value_objects
  infrastructure/
    cache, database, documentation, graph, impact, jobs, llm, observability,
    parsers, persistence, resilience, salesforce, search, security, time
  ports/
    services/               cache, clock, encryption, queue ports
  services/
    empty namespace packages
  shared/
    exceptions, middleware, utils
  workers/
    celery.py, scheduler.py, tasks/metadata_sync.py
```

## 3. Service Dependency Diagram

```text
Container.startup
  |
  +-- DB engine/session factory
  +-- Redis or NullCache
  +-- cache coordinator + cache services
  +-- observability services
  +-- security services
  +-- parser registry, graph engine, search engine, documentation engine, job engine
  +-- AI services and resilience services
  |
  +-- use-case factories
        |
        +-- AuthUseCase
        |     repos: user, org, org_member, role, session, refresh_token, audit_log
        |     deps: PasswordService, JWTService
        |
        +-- OrganizationUseCase
        |     repos: user, org, org_member, role, audit_log, salesforce_connection, metadata_version
        |     deps: JWTService
        |
        +-- SalesforceUseCase
        |     repos: salesforce_connection, organization, audit_log
        |     deps: SalesforceOAuthService, EncryptionService, SyncCoordinator
        |
        +-- SyncCoordinator
        |     repos: salesforce_connection, sync_job, metadata_version, sync_history,
        |            retry_queue, statistics, audit_log
        |     deps: EncryptionService, MetadataDownloadManager, SalesforceOAuthService,
        |           MetadataPipeline, retry/recovery/hash/manifest helpers
        |
        +-- GraphService
        |     deps: MetadataVersionRepository, infrastructure.salesforce.parsers.ParserRegistry,
        |           CompositeExtractor
        |
        +-- AIOrchestrator
              deps: AIRequestCoordinator, ConversationManager, ProviderRegistry,
                    UsageTracker, circuit breaker, retry, degradation
              coordinator deps: PromptBuilder, ContextRetriever, CitationGenerator,
                                ResponseValidator/Formatter, SafetyFilter, ToolRegistry
```

## 4. Router Map

| Router | Purpose | Dependencies | Auth | Services Used | Responses | Streaming |
| --- | --- | --- | --- | --- | --- | --- |
| `health.py` | Liveness/readiness/status/checks | request app container | Exempt in middleware | HealthCheckManager if present | dict/JSONResponse | No |
| `auth.py` | Register/login/logout/refresh/me | AuthUseCase, user/org deps | register/login/refresh exempt; logout/me Bearer | AuthUseCase, JWT, repos | auth DTOs | No |
| `organizations.py` | Org CRUD and org switch | current user, OrganizationUseCase | Bearer | OrganizationUseCase | org DTOs | No |
| `salesforce.py` | OAuth connect/callback/status/health/disconnect | current user/org, SalesforceUseCase | Bearer | SalesforceUseCase | Salesforce DTOs | No |
| `metadata_sync.py` | Start/list/control sync jobs | current user/org, SyncCoordinator | Bearer | SyncCoordinator | sync DTOs | No |
| `metadata.py` | Browse synced metadata versions | org, metadata version repo | Missing explicit user dep; relies on middleware org context | MetadataVersionRepository | dict | No |
| `graph.py` | Build/query dependency graph | org, GraphService | Missing explicit user dep; relies on middleware org context | GraphService | dict | No |
| `dependencies.py` | Dependency views/trees/reverse graph | user/org, RBACUseCase, GraphService | Bearer | GraphService | dict | No |
| `search.py` | Metadata search/autocomplete | user/org, RBACUseCase, MetadataVersionRepository | Bearer | repo search methods | SearchResponse/list | No |
| `impact.py` | Impact analysis/simulation/report lookup | user/org, RBACUseCase, GraphService | Bearer | GraphService | Impact DTOs | No |
| `documentation.py` | List/generate/export/get docs | user/org, RBACUseCase, DocumentationEngine, GraphService | Bearer | DocumentationEngine | doc DTOs | No |
| `ai.py` | Conversations, chat, explain, summarize, providers, tools | mixed: current user/org, container, conversation manager | Some endpoints lack user/org deps | AIOrchestrator, AgentService, ConversationManager | AI DTOs/dicts | `POST /chat` SSE when `stream=true` |
| `jobs.py` | Job listing/control/progress/metrics/workers | org, JobEngine | Mostly missing user dep | JobEngine | job DTOs/dicts | No |
| `observability.py` | Health/diagnostics/status | request app container | Exempt by lack of user dep | ObservabilityManager | health/diagnostic DTOs | No |
| `security.py` | Security status/audit/policies/evaluate | SecurityManager, user/org | Bearer | SecurityManager | dict | No |
| `admin.py` | Admin users/orgs/audit/system/config/cache/version | `_require_admin`, container | Partly broken: cache/version skip admin dep | SecurityManager/cache stubs | admin DTOs/dicts | No |
| `main.py /ws` | WebSocket channel subscription | token query param | JWT query token | WebSocketManager | JSON messages | WebSocket |

## 5. Service Map

| Service | Inputs | Outputs | Responsibilities | Dependencies | Used By | Test Coverage |
| --- | --- | --- | --- | --- | --- | --- |
| `AuthUseCase` | register/login/refresh/user IDs | auth DTOs | user auth, sessions, refresh tokens, audit logs | repos, PasswordService, JWTService | auth routes | unit auth tests |
| `OrganizationUseCase` | org requests/user/org IDs | org DTOs, access token on switch | org CRUD, membership checks, role permissions | repos, JWTService | org routes | unit org tests |
| `RBACUseCase` | user, org, permission | bool/raises/permission set | permission enforcement | org_member, role repos | search/deps/docs/impact routes | unit rbac tests |
| `SalesforceUseCase` | OAuth/connect/status requests | Salesforce DTOs | OAuth, encrypted tokens, health, initial sync job creation | connection/org/audit repos, OAuth, encryption, SyncCoordinator | salesforce routes | unit salesforce tests |
| `SyncCoordinator` | sync job/request | sync job/history/stats DTOs | lifecycle for sync jobs and Salesforce metadata download | many sync repos, downloader, pipeline, OAuth/encryption | sync routes, workers, SalesforceUseCase | unit metadata_sync tests |
| `GraphService` | org ID, component type/name | DependencyGraph/dicts | build graph from `metadata_versions`, resolve deps/impact/cycles | metadata repo, Salesforce parser registry, extractor | graph/deps/impact/docs/AI tools | graph tests indirectly |
| `MetadataPipeline` | PipelineContext | PipelineResult | stage orchestration | parser/map/validate/normalize/persist/graph/search stages | SyncCoordinator | pipeline tests |
| `DocumentationEngine` | graph/request/component key | documentation reports/pages/export strings | generate reports from graph | internal doc generators/cache/exporter | documentation routes, AI doc tool | unit doc tests |
| `JobEngine` | job operations | job DTO-like state | queue/workers/progress/retry | in-memory job components | jobs routes | unit job tests |
| `SecurityManager` | security queries/events | status/audit/policy results | encryption, audit, abuse, policy, rate limit facade | security subservices/repos/cache | security/admin routes | unit security tests |
| `AIOrchestrator` | query, org/user, provider/model, stream flag | AIResponse or stream events | conversation management and LLM request orchestration | coordinator, providers, usage, resilience | AI routes | unit AI tests |
| `AIRequestCoordinator` | AIRequest/context | AIResponse or events | safety, context retrieval, prompt build, provider call, tools, citations, confidence | LLM infra and ToolRegistry | AIOrchestrator | unit AI tests |
| `AgentService` | query/org/graph/history | dict response | legacy/tool-based agent path | LLM provider, ToolRegistry, GraphService | `/ai/query` | partial tests |
| `ContextRetriever` | org/query/component | text + citations | retrieve metadata/search/graph/doc/impact context | registered retrievers | AI coordinator | unit tests, but not wired |
| `ProviderRegistry` | settings/provider name | provider instance | create LLM providers | OpenAI/Anthropic/Ollama only | AI coordinator/orchestrator | unit provider tests |
| `ConversationManager` | user/org/conversation/messages | conversation dict/history | in-memory conversation state | ConversationMemory | AI routes/orchestrator | unit AI tests |
| `MetadataDownloadManager` | metadata type/SOQL/component ID | Salesforce records/detail | Salesforce metadata download facade | SalesforceClient | SyncCoordinator | unit sync tests |
| `SalesforceClient` | REST/SOQL paths | JSON/list records | Salesforce HTTP client with retries/circuit breaker | httpx | downloader, SalesforceUseCase | unit salesforce tests |
| `SearchEngine` | components/query | indexed docs/search results | in-memory search index and ranking | search services | pipeline search stage | unit search tests |
| `DependencyGraphEngine` | canonical/normalized docs | Graph | in-memory graph build/traversal/stats | graph infra | pipeline graph stage, docs engine when injected | unit graph tests |
| `ImpactAnalysisEngine` | graph/component changes | impact domain models | rich impact simulation/deployment/delete/rename | graph engine + impact analyzers | not wired in container/routes | unit impact tests |
| cache services | cache keys/scopes | cache values/metrics | component-specific caching wrappers | CacheCoordinator | container/security services | unit cache tests |

## 6. Existing Architecture

- Intended architecture is hexagonal/clean-ish: `domain` interfaces and models, `application` use cases, `infrastructure` implementations, `api` adapters, `config.Container` composition root.
- Actual architecture is pragmatic and leaky: application services import infrastructure directly; some infrastructure imports application use cases.
- Domain layer is clean by static import scan: no domain imports outside `domain`/`shared`.
- Static import cycle check found `0` module cycles.
- Backend source size is about `44,730` Python lines.
- Largest files: `engineering_tools.py` 1139, `container.py` 1054, `metadata_sync.py` 1027, `sync_repos.py` 608, `metadata_components.py` 561, `documentation/reports.py` 550.

## 7. AI Component Map

- Route entry: `POST /api/v1/ai/chat`.
- Non-stream path: route -> `AIOrchestrator.chat` -> `AIRequestCoordinator.process_request` -> safety -> `ContextRetriever.retrieve_all_context` -> prompt -> `provider.chat` -> response validation/citation extraction.
- Stream path: route -> `AIOrchestrator.stream_chat` -> `AIRequestCoordinator.process_request_stream` -> safety/injection filter -> context -> prompt -> `provider.chat_stream(tools=...)` -> token/tool/citation/confidence/next_action/done SSE events.
- Tool registry includes graph tools plus engineering tools for field impact, dependency analysis, impact/safe delete/deployment risk, metadata analysis, code intelligence/review/security, documentation generation.
- Critical gap: `ContextRetriever` is created but no retrievers are registered in `Container._make_ai_orchestrator`.
- Critical gap: non-stream chat does not enforce backend tool execution.
- Critical gap: several engineering tools manufacture `uuid.uuid4()` as `org_id`, so tool output is not tied to authenticated tenant context.
- Provider registry only registers OpenAI, Anthropic, and Ollama. Azure, Gemini, OpenRouter, and Bedrock providers exist but are not wired.

## 8. Metadata Component Map

- Downloader supports generic `get_metadata_components`, detail fetch, sobjects describe, Apex, triggers, flows, profiles, permission sets, validation rules, layouts, record types, workflow rules, approval processes, reports, dashboards, email templates, labels, value sets, roles, queues, sharing rules.
- Sync uses `KNOWN_METADATA_TYPES` and generic SOQL `SELECT Id, Name, LastModifiedDate FROM <type>`.
- Runtime graph parser registry registers only:
  - `ApexClassParser`
  - `ApexTriggerParser`
  - `CustomObjectParser`
  - `LayoutParser`
  - `ValidationRuleParser`
- Runtime graph extractor registers only:
  - `ApexDependencyExtractor`
  - `ProfileDependencyExtractor`
  - `LayoutDependencyExtractor`
  - `ValidationRuleDependencyExtractor`
- A richer `infrastructure/parsers` package exists for fields, objects, relationships, flows, permission sets, profiles, reports, dashboards, custom metadata/settings, integrations, UI, workflow, approval process, etc., but it is not the parser registry wired into the container.
- Normalized metadata ORM tables exist and migrations create them, but repositories and runtime paths primarily use `metadata_versions`.

## 9. Authentication Component Map

- JWT auth service: `JWTService` creates/decodes access tokens and refresh tokens.
- Request auth dependency: `get_current_user_id` requires `Authorization: Bearer <token>`.
- Tenant context: `AuthContextMiddleware` decodes Bearer token and writes `org_id`/`user_id` to contextvars.
- Refresh token/session storage: `refresh_tokens` and `sessions` tables via repositories.
- RBAC: `RBACUseCase` checks org membership role permissions.
- Security subsystem: `SecurityManager` coordinates encryption, session security, authorization, audit, policy, abuse, secrets, event publishing, and rate limiting.
- Gaps:
  - Some routes rely only on `get_current_org_id` and do not depend on `get_current_user_id`, so missing/invalid auth can produce soft `"Organization context required"` instead of authenticated authorization failure.
  - Some routes inject RBAC but never call `require_permission`.
  - Admin `_require_admin` always raises, while several admin cache/version endpoints skip `_require_admin`.

## 10. Streaming Component Map

- SSE: `POST /api/v1/ai/chat` with `stream=true` returns `StreamingResponse(media_type="text/event-stream")`.
- Stream event types in coordinator: `token`, `tool_start`, `tool_complete`, `tool_failed`, `citation`, `confidence`, `next_actions`, `done`, `error`.
- Cancellation support exists through `ResponseStreamer.is_cancelled`.
- WebSocket: `/ws?token=...` authenticates JWT query token, supports subscribe/unsubscribe/pong and heartbeat ping.
- Gaps:
  - WebSocket auth does not set org/tenant context.
  - SSE tool calls depend on provider support and LLM behavior, not deterministic backend routing.

## 11. Database Model Map

Core auth/org:

- `users`, `organizations`, `roles`, `permissions`, `org_members`, `sessions`, `refresh_tokens`, `audit_logs`.

Salesforce and sync:

- `salesforce_connections`, `sync_jobs`, `metadata_versions`, `sync_history`, `sync_retry_queue`, `sync_statistics`.

Normalized metadata:

- `metadata_objects`, `metadata_fields`, `metadata_validation_rules`, `metadata_record_types`, `metadata_apex_classes`, `metadata_triggers`, `metadata_flows`, `metadata_layouts`, `metadata_profiles`, `metadata_permission_sets`, `metadata_reports`, `metadata_dashboards`, `metadata_workflow_rules`, `metadata_relationships`, `metadata_dependencies`, `search_documents`.

Persistence issue:

- `infrastructure/persistence/models/__init__.py` exports core/sync models but not normalized metadata component models.
- Repositories exist for core/sync models, but no repositories were found for normalized metadata component tables.

## 12. Dead Code and Duplicate Services

Likely dead or underwired:

- Empty namespace directories: `application/services/agent`, `domain/services/metadata`, plus empty package families under `services/*`, `domain/policies`, `domain/ports`, `infrastructure/event_bus`, `infrastructure/queue`.
- `api/schemas.py`, `workers/scheduler.py`, `shared/utils/pagination.py`, `shared/utils/id_generation.py`, `infrastructure/cache/tenant_cache.py`, `infrastructure/salesforce/connection_manager.py`, `infrastructure/impact/engine.py`, `ports/services/queue_port.py` have no static internal incoming imports.
- `ImpactAnalysisEngine` is implemented but not registered in `Container`; impact routes use `GraphService` directly instead.
- Azure/Gemini/OpenRouter/Bedrock providers exist but are not registered by `create_provider_registry`.
- Normalized metadata component ORM models exist but are not exported and not backed by repositories.

Duplicate/parallel systems:

- Two parser systems:
  - `infrastructure.salesforce.parsers` is wired into sync/graph.
  - `infrastructure.parsers` is broader and tested but not wired into runtime.
- Two graph concepts:
  - `application.use_cases.graph.GraphService` builds a graph per request from `metadata_versions`.
  - `infrastructure.graph.DependencyGraphEngine` holds an in-memory graph used by pipeline/docs/impact engine.
- Two AI tool paths:
  - `AgentService` in `/ai/query`.
  - `AIOrchestrator`/`AIRequestCoordinator` in `/ai/chat`.
- Documentation generators exist both under application AI and infrastructure documentation.

## 13. TODOs, Placeholders, Mock Responses, Fake Data

No literal production `TODO` list dominates, but placeholder behavior exists:

- `admin._require_admin` always raises `AuthorizationFailedError`.
- `admin._list_users` and `_list_organizations_admin` return empty lists.
- `admin` cache statistics/invalidate/flush return default/success responses without using real cache state.
- `impact._get_impact_analysis` and `_get_impact_report` always return `None`.
- `ContextRetriever` returns unavailable text when retrievers are not registered.
- Noop LLM providers return "LLM not configured" strings.
- AI graph tools return "Graph not available. Build the graph first." if graph is not injected.
- `SearchStage` passes `None` documents into `SearchEngine.index_components` if normalization produced invalid docs.
- `metadata_sync.start_sync` creates a sync job but does not execute it; worker execution is separate.

## 14. Missing Modules and Broken Flows

Missing or broken:

- `Container` does not register `health_check_manager`, but health routes look for that service name. Container registers `health_manager`.
- `Container` registers `DocumentationEngine()` without a graph engine; documentation routes inject `GraphService` but do not use it to populate the engine.
- Startup validation checks `SFIR_SECRET_KEY`/`settings.secret_key`, but settings define `jwt_secret_key`.
- Startup validation requires Python 3.14+, while `pyproject.toml` says `>=3.13`.
- `RateLimitMiddleware` is only added when a rate limiter is passed to `add_security_middleware`; `main.create_app` passes only settings, so request rate limiting is not active there.
- `/api/v1/ai/query` uses `Depends(lambda c: c.get_use_case(...))`; FastAPI does not provide `c`, so this dependency path is suspect.
- `ConversationManager.create_conversation` annotates `Conversation` without importing it; future annotations avoid import-time failure, but the type is unresolved.
- `CanonicalNormalizer` references `NormalizedRelationship` without importing it; this will fail when component relationships are present.
- `SearchStage._normalized_to_search_document` can return `None`, but the result list is passed directly to `SearchEngine.index_components`.
- `get_current_org_id` depends on middleware-set context rather than independently validating membership.

## 15. SOLID and Layer Violations

Single Responsibility:

- `Container`, `SyncCoordinator`, `engineering_tools.py`, `metadata_sync.py`, and `DocumentationEngine` each coordinate too many responsibilities.

Open/Closed:

- Provider registry requires code edits for new providers despite existing provider classes.
- Parser/extractor registry is manually hard-coded in `Container`.

Liskov/Interface Segregation:

- Multiple parser abstractions exist with incompatible result models.
- AI tools return free-form strings instead of typed facts, making downstream contracts weak.

Dependency Inversion:

- Application layer imports infrastructure directly in auth, org, salesforce, sync, graph, AI, and pipeline stages.
- Infrastructure security imports `application.use_cases.rbac`.

Layer violations:

- API routes instantiate repositories directly in `search.py` and `metadata.py`.
- Documentation routes inject `GraphService` but use `DocumentationEngine`'s separate graph state.
- Use cases depend on concrete infrastructure services rather than ports in multiple places.

## 16. Code Quality Report

Static checks run:

```text
./Agent.env/bin/python -m py_compile $(find src/sfir_backend -type f -name '*.py')
Result: passed

./Agent.env/bin/python -m ruff check src/sfir_backend --statistics
Result: failed, 402 lint findings
```

Ruff summary:

- 246 line-too-long
- 35 unused method arguments
- 22 unused imports
- 18 collapsible ifs
- 15 unused function arguments
- 14 unsorted imports
- 7 unused variables
- 2 undefined names

High-signal ruff findings:

- `application/pipeline/normalizer/canonical_normalizer.py`: undefined `NormalizedRelationship`.
- `application/use_cases/ai/conversation_manager.py`: undefined `Conversation` annotation.
- Unused `graph_service` in documentation routes.
- Unused admin/search/impact arguments indicate placeholders or incomplete endpoints.

Targeted tests run:

```text
./Agent.env/bin/python -m pytest tests/audit tests/unit/test_health.py tests/unit/test_settings.py tests/unit/ai -q
145 passed, 5 xfailed
```

Full suite was not run during this audit because integration paths depend on local DB/Redis/service availability.

## 17. Technical Debt Report

High:

- DI container is a 1000+ line composition root with service construction, registry wiring, cache wiring, security wiring, and factory logic all in one class.
- Metadata sync is a 1000+ line coordinator with job control, Salesforce download, retry logic, change detection, persistence, pipeline delegation, token refresh, and statistics.
- AI engineering tools are 1100+ lines and mix backend facts, heuristics, LLM tool contracts, and string formatting.
- Runtime metadata parser coverage is much narrower than domain/persistence model coverage.
- AI grounding is not deterministic.

Medium:

- Route auth/RBAC is inconsistent.
- Documentation, graph, impact, and search have overlapping/in-memory vs DB-backed models.
- Static normalized metadata tables are not integrated into repositories.
- Rate limiting exists but is not active by default in app construction.
- Observability health service name mismatch.

Low:

- Many empty `__init__.py` files are normal, but empty feature directories suggest scaffolding residue.
- Many lint issues are style-only but still create friction for CI and maintainability.

## 18. Production Risks

Critical:

- AI answers can be ungrounded because context retrievers are not wired and non-stream chat directly calls the provider.
- Tenant correctness is unsafe in AI engineering tools that generate random org IDs.
- Some routes expose behavior without explicit `get_current_user_id` dependency.
- Documentation routes likely operate on an empty graph because the engine is not wired to request graph data.

High:

- Startup validation can fail valid configs due `SFIR_SECRET_KEY` mismatch.
- Sync job creation does not guarantee sync execution without worker orchestration.
- Parser/extractor coverage is insufficient for enterprise Salesforce dependency analysis.
- Admin endpoints are either permanently denied or unauthenticated placeholders.
- Normalized metadata tables may drift because they are not first-class repository-backed runtime models.

Medium:

- Rate limiting is not active unless injected.
- Health endpoints use a missing service key and can underreport observability status.
- In-memory conversation state, docs cache, graph engine, and job engine are not durable/distributed.

## 19. Recommended Refactoring Order

Phase 2 should not start with polishing. Recommended order:

1. Freeze route/auth contracts.
   - Decide which endpoints require user auth, org context, and RBAC.
   - Add tests for every route's auth behavior.
2. Fix composition-root wiring.
   - Correct health service name, documentation engine graph source, rate limiter injection, provider registry, and startup validation.
3. Split `Container`.
   - Separate database/cache/security/metadata/AI/worker factories.
4. Consolidate parser architecture.
   - Choose one parser registry/result model.
   - Wire broad metadata parser coverage into sync and graph.
5. Consolidate graph architecture.
   - Decide DB-backed per-request graph vs cached in-memory graph engine.
6. Fix sync execution contract.
   - Make API start route explicitly enqueue/run a worker job or document "create only" behavior.
7. Make AI backend-deterministic.
   - Route questions to typed tools first.
   - Pass authenticated org/user into tools.
   - Return structured facts, citations, and confidence before LLM explanation.
8. Integrate normalized metadata repositories.
   - Either make them authoritative or remove them from runtime expectations.
9. Replace placeholders.
   - Admin, impact report lookup, cache endpoints, documentation graph wiring.
10. Add production test gates.
   - Route auth matrix, sync integration fixtures, graph/parser coverage, AI grounding, streaming contract, large-org performance.

## 20. GO / NO GO for Phase 2

Phase 1 audit is complete.

Production readiness: NO GO.

Phase 2 should begin only after approval, with the first implementation slice focused on route/auth contract tests and composition-root wiring fixes.

