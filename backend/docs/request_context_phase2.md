# Inspector AI Phase 2 Request Context Architecture

## Status

Phase 2 establishes the canonical request-context foundation. It does not add AI grounding, metadata intelligence, or new AI features.

Production readiness for Phase 3: **CONDITIONAL GO**

Reason: the HTTP authentication path, AI orchestration boundary, and tool execution boundary now have a canonical immutable `RequestContext`. Several older services still accept primitive `organization_id` and `user_id` parameters for backward compatibility, so full constructor-level service adoption should continue in Phase 3 hardening.

## 1. Architecture Changes Made

- Added one immutable `RequestContext` domain model.
- Added request authentication classification through `EndpointAuthClass`.
- Added one canonical context carrier in `shared.middleware.tenant_context`.
- Updated `AuthContextMiddleware` to build one `RequestContext` per HTTP request.
- Updated API dependencies so `get_current_user_id` and `get_current_org_id` derive from `get_request_context`.
- Added optional/authenticated request-context dependencies for routes that need explicit auth behavior.
- Added `RequestContext` to `AIRequest`.
- Updated `AIOrchestrator` to accept and propagate a `RequestContext`, while preserving old `organization_id` and `user_id` call signatures.
- Updated streaming tool execution to pass the same `RequestContext` object into `ToolRegistry`.
- Updated all registered AI tools to accept `request_context`.
- Removed random organization UUID generation from `engineering_tools.py`.
- Updated regression tests so random AI tool org IDs are now a failing condition.

## 2. RequestContext Class Design

Location: `backend/src/sfir_backend/domain/request_context.py`

`RequestContext` is a frozen dataclass with slots. It contains:

- Request: `request_id`, `trace_id`, `timestamp`
- Authentication: `user_id`, `organization_id`, `session_id`
- Salesforce: `instance_url`, `salesforce_org_id`, `salesforce_user_id`, `api_version`
- Identity: `username`, `email`, `profile`
- Authorization: `roles`, `permission_sets`, `permissions`, `crud_permissions`, `field_permissions`
- Current context: `current_object`, `current_record`, `current_page`, `selected_metadata`
- Execution: `request_source`, `client_version`, `extension_version`
- Observability: `correlation_id`, `span_id`
- Classification: `auth_class`, `membership_verified`

Collections are normalized in `__post_init__`:

- roles, permission sets, selected metadata, permissions become immutable tuples
- CRUD and field permissions become read-only mapping proxies

Validation helpers:

- `require_authenticated()`
- `require_organization()`
- `require_permission(permission)`

## 3. Authentication Flow Diagram

```text
Incoming HTTP request
  |
  v
AuthContextMiddleware
  |
  +--> public/health/options path?
  |      |
  |      v
  |   RequestContext.anonymous(...)
  |
  +--> Authorization: Bearer token?
         |
         v
      JWTService.decode_access_token(token)
         |
         v
      user_id/org_id/session extracted once
         |
         v
      optional user/member/role/permissions enrichment
         |
         v
      RequestContext(...)
         |
         v
      request.state.request_context
         |
         v
      set_request_context(context)
         |
         v
      FastAPI route dependency
```

Dependency flow:

```text
get_optional_request_context
  |
  +--> returns request.state.request_context if already built
  |
  +--> otherwise decodes Authorization once and stores context

get_request_context
  |
  v
context.require_authenticated()

get_current_user_id / get_current_org_id
  |
  v
derived from RequestContext for backward compatibility
```

## 4. Context Propagation Diagram

```text
Inspector AI route
  |
  v
get_request_context / get_optional_request_context
  |
  v
AIOrchestrator.chat / stream_chat(request_context=context)
  |
  v
AIRequest(request_context=context)
  |
  v
AIRequestCoordinator.process_request_stream
  |
  v
ToolRegistry.execute(request_context=context)
  |
  v
AgentTool.execute(request_context=context)
```

Legacy compatible path:

```text
Older caller passes organization_id + user_id only
  |
  v
AIOrchestrator creates RequestContext.authenticated(...)
  |
  v
AIRequest carries RequestContext
```

## 5. Route Authentication Matrix

Current explicit classification:

