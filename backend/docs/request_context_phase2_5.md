# Inspector AI Phase 2.5 RequestContext Validation

## Status

Phase 2.5 is a **backend verification phase**. It adds no new features and changes no production code. It proves that the Phase 2 `RequestContext` foundation is correct, deterministic, and production-ready before Phase 3 hardening begins.

**Result: PASS** — the verification suite is complete and green.

## 1. Scope

The Phase 2.5 verification suite (`backend/tests/unit/api/test_request_context_phase_2_5.py`) proves:

1. Singleton context per request (no duplicate construction)
2. JWT decoded exactly once per request
3. No duplicate organization/user lookups
4. RequestContext propagation through the entire AI execution path
5. Streaming uses the same canonical RequestContext
6. No random Org ID generation
7. **Route authentication matrix** (added in this phase — see §4)
8. Multi-tenant isolation

The suite also covers:

- RequestContext immutability and read-only permission maps
- ContextVar availability and tenant-context synchronization
- Factory method defaults (`anonymous`, `authenticated`)
- Authorization guards (`require_authenticated`, `require_organization`, `require_permission`)
- Middleware compatibility (public paths, missing auth header, OPTIONS preflight)

## 2. What Changed In This Phase

Phase 2.5 completes the verification suite with the missing **Task 7: Route authentication matrix** coverage. The Phase 2 docstring promised this verification but it was not implemented.

Files changed:

- `backend/tests/unit/api/test_request_context_phase_2_5.py`
  - Added `Task 11: Route Authentication Matrix` section:
    - `_classify_path` unit tests for the full route matrix (health, public, admin, streaming, authenticated families)
    - Middleware integration test asserting the route `auth_class` and auth state land on `request.state.request_context` per route family
    - Protected-route-without-token behavior (anonymous context keeps route class)
    - OPTIONS preflight bypass (no JWT decode)
  - Removed two genuinely unused imports (`F401`).
- `backend/docs/request_context_phase2_5.md` (this document)

No production code was modified.

## 3. Route Authentication Matrix (Verified)

The middleware classifies routes through `_classify_path` and stores the result on every `RequestContext` as `auth_class`. Verified expectations:

| Route family | Expected `auth_class` | Verified |
|---|---:|---|
| `/api/v1/health/*` | `HEALTH` | ✅ |
| `/api/v1/auth/login`, `/register`, `/refresh` | `PUBLIC` | ✅ |
| `/metrics`, `/docs`, `/redoc`, `/openapi.json`, `/version` | `PUBLIC` | ✅ |
| `/api/v1/admin/*` | `ADMIN` | ✅ |
| `/api/v1/ai/chat` | `STREAMING` | ✅ |
| `/api/v1/ai/*`, `/search/*`, `/documentation/*`, `/dependencies/*`, `/graph/*`, `/metadata/*`, `/salesforce/*`, `/sync/*`, `/security/*`, `/jobs/*`, `/observability/*` | `AUTHENTICATED` | ✅ |

Middleware behavior verified:

- Auth-exempt routes return before JWT processing (`decode_count == 0`).
- Protected routes with a token decode the JWT exactly once and build an authenticated context carrying the route class.
- Protected routes without a token leave an anonymous context that still carries the route class; enforcement is delegated to route dependencies (`require_authenticated`).
- OPTIONS preflight requests bypass auth even when a token header is present.

## 4. Test Results

```text
Agent.env/bin/python -m pytest tests/unit/api/test_request_context_phase_2_5.py -q
59 passed in 1.67s

Agent.env/bin/python -m pytest tests/unit/api tests/unit/ai \
  tests/audit/test_inspector_ai_grounding_contract.py -q
250 passed, 4 xfailed in 5.86s
```

The 4 xfails are the pre-existing expected-failure audit contract tests, unchanged.

Lint:

```text
Agent.env/bin/python -m ruff check tests/unit/api/test_request_context_phase_2_5.py
1 error: ARG005 (pre-existing, intentionally preserved)
```

The single remaining finding is `ARG005` on a mock `side_effect` lambda in the orchestrator propagation test. It is pre-existing and not safely fixable: `AsyncMock` invokes the lambda by keyword (`context_data=`), so renaming the parameter or collapsing it to `**kwargs` changes the mock call contract. It was left untouched per the smallest-correct-change rule.

## 5. Pre-Existing Failures (Not Caused By Phase 2.5)

The full unit suite reports failures in files outside this phase's scope. These were confirmed to exist on the committed `HEAD` baseline via a clean worktree checkout:

| Suite | Result on HEAD | Cause |
|---|---|---|
| `tests/unit/test_container.py` (2 tests) | Failed | `Container._register_security → _make_repos` requires a session factory; testing-mode startup does not create one |
| `tests/unit/test_metadata_sync.py` (13 errors) | Failed | Fixture/setup errors in the sync coordinator suite |
| `tests/unit/domain/repositories/test_metadata_repo.py` | Failed | Untracked in-progress metadata-repository work (separate effort, not committed) |

These are unrelated to `RequestContext` and are tracked by the metadata-repository in-progress work visible in `git status`.

## 6. Remaining Risks

Unchanged from Phase 2:

- Not every backend service constructor consumes `RequestContext` yet; legacy primitive parameters remain for backward compatibility.
- Full centralized RBAC is not finished; route-level permission checks remain inconsistent in some route families.
- CRUD/FLS fields on `RequestContext` are not yet populated from Salesforce permission metadata.
- Background jobs and websocket flows still need first-class `RequestContext` propagation.
- Session/refresh-token validation is still owned by existing auth flows.

## 7. Recommendation For Phase 3

Proceed to Phase 3 hardening after:

1. Protected routes are migrated from primitive user/org dependencies to `RequestContext`.
2. RBAC checks are centralized around `RequestContext.require_permission`.
3. Context is passed into graph, metadata, search, documentation, impact, websocket, and background-job services.
4. CRUD/FLS and Salesforce identity fields are populated deterministically.
5. The pre-existing `test_container.py` / `test_metadata_sync.py` failures and the in-progress metadata-repository work are resolved.
