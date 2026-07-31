# Inspector AI Grounding Audit

Audit date: 2026-07-30

Scope: verify whether Inspector AI can answer Salesforce engineering questions from real Salesforce metadata and deterministic backend reasoning, with the LLM limited to explaining backend facts.

## Overall Readiness

Overall Score: 38 / 100

Architecture: Partially present, not enterprise-ready. FastAPI routes, JWT auth, metadata sync, graph services, AI orchestration, tools, citations, confidence scoring, and streaming paths exist. The production chat path is still LLM-first, and critical grounding services are not wired into the AI context retriever.

Metadata Engine: Partial. Salesforce HTTP and sync primitives exist (`SalesforceClient`, `MetadataDownloadManager`, `SyncCoordinator`), but the graph parser registry used by `GraphService` registers only ApexClass, ApexTrigger, CustomObject, Layout, and ValidationRule. Required metadata coverage is far broader.

Dependency Engine: Partial. Graph service and extractors exist, but registered extractors cover Apex, Profile, Layout, and ValidationRule only. Flow, LWC, Aura, Visualforce, permission set group, report, dashboard, custom metadata, and many setup metadata dependencies are not covered in the graph path.

Impact Engine: Partial. Impact assessment tools exist, but AI tool implementations generate random organization IDs instead of accepting authenticated org context, so tool results are not proven isolated to the caller's org.

Permission Engine: Incomplete for Inspector AI. Backend auth requires a JWT Bearer token and tenant context is set from the JWT org claim, but AI engineering tools do not consistently consume that org context. Permission-specific metadata analysis is heuristic and not sufficient to answer profile/FLS questions reliably.

Streaming: Functional at the HTTP/SSE layer. Streaming emits token, tool, citation, confidence, next_actions, and done events. However, streaming depends on the LLM deciding whether to call tools, and tool citations are not built from executed backend facts.

Performance: Not production-proven. There are HTTP client retries, circuit breaker behavior, cache services, and observability primitives, but no large-org benchmark evidence for the requested metadata breadth, graph size, streaming latency, or Salesforce API limits.

Security: Mixed. API auth is now consistently Bearer JWT between frontend and backend. Prompt injection and safety filters exist. However, org isolation is broken in AI tool implementations that create random UUIDs, and route-level RBAC/permission checks for AI metadata questions are not proven.

Testing: Improved for audit evidence. Added `backend/tests/audit/test_inspector_ai_grounding_contract.py`. Result: `4 passed, 5 xfailed`. Passing tests verify route/auth/header facts and current parser coverage. Expected failures capture missing enterprise grounding requirements.

Production Readiness: NO GO.

## Working

- Backend exposes `GET /api/v1/health/live` and `POST /api/v1/ai/chat`; `/api/v1/health` is not registered. Evidence: audit test `test_ai_route_and_health_route_contract_is_registered`.
- Backend auth expects `Authorization: Bearer <jwt>`, not `X-API-Key`. Evidence: `api/deps.py` requires an authorization header and Bearer scheme, and `api/middleware.py` reads Bearer tokens into tenant context.
- Frontend AI client now sends Bearer auth only through `addon/services/aiApiClient.js`, `addon/backend_service.js`, and `addon/components/InspectorAiBackendConfig.js`. Evidence: audit test `test_frontend_ai_clients_send_bearer_token_only`.
- Salesforce API client primitives are real. `SalesforceClient` sends Salesforce Bearer tokens and supports REST, SOQL query paging, Tooling paths, and metadata paths.
- Metadata downloader has real SOQL/Describe/Tooling calls for objects, fields, Apex classes/triggers, flows, profiles, permission sets, validation rules, layouts, record types, reports, dashboards, email templates, roles, queues, and sharing rules.
- Streaming endpoint returns Server-Sent Events through `StreamingResponse` and delegates to `AIOrchestrator.stream_chat`.

## Broken

- The AI context retriever is instantiated but not wired to metadata, search, dependency graph, impact, or documentation retrievers. `ContextRetriever` returns "Metadata context unavailable.", "Search unavailable.", and "Dependency graph unavailable." when no retrievers are registered.
- Non-streaming `POST /api/v1/ai/chat` retrieves whatever context is available, builds a prompt, and calls `provider.chat` directly. It does not enforce deterministic backend tool execution before the LLM answer.
- Streaming chat can pass tool definitions to the provider, but the LLM decides whether to call them. That violates the requirement that backend performs all engineering reasoning and LLM only explains results.
- Engineering tools in `engineering_tools.py` call `uuid.uuid4()` inside `execute()` and use that random value as `org_id`. This breaks authenticated-org grounding and org isolation for field impact, dependency analysis, impact assessment, and metadata analysis.
- Agent tools in `agent.py` require an in-memory graph to be set. If no graph is attached, they return "Graph not available. Build the graph first."
- `/api/v1/ai/query` has suspicious dependencies using `Depends(lambda c: c.get_use_case(...))`, where `c` is not provided by FastAPI dependency injection. The main chat route does not use this route, but it is not a reliable production path.
- Citations are extracted from LLM text or existing context citations, not from executed backend tool results. When context citations are empty, citation validation cannot prove claims.

## Missing

- Full metadata parser coverage for the requested Salesforce surface:
  - Missing from the registered graph parser path: CustomField, Flow, PermissionSet, PermissionSetGroup, Profile, Role, RecordType, CompactLayout, FlexiPage, Report, Dashboard, FormulaField, CustomMetadata, CustomSetting, NamedCredential, ConnectedApp, RemoteSiteSetting, EmailTemplate, ApprovalProcess, AssignmentRules, EscalationRules, SharingRule, Queue, Group, PlatformEvent, LightningComponentBundle, AuraDefinitionBundle, ApexPage, StaticResource.