| Route family | Class | Notes |
|---|---:|---|
| `/api/v1/health/live` | Health/Public | Exempt from auth |
| `/api/v1/health/ready` | Health/Public | Exempt from auth |
| `/api/v1/health/status` | Health/Public | Exempt from auth |
| `/api/v1/auth/login` | Public | Exempt from auth |
| `/api/v1/auth/register` | Public | Exempt from auth |
| `/api/v1/auth/refresh` | Public | Exempt from auth |
| `/metrics` | Public/Internal | Exempt from auth by current middleware |
| `/docs`, `/redoc`, `/openapi.json` | Public | Disabled in production settings |
| `/api/v1/admin/*` | Admin | Still has placeholder admin enforcement from Phase 1 audit |
| `/api/v1/ai/chat` | Streaming | Authenticated via dependency, supports SSE when requested |
| `/api/v1/ai/*` | Authenticated | Some metadata endpoints still need full RBAC centralization |
| `/api/v1/search/*` | Authenticated | Existing RBAC permission checks retained |
| `/api/v1/documentation/*` | Authenticated | Existing RBAC checks retained where present |
| `/api/v1/dependencies/*` | Authenticated | Currently authenticates; permission enforcement remains partial |
| `/api/v1/graph/*` | Authenticated | Auth depends on legacy org helper now backed by RequestContext |
| `/api/v1/metadata/*` | Authenticated | Tenant filtering retained |
| `/api/v1/salesforce/*` | Authenticated | Existing service behavior retained |
| `/api/v1/sync/*` | Authenticated | Existing service behavior retained |
| `/api/v1/jobs/*` | Mixed | Some routes still expose job operations without user identity |
| `/api/v1/observability/*` | Mixed | Needs admin/internal policy in a later hardening pass |
| `/api/v1/security/*` | Authenticated | Existing security manager behavior retained |

## 6. Files Modified

Production code:

- `backend/src/sfir_backend/domain/request_context.py`
- `backend/src/sfir_backend/shared/middleware/tenant_context.py`
- `backend/src/sfir_backend/api/middleware.py`
- `backend/src/sfir_backend/api/deps.py`
- `backend/src/sfir_backend/domain/ai/models.py`
- `backend/src/sfir_backend/application/use_cases/ai/orchestrator.py`
- `backend/src/sfir_backend/application/use_cases/ai/coordinator.py`
- `backend/src/sfir_backend/application/use_cases/ai/tools.py`
- `backend/src/sfir_backend/application/use_cases/ai/engineering_tools.py`
- `backend/src/sfir_backend/application/use_cases/ai/agent.py`

Tests/docs:

- `backend/tests/unit/api/test_request_context.py`
- `backend/tests/audit/test_inspector_ai_grounding_contract.py`
- `backend/docs/request_context_phase2.md`

## 7. Tests Added

Added unit coverage for:

- RequestContext immutability and read-only permission maps
- JWT decoding once through the dependency context path
- API request to middleware-created RequestContext
- Context propagation into ToolRegistry and AgentTool execution

Updated audit regression:

- `test_engineering_tools_use_authenticated_org_context` now passes instead of being an expected failure.

## 8. Test Results

Passed:

```text
backend/Agent.env/bin/python -m py_compile <touched backend files>
backend/Agent.env/bin/python -m pytest backend/tests/unit/api/test_request_context.py -q
backend/Agent.env/bin/python -m py_compile all backend/src/sfir_backend Python files
backend/Agent.env/bin/python -m pytest backend/tests/unit/api/test_request_context.py backend/tests/audit/test_inspector_ai_grounding_contract.py backend/tests/unit/ai -q
```

Results:

```text
4 passed in backend/tests/unit/api/test_request_context.py
Full backend source compile passed
Static scan found no random org/user UUID creation in backend/src/sfir_backend/application/use_cases/ai
144 passed, 4 xfailed across request-context tests, audit contract tests, and AI unit tests
```

Lint:

```text
Core request-context files passed ruff.
AI propagation files still report pre-existing long-line/style findings in large AI modules.
```

Unable to complete:

```text
backend/Agent.env/bin/python -m pytest backend/tests/api/v1/test_ai_routes.py -q
```

The AI route test suite hung with no output in this environment, including a narrowed first-class run. It was interrupted and isolated separately from the successful context tests and compile checks.

## 9. Remaining Risks

- Not every backend service constructor consumes `RequestContext` yet. Phase 2 provides the canonical object and propagates it through the AI streaming/tool path, while preserving legacy primitive parameters.
- Full centralized RBAC is not finished. Existing route-level permission checks remain inconsistent in some route families.
- Admin, observability, jobs, graph, and dependency route policies still need explicit policy objects or decorators.
- Context enrichment currently uses available JWT claims and best-effort user/member/role lookups. Session and refresh-token validation are still owned by existing auth flows and not fully consolidated into the context builder.
- CRUD/FLS fields exist on `RequestContext`, but are not yet populated from Salesforce permission metadata.
- Background jobs and websocket flows still need first-class `RequestContext` propagation.
- The AI route test suite hang must be resolved before claiming complete end-to-end route regression coverage.

## 10. Recommendation For Phase 3

Proceed to Phase 3 only after:

1. The AI route test hang is resolved.
2. Protected routes are migrated from primitive user/org dependencies to `RequestContext`.
3. RBAC checks are centralized around `RequestContext.require_permission`.
4. Context is passed into graph, metadata, search, documentation, impact, websocket, and background-job services.
5. CRUD/FLS and Salesforce identity fields are populated deterministically.

Do not begin metadata intelligence or AI grounding work until those hardening steps are complete.