- Deterministic question router for the 15 requested engineering questions.
- Backend-owned answer composition that refuses unsupported questions or low-confidence answers.
- Tool results with structured facts, citations, confidence, and org/user provenance.
- Required end-to-end tests against real or contract-recorded Salesforce metadata fixtures.
- Permission-aware filtering for metadata answers based on the Salesforce user and org authorization model.
- Large-org performance tests for sync, parsing, graph construction, search, impact analysis, and streaming.

## Fake

- No production code path was found that uses explicit fake JSON as Salesforce metadata for the sync pipeline.
- The risky "fake" behavior is not fake data; it is fake grounding:
  - AI tools can run with random org IDs instead of the authenticated org.
  - If the graph is not built or context retrievers are not registered, the LLM can still answer from general knowledge.
  - Basic code/security review tools use heuristics on provided snippets and can sound authoritative without org metadata.
  - The Noop provider can return "LLM not configured", which is honest, but it does not validate Salesforce question answering.

## Risk (High/Medium/Low)

High:

- Hallucinated Salesforce engineering answers. The LLM can answer even when metadata/search/graph context is unavailable.
- Cross-org correctness and isolation. Random org IDs in tools mean results cannot be trusted for the authenticated user.
- Delete/deployment recommendations. Safe delete and deployment impact cannot be trusted until graph coverage and org context are fixed.
- Permission/FLS answers. Permission set/profile/FLS analysis is incomplete and not proven against real Salesforce metadata.

Medium:

- Streaming reliability. SSE works, but tool execution and citation semantics are not strong enough for enterprise trust.
- Metadata sync breadth. Downloader has useful coverage, but parser/graph coverage is much narrower than downloader coverage.
- Dependency graph completeness. Current extractors do not cover many metadata types that often carry references.

Low:

- Basic route/auth reachability. Health and chat routes are registered, and auth scheme is now consistent.
- Salesforce HTTP plumbing. The base client and downloader are structurally real, though not sufficient alone for AI readiness.

## Required Fixes

1. Wire `ContextRetriever` in `Container._make_ai_orchestrator()` to real metadata search, dependency graph, impact, and documentation services.
2. Pass authenticated `organization_id` and `user_id` into every engineering tool execution. Remove all `org_id = uuid.uuid4()` usage in AI tools.
3. Make backend deterministic for engineering questions:
   - Classify the user question.
   - Execute required metadata/dependency/impact/permission tools first.
   - Compose a structured fact bundle.
   - Let the LLM explain only that fact bundle.
4. Expand parser and extractor registration to cover the requested Salesforce metadata surface.
5. Generate citations from backend fact rows, graph nodes, metadata version IDs, and Salesforce component identifiers.
6. Add confidence scoring based on coverage, freshness, parser success, graph completeness, and citation density.
7. Add refusal behavior for unsupported metadata types, stale sync, missing permissions, or low-confidence impact analysis.
8. Fix or remove `/api/v1/ai/query` dependency injection path.
9. Build a representative Salesforce metadata fixture set for all 15 audit questions.
10. Add integration/e2e/performance/security tests that prove answers are based on backend facts, not LLM memory.

## GO / NO GO

NO GO.

Inspector AI is not production-ready as an enterprise Salesforce engineering copilot. It has a credible foundation, and the networking/auth/streaming path is substantially closer now, but it cannot yet prove answers for the 15 target questions from real Salesforce metadata with backend-owned reasoning.

Question readiness snapshot:

| Question | Status | Reason |
| --- | --- | --- |
| Where is Account.Name used? | NO GO | Field dependency path exists, but org context and graph/parser coverage are not reliable. |
| Find every Flow using Opportunity. | NO GO | Flow downloader exists, but Flow parser/extractor is not registered in the graph path. |
| Can I safely delete Custom_Field__c? | NO GO | Impact tools use random org IDs and graph coverage is incomplete. |
| Which Apex classes call MyTrigger? | PARTIAL | Apex parser/extractor exists, but deterministic chat execution is not enforced. |
| Deployment impact of validation rule | PARTIAL | Validation parser/extractor exists, but impact depends on incomplete graph and random org IDs in AI tools. |
| Permission sets reference object | NO GO | PermissionSet downloader exists, but graph parser/extractor coverage is missing. |
| Profiles edit field | NO GO | Profile extractor exists, but profile parser is not registered in graph path and permission semantics are incomplete. |
| Unused Apex classes | PARTIAL | Apex graph primitives exist, but no proven whole-org unused-component analysis in chat. |
| Orphaned flows | NO GO | Flow graph coverage missing. |
| Duplicate validation rules | PARTIAL | Validation rules are parsed, but duplicate detection is not proven in AI route. |
| Explain object Account | PARTIAL | Object parser exists, but context retriever is not wired. |
| Generate documentation for Opportunity | PARTIAL | Documentation generator exists, but backend fact grounding is not guaranteed. |
| Dependency graph for custom object | PARTIAL | CustomObject parser exists, but dependency extraction coverage is limited. |
| References to custom metadata | NO GO | CustomMetadata is not registered in graph parser path. |
| SOQL for Accounts with Opportunities | PARTIAL | The LLM can generate SOQL, but there is no enforced schema-grounded generator/validator. |

Audit test evidence:

```text
$ ./Agent.env/bin/python -m pytest tests/audit -q
....xxxxx                                                                [100%]
4 passed, 5 xfailed in 3.28s
```

