# Phase 22 — Final System Audit, Documentation & Developer Guide

**Status:** Complete  
**Date:** 2026-07-16  
**Scope:** Full engineering audit of the entire SFIR Backend platform  
**Rule:** No new features, no business logic changes, no architecture rewrites — only review, validate, document, and generate operational guides.

---

## Table of Contents

1. [Part 1 — Complete Architecture Review](#part-1--complete-architecture-review)
2. [Part 2 — Code Quality Review](#part-2--code-quality-review)
3. [Part 3 — Security Review](#part-3--security-review)
4. [Part 4 — Performance Review](#part-4--performance-review)
5. [Part 5 — Test Review](#part-5--test-review)
6. [Part 6 — Documentation](#part-6--documentation)
7. [Part 7 — Complete Developer Guide](#part-7--complete-developer-guide)
8. [Part 8 — How to Run the Application](#part-8--how-to-run-the-application)
9. [Part 9 — Production Deployment Guide](#part-9--production-deployment-guide)
10. [Part 10 — Final Report](#part-10--final-report)

---

## Part 1 — Complete Architecture Review

### Architecture Overview

The SFIR Backend follows **Hexagonal Architecture (Ports & Adapters)** organized into four layers:

| Layer | Location | Contents |
|---|---|---|
| **Domain** | `src/sfir_backend/domain/` | Entities, Value Objects, Repository interfaces, Domain Events, Domain models for all subdomains (AI, cache, canonical, documentation, graph, impact, jobs, metadata, observability, search, security) |
| **Application** | `src/sfir_backend/application/` | Use Cases, DTOs, Cache services |
| **Infrastructure** | `src/sfir_backend/infrastructure/` | Adapters (database, cache, parsers, search, graph, impact, jobs, LLM, observability, security, salesforce) |
| **API** | `src/sfir_backend/api/` | FastAPI routes, middleware, dependencies, DTOs, WebSocket |

**Total source files:** ~75 domain files, ~20 application files, ~150+ infrastructure files, ~20 API files = **~265 Python files**  
**Estimated source lines of code:** ~18,000-22,000 in `src/`

### Hexagonal Architecture Assessment

| Criterion | Score | Notes |
|-----------|-------|-------|
| Dependency direction | ✅ | Domain has zero imports from infrastructure or API |
| Port definition | ✅ | Clear abstract interfaces in `domain/repositories/` and `ports/services/` |
| Adapter isolation | ✅ | Infrastructure implementations implement domain interfaces |
| Layer strictness | ✅ | No infra imports from API, no API imports from domain |

### Layer Violations Found

| # | Violation | Severity | Details |
|---|-----------|----------|---------|
| 1 | `application/use_cases/metadata_sync.py` imports infrastructure | **Medium** | Imports `Downloader`, `ManifestGenerator`, `ChangeDetector`, `HashCalculator`, `RetryManager`, `RecoveryManager` directly from `infrastructure/salesforce/sync/` and `infrastructure/jobs/` |
| 2 | `application/use_cases/organization.py` includes orchestration logic | **Low** | Mixes use-case orchestration with entity creation; could delegate to domain services |
| 3 | `application/use_cases/ai/agent.py` imports infrastructure directly | **Medium** | References `GraphService` which is in infrastructure layer |
| 4 | `api/deps.py` is 118 lines of dependency injection wire-up | **Low** | Should be thin; much of the container's work is duplicated here |

### Circular Dependencies

No circular dependencies detected. The dependency graph is acyclic: Domain → Application → Infrastructure → API.

### Duplicate Logic

| # | Description | Location |
|---|-------------|----------|
| 1 | Token generation appears in both `JWTService` and `PasswordService` | `infrastructure/security/jwt.py` and `infrastructure/security/password.py` |
| 2 | Email validation regex appears in both `Email` value object and can be duplicated elsewhere | `domain/value_objects/email.py` |
| 3 | Organization ID filtering appears in every repository method | All repository files |

### Dead Code

| # | Description | Location |
|---|-------------|----------|
| 1 | `infrastructure/event_bus/` has only `__init__.py` — unused stub | `infrastructure/event_bus/` |
| 2 | `infrastructure/queue/` has only `__init__.py` — unused stub | `infrastructure/queue/` |
| 3 | `domain/policies/` has only `__init__.py` | `domain/policies/` |
| 4 | Several `services/` directories: `services/ai/`, `services/audit/`, `services/auth/`, `services/graph/`, `services/metadata/` — all contain only empty `__init__.py` | `services/*/` |
| 5 | `scripts/` directory contains only `__init__.py` | `scripts/` |
| 6 | No migration files exist — `alembic/versions/` has only `__init__.py` | `alembic/versions/` |
| 7 | Pytest markers `unit`, `integration`, `api`, `security`, `slow` are declared but never used | `pyproject.toml` |
| 8 | `tests/unit/application/`, `tests/unit/domain/entities/`, `tests/unit/domain/services/`, `tests/unit/domain/value_objects/` — empty `__init__.py` only | `tests/unit/` |

### Over-Engineering Assessment

| Area | Assessment |
|------|------------|
| Cache layer (11 cache services, `CacheCoordinator`, `CacheHealthMonitor`, `CacheInvalidationManager`, etc.) | **Adequate** for enterprise multi-tenant app, but could be simplified for early-stage |
| Security layer (13 files: abuse detection, audit engine, encryption, JWT, password, rate limiter, secrets manager, security manager, etc.) | **Appropriate** for production security posture |
| AI layer (8 provider implementations, prompt templates, conversation memory, context retrieval, citation generation, response validation, safety filter) | **Appropriate** for the flexibility required |
| Impact analysis (12 files: blast radius, change, delete, deployment, rename, risk, simulation) | **Slightly over-engineered** for current usage — `rename.py` and `simulation.py` are detailed but there is no API route that exercises all features |
| Job engine (15 files: dead letter, dispatcher, heartbeat, lock, pool, prioritizer, progress, queue, recovery, retry, scheduler) | **Appropriate** for async job system reliability |

### Under-Engineering Assessment

| Area | Assessment |
|------|------------|
| Database indexes — no composite indexes defined | **Under-engineered** for query performance at scale |
| No migration history | **Critical gap** — no way to track or roll back schema changes |
| Repository N+1 queries — no eager loading | **Significant gap** for production performance |
| No integration tests | **Major gap** — no real DB/Redis test coverage |
| No CI/CD for backend | **Critical gap** — no automated build/test/deploy pipeline |

### Module Boundary Analysis

```
┌─────────────────────────────────────────────┐
│                   API Layer                  │
│  routes/  middleware/  deps.py  websocket.py │
├─────────────────────────────────────────────┤
│               Application Layer              │
│  use_cases/  dto/  cache/                    │
├─────────────────────────────────────────────┤
│             Infrastructure Layer             │
│  database/  cache/  security/  salesforce/   │
│  parsers/  graph/  impact/  search/  jobs/   │
│  llm/  observability/  documentation/        │
├─────────────────────────────────────────────┤
│                Domain Layer                  │
│  entities/  value_objects/  repositories/    │
│  events/  models/  ports/  canonical/        │
└─────────────────────────────────────────────┘
```

### Architecture Recommendations

1. **Move infrastructure imports out of application layer** — Refactor `metadata_sync.py` to accept infrastructure dependencies via the DI container's interface abstractions rather than direct imports
2. **Remove dead code stubs** — Delete empty `services/*/`, `scripts/`, `event_bus/`, `queue/`, `policies/` directories
3. **Generate initial Alembic migration** — Create the baseline migration from current model definitions
4. **Add composite indexes** to improve query performance for common multi-column WHERE clauses
5. **Add eager loading** to all repository methods that return related entities

---

## Part 2 — Code Quality Review

### Folder Structure

```
src/sfir_backend/
├── __init__.py
├── main.py                              # Application factory (136 lines)
├── config/
│   ├── settings.py                      # Pydantic Settings (182 lines)
│   └── container.py                     # DI Container (620 lines)
├── api/
│   ├── deps.py                          # FastAPI dependencies (118 lines)
│   ├── errors.py                        # Error handlers
│   ├── middleware.py                     # General middleware
│   ├── schemas.py                       # Pydantic schemas
│   ├── security_middleware.py           # Security middleware
│   ├── websocket.py                     # WebSocket manager (171 lines)
│   ├── dto/                             # API DTOs (admin, ai, documentation, impact, search)
│   └── v1/routes/                       # 16 route files ~ 62 endpoints
├── application/
│   ├── cache/services.py                # 11 cache service classes
│   ├── dto/                             # 7 application DTOs
│   └── use_cases/                       # 8 use case groups
│       ├── auth.py
│       ├── metadata_sync.py             # 873 lines — largest file
│       ├── organization.py
│       ├── rbac.py
│       ├── salesforce.py
│       └── ai/                          # 5 files
├── domain/                              # 75 files across 19 sub-packages
├── infrastructure/                      # 150+ files across 18 sub-packages
├── workers/                             # Celery app, scheduler, tasks
├── shared/                              # Exceptions, middleware, utils
└── ports/                               # Abstract port interfaces
```

### Naming Conventions

| Convention | Consistency | Notes |
|------------|-------------|-------|
| Snake case for files/functions | ✅ Consistent | `metadata_sync.py`, `get_user_by_email()` |
| Pascal case for classes | ✅ Consistent | `AuthUseCase`, `AIOrchestrator` |
| Uppercase for enums | ✅ Consistent | `AIFeature`, `AIProviderType` |
| I-prefix for interfaces | ✅ Consistent | `IUserRepository`, `IAuditLogRepository` |
| Python module style | ✅ Consistent | No camelCase in file names |

### SOLID Principles

| Principle | Grade | Notes |
|-----------|-------|-------|
| **S**ingle Responsibility | **B+** | Most classes have single responsibility. `SecurityManager` and `Container` could be split |
| **O**pen/Closed | **A** | New LLM providers, parsers, caches can be added without modifying existing code |
| **L**iskov Substitution | **A** | All repository implementations correctly implement interfaces |
| **I**nterface Segregation | **A** | Repository interfaces are small and focused |
| **D**ependency Inversion | **B** | Application layer imports infrastructure directly in 2 cases (violation) |

### Dependency Injection

**Approach:** Manual DI container in `config/container.py` (620 lines). No DI framework used.

Strengths:
- Full control over object lifecycle
- Lazy initialization of use cases
- Clean interface for testing (mocks can be injected)

Weaknesses:
- 620 lines of manual wiring is error-prone
- No compile-time validation of dependency graph
- `api/deps.py` duplicates some container logic
- Adding a new dependency requires modifying the container in 3+ places

### Error Handling

| Aspect | Grade | Details |
|--------|-------|---------|
| Exception hierarchy | **A** | Custom exceptions in `shared/exceptions/` (ApplicationError, DomainError, InfrastructureError) |
| HTTP error mapping | **A** | RFC 7807 ProblemResponse for all API errors |
| Try/catch granularity | **B** | Some use cases catch broadly (`except Exception`) |
| Error logging | **A** | All errors logged with structlog with correlation IDs |
| Retry logic | **A** | Smart retry with exponential backoff in sync operations |

### Logging

| Aspect | Detail |
|--------|--------|
| Library | structlog (structured JSON logging) |
| Format | JSON in production, console in development |
| Sensitive data masking | Keys containing `password`, `secret`, `token`, `api_key`, `authorization`, `jwt` are masked |
| Correlation IDs | Present in all log entries |
| Levels | DEBUG, INFO, WARNING, ERROR, CRITICAL (configurable) |

### Configuration

| Aspect | Detail |
|--------|--------|
| Library | Pydantic Settings v2 |
| Env prefix | `SFIR_` |
| .env file | Read automatically by Pydantic |
| Secret handling | `SecretStr` for sensitive values |
| Validation | Field validators for `environment`, `jwt_algorithm`, `log_level` |
| Caching | `@lru_cache` on `get_settings()` |

### Code Quality Recommendations

1. **Split `metadata_sync.py`** — 873 lines is too large. Extract sync strategies into separate files
2. **Split `container.py`** — 620 lines is too large. Break into `container_database.py`, `container_security.py`, `container_ai.py`
3. **Add pre-commit hooks** — Currently configured but not enforced
4. **Add `.dockerignore`** — Prevent build context bloat
5. **Remove dead code** — Clean up empty `services/*/`, `scripts/`, `event_bus/`, `queue/`, `policies/` directories
6. **Fix layer violations** — Remove infrastructure imports from application layer

---

## Part 3 — Security Review

### Authentication

| Aspect | Detail |
|--------|--------|
| Registration | Email + password with bcrypt (12 rounds) hashing |
| Login | Email/password verification with account lockout after 5 failures (15 min) |
| Token type | JWT (HS256) with 30 min access token expiry |
| Refresh tokens | SHA-256 hashed in DB, 7 day expiry, rotation on refresh |
| Session management | Max 10 sessions per user, tracked in `sessions` table |
| Audit events | `user.login`, `user.login.failed`, `user.registered`, `user.locked`, `token.refreshed`, `token.revoked` |

### Authorization

| Aspect | Detail |
|--------|--------|
| RBAC model | Hierarchical roles: owner(100) > admin(80) > developer(60) > viewer(40) > readonly(20) |
| Permission evaluation | `AuthorizationEngine.require_permission()` checks role hierarchy |
| Tenant isolation | `validate_tenant_access()` + `require_tenant_access()` + JWT `org` claim |
| Resource ownership | Cross-tenant access blocked; resource owner check for sensitive operations |

### Encryption

| Aspect | Detail |
|--------|--------|
| Algorithm | AES-256-GCM with envelope encryption |
| Key derivation | PBKDF2-HMAC-SHA256 (100,000 iterations — SHOULD BE 600,000 in production) |
| Key rotation | Manual via `rotate_key()` method |
| AAD | Optional context binding via Additional Authenticated Data |

### Security Gaps Found

| # | Gap | Severity | Recommendation |
|---|-----|----------|----------------|
| 1 | **CORS wildcard `chrome-extension://*`** | **High** | Lock to specific extension IDs |
| 2 | **No backend CI/CD pipeline** | **High** | Create CI pipeline for lint, test, security scan |
| 3 | **No migration files** | **High** | Generate initial Alembic migration |
| 4 | **PBKDF2 static salt** | **Medium** | Use per-key random salt |
| 5 | **`_is_production` hardcoded False** | **Medium** | Fix to use actual environment detection |
| 6 | **Password strength not validated** | **Medium** | Add min length, complexity requirements to `RegisterRequest` |
| 7 | **SafetyFilter is purely regex-based** | **Medium** | Add ML-based content moderation for production |
| 8 | **WebSocket auth via query parameter** | **Medium** | Use `Sec-WebSocket-Protocol` header instead |
| 9 | **No database-level RLS** | **Low-Medium** | Consider PostgreSQL Row-Level Security for defense-in-depth |
| 10 | **SOQL escaping is minimal** | **Medium** | Use parameterized SOQL queries |
| 11 | **No brute-force protection on `/auth/refresh`** | **Low** | Add rate limiting to refresh endpoint |
| 12 | **No alerting rules in Prometheus** | **Medium** | Add alert rules for security events |

### Rate Limiting

| Rule | Limit | Window | Scope |
|------|-------|--------|-------|
| Default | 1000 requests | 60 seconds | All endpoints |
| AI | 100 requests | 60 seconds | `/api/v1/ai/*` |
| Deployment | 50 requests | 60 seconds | Deployment operations |

### Security Headers

| Header | Value |
|--------|-------|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `X-XSS-Protection` | `1; mode=block` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` |
| `Content-Security-Policy` | `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'` |

### Security Recommendations

1. Lock CORS origins to specific Chrome extension IDs
2. Add password strength validation to registration endpoint
3. Fix PBKDF2 iteration count for production environments
4. Add per-key random salt for encryption key derivation
5. Move WebSocket auth from query parameter to `Sec-WebSocket-Protocol` header
6. Add Prometheus alerting rules for security events
7. Generate initial database migration

---

## Part 4 — Performance Review

### API Performance

| Metric | Detail |
|--------|--------|
| Framework | FastAPI + uvicorn with uvloop + httptools |
| Workers | 4 (configurable) |
| Connection pooling | DB: pool=10, overflow=20, pool_pre_ping=True, pool_recycle=3600s |
| Redis pooling | max_connections=50, retry_on_timeout=True, health_check_interval=30 |
| Async | All I/O paths are async (FastAPI, SQLAlchemy async, Redis async, httpx) |

### Database Performance

| Aspect | Grade | Issues |
|--------|-------|--------|
| Indexes | **C** | 33 single-column indexes defined, but no composite indexes, no migration files |
| N+1 prevention | **D** | No `selectinload`/`joinedload` used anywhere in repository code |
| Bulk operations | **D** | `save_many()` does N individual flushes; no bulk inserts |
| Pagination | **C** | OFFSET-based only — no keyset pagination; some unbounded queries |
| Connection pooling | **A** | Good pool sizing with pre-ping and recycle |

### Redis Performance

| Aspect | Detail |
|--------|--------|
| Pool size | 50 connections (hardcoded in `connection_pool.py`) |
| Eviction | LRU (maxmemory 2GB in k8s config) |
| Persistence | AOF |
| Health check | PING every 30 seconds |
| Key design | `{org_id}:{prefix}:{key}` for tenant isolation |

### Performance Bottlenecks

| # | Bottleneck | Impact | Recommendation |
|---|------------|--------|----------------|
| 1 | **No eager loading in repositories** | N+1 queries on every list endpoint | Add `selectinload()` to all repository list methods |
| 2 | **`save_many()` does N flushes** | Slow bulk inserts | Use `session.add_all()` + single flush |
| 3 | **OFFSET-based pagination** | O(n) performance for deep pages | Implement keyset pagination |
| 4 | **Unbounded list returns** | Memory pressure | Add pagination to all list methods |
| 5 | **No composite indexes** | Full table scans for multi-column filters | Add composite indexes for common query patterns |
| 6 | **`next_retry_at` comparison not sargable** | Index can't be used | Rewrite query to avoid wrapping column in function |
| 7 | **No query timeout/statement timeout** | Long-running queries block connections | Set `statement_timeout` on engine and query-level timeouts |
| 8 | **No read replicas** | All traffic hits primary | Add read replica configuration |
| 9 | **No PgBouncer** | Connection overhead per worker | Add PgBouncer for connection pooling |
| 10 | **No prepared statement caching** | Repeated query planning | Tune asyncpg prepared statement cache |

### Performance Recommendations

1. Add `selectinload`/`joinedload` to all repository methods that return related entities
2. Implement `session.add_all()` + single flush in `save_many()`
3. Add keyset (cursor-based) pagination for high-volume list endpoints
4. Add composite indexes for `(organization_id, status)`, `(sync_job_id, status)`, `(organization_id, component_type)` 
5. Add `statement_timeout` configuration
6. Add PgBouncer for connection pooling
7. Add read replica configuration for production
8. Move Redis pool config into settings (not hardcoded)

---

## Part 5 — Test Review

### Test Inventory

| Category | Count | Details |
|----------|-------|---------|
| Unit tests | ~1,336 | All in `tests/unit/` |
| Integration tests | **0** | Empty `__init__.py` files only |
| Load tests | 4 Locust user classes | `tests/load/test_api.py` |
| Chaos tests | 8 test cases | `tests/chaos/test_failures.py` |
| Security tests | ~100 | `tests/unit/security/` |
| AI tests | ~134 | `tests/unit/ai/` |
| API tests | ~46 | `tests/unit/api/` |
| **Total** | **~1,336 passing** | All pass in ~27 seconds |

### Test Coverage by Module

| Module | Tests | Coverage Quality |
|--------|-------|-----------------|
| Domain models | ~214 | Good — all model files have corresponding tests |
| Cache | ~78 | Good |
| Graph | ~46 | Good |
| Documentation | ~77 | Good |
| Search | ~66 | Good |
| Jobs | ~125 | Good |
| Impact | ~52 | Good |
| Observability | ~65 | Good |
| Parsers | ~73 | Good |
| Security | ~100 | Good |
| AI | ~134 | Good |
| Auth | ~15 | Adequate |
| Salesforce | ~51 | Good |
| Metadata sync | ~65 | Adequate |

### Test Quality Assessment

| Criterion | Grade | Notes |
|-----------|-------|-------|
| Async test usage | **A** | Heavily uses `@pytest.mark.asyncio` |
| Fixtures | **A** | 32 fixtures, well-scoped |
| Parametrization | **A** | Used for model validation tests |
| Mocking | **B** | Adequate mocking of external services |
| Edge cases | **B** | Covers happy paths and error cases, but could use more boundary tests |
| Isolation | **A** | Tests are independent |
| Speed | **A** | Full suite runs in < 30 seconds |

### Missing Tests

| Gap | Impact |
|-----|--------|
| **Zero integration tests** | No validation of database interactions, Redis cache behavior, or real async workflows |
| **Zero API endpoint tests** | No request/response validation for any of the 62+ endpoints |
| **Zero E2E flow tests** | No end-to-end workflows (register → connect Salesforce → sync → graph → impact) |
| **No migration tests** | No validation of Alembic migration scripts (which don't exist yet) |
| **No performance benchmark suite** | No regression benchmarks for API latency |
| **Chaos tests skip by default** | All chaos tests have `@pytest.mark.skipif("not service_running()")` |

### Test Recommendations

1. **Write integration tests** — Start with repository-level tests against a test PostgreSQL/Redis
2. **Write API endpoint tests** — Use FastAPI `TestClient` for all 62 endpoints
3. **Remove empty test directories** — Clean up `tests/unit/domain/entities/`, `tests/e2e/workflows/`, etc.
4. **Add performance benchmarks** — Use `pytest-benchmark` for critical code paths
5. **Add migration tests** — Once migrations exist, test `upgrade` + `downgrade`

---

## Part 6 — Documentation

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Chrome Extension                             │
│                    (Salesforce Inspector UI)                         │
└─────────────────────────┬───────────────────────────────────────────┘
                          │ HTTPS / WSS
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      FastAPI API Server                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────────────┐ │
│  │ Auth     │  │ Org      │  │ SF       │  │ AI                  │ │
│  │ Routes   │  │ Routes   │  │ Routes   │  │ Routes              │ │
│  ├──────────┤  ├──────────┤  ├──────────┤  ├─────────────────────┤ │
│  │ Use Case │◄─┤ Use Case │◄─┤ Use Case │◄─┤ Use Case            │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬──────────────┘ │
│       │              │              │               │               │
│       ▼              ▼              ▼               ▼               │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                     Domain Layer                                 ││
│  │  Entities / Value Objects / Ports / Events / Canonical Models   ││
│  └─────────────────────────────────────────────────────────────────┘│
│       ▲              ▲              ▲               ▲               │
│       │              │              │               │               │
│  ┌────┴──────┐ ┌────┴──────┐ ┌────┴──────┐  ┌───────┴───────────┐  │
│  │ Security  │ │ Metadata  │ │ Graph/    │  │ AI/LLM           │  │
│  │ Auth/JWT  │ │ Sync      │ │ Impact    │  │ 7 Providers      │  │
│  │ RBAC      │ │ Parsers   │ │ Search    │  │ SafetyFilter     │  │
│  │ Encryption│ │ Salesforce│ │ Doc Gen   │  │ CitationGen      │  │
│  └───────────┘ └───────────┘ └───────────┘  └──────────────────┘  │
└─────────────────────────┬───────────────────────────────────────────┘
                          │ Redis
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        PostgreSQL 16                                 │
│           ┌─────────────────────────────────────┐                   │
│           │ audit_logs │ backup│ graph│ metadata│                   │
│           │ sessions │ users │ jobs │ cache     │                   │
│           └─────────────────────────────────────┘                   │
└─────────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Celery Workers                                │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐               │
│  │ default  │ │ metadata │ │ graph    │ │ ai       │               │
│  │ queue    │ │ queue    │ │ queue    │ │ queue    │               │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘               │
└─────────────────────────────────────────────────────────────────────┘
```

### Folder Structure (Complete)

```
src/sfir_backend/
├── main.py                                 Application factory
├── config/
│   ├── settings.py                         Pydantic Settings (182 lines)
│   └── container.py                        DI Container (620 lines)
├── api/
│   ├── deps.py                             FastAPI dependencies
│   ├── errors.py                           Error handlers (RFC 7807)
│   ├── middleware.py                        General middleware
│   ├── schemas.py                          Pydantic schemas
│   ├── security_middleware.py              Security headers + rate limiting
│   ├── websocket.py                        WebSocket manager
│   ├── dependencies/__init__.py
│   ├── dto/
│   │   ├── admin.py
│   │   ├── ai.py
│   │   ├── documentation.py
│   │   ├── impact.py
│   │   └── search.py
│   └── v1/routes/
│       ├── __init__.py                     Aggregates all routers
│       ├── admin.py                        Admin endpoints
│       ├── ai.py                           AI endpoints (8)
│       ├── auth.py                         Auth endpoints (5)
│       ├── dependencies.py                 Dependency graph endpoints (5)
│       ├── documentation.py                Documentation endpoints (4)
│       ├── graph.py                        Graph endpoints (6)
│       ├── health.py                       Health endpoints (3)
│       ├── impact.py                       Impact analysis endpoints (4)
│       ├── jobs.py                         Job management endpoints (7)
│       ├── metadata_sync.py                Sync endpoints (9)
│       ├── observability.py                Observability endpoints (1)
│       ├── organizations.py                Organization endpoints (4)
│       ├── salesforce.py                   Salesforce endpoints (5)
│       ├── search.py                       Search endpoints (4)
│       └── security.py                     Security endpoints (4)
├── application/
│   ├── cache/services.py                   11 cache service classes
│   ├── dto/                                7 DTO files
│   └── use_cases/
│       ├── auth.py                         AuthUseCase
│       ├── metadata_sync.py                SyncCoordinator (873 lines)
│       ├── organization.py                 OrganizationUseCase
│       ├── rbac.py                         RBACUseCase
│       ├── salesforce.py                   SalesforceUseCase
│       └── ai/
│           ├── agent.py                    AgentService
│           ├── conversation_manager.py     ConversationManager
│           ├── coordinator.py              AIRequestCoordinator
│           ├── orchestrator.py             AIOrchestrator
│           ├── prompt_builder.py           PromptBuilder
│           └── tools.py                    ToolRegistry
├── domain/
│   ├── ai/                                 AI domain models + enums
│   ├── cache/                              Cache models
│   ├── canonical/                          14 canonical metadata models
│   ├── documentation/                      Documentation models
│   ├── entities/                           10 entity classes
│   ├── events/                             5 domain event types
│   ├── graph/                              Graph models + traversal
│   ├── impact/                             Impact analysis models
│   ├── jobs/                               Job models
│   ├── metadata/                           9 metadata subdomain models
│   ├── observability/                      Observability models
│   ├── policies/                           (empty)
│   ├── ports/                              Repository interfaces
│   ├── repositories/                       10 repository interfaces
│   ├── search/                             Search models
│   ├── security/                           Security models
│   ├── services/                           (empty)
│   └── value_objects/                      5 value objects
├── infrastructure/
│   ├── cache/                              13 files — Redis caching
│   ├── database/                           3 files + models — SQLAlchemy
│   ├── documentation/                      7 files — Doc generation
│   ├── event_bus/                          1 file — (empty stub)
│   ├── graph/                              8 files — Dependency graph
│   ├── impact/                             12 files — Impact analysis
│   ├── jobs/                               15 files — Async job engine
│   ├── llm/                                8 files + 8 providers — AI
│   ├── observability/                      9 files — Observability
│   ├── parsers/                            20 files — Metadata parsers
│   ├── persistence/                        11 models + 10 repos
│   ├── queue/                              1 file — (empty stub)
│   ├── salesforce/                         Client + OAuth + sync
│   ├── search/                             10 files — Search engine
│   ├── security/                           13 files — Security
│   └── time/                               3 files — Clock
├── ports/
│   ├── repositories/__init__.py
│   └── services/
│       └── cache_port.py                   Abstract CachePort
├── workers/
│   ├── celery.py                            Celery app config
│   ├── scheduler.py                         Celery beat schedule
│   └── tasks/metadata_sync.py               Celery tasks
└── shared/
    ├── exceptions/                          3 exception files
    ├── middleware/tenant_context.py          ContextVars
    └── utils/                               2 utility files
```

### Module Overview

| Module | Responsibility | Key Files |
|--------|---------------|-----------|
| **Auth** | User registration, login, JWT, OAuth (Salesforce) | `application/use_cases/auth.py`, `infrastructure/security/jwt.py`, `infrastructure/security/password.py` |
| **Organizations** | Multi-tenant org management, members, roles | `application/use_cases/organization.py`, `application/use_cases/rbac.py` |
| **Salesforce** | OAuth connection, metadata download, sync | `infrastructure/salesforce/`, `application/use_cases/salesforce.py` |
| **Metadata Sync** | Full/incremental sync, change detection, retry | `application/use_cases/metadata_sync.py`, `infrastructure/jobs/` |
| **Dependency Graph** | Build, traverse, resolve metadata dependencies | `infrastructure/graph/`, `application/use_cases/graph/` |
| **Impact Analysis** | Blast radius, change simulation, risk assessment | `infrastructure/impact/` |
| **Search** | Full-text search, autocomplete, ranking | `infrastructure/search/` |
| **Documentation** | Auto-generate documentation from metadata | `infrastructure/documentation/` |
| **AI** | Multi-provider LLM orchestration, safety, citations | `infrastructure/llm/`, `application/use_cases/ai/` |
| **Security** | Encryption, audit, RBAC, rate limiting, abuse detection | `infrastructure/security/` |
| **Observability** | Tracing (OTel), metrics (Prometheus), logging (structlog) | `infrastructure/observability/` |
| **Cache** | Redis caching with TTL, invalidation, tenant isolation | `infrastructure/cache/`, `application/cache/` |
| **Jobs** | Async task orchestration, scheduling, retry, progress | `infrastructure/jobs/` |
| **Parsers** | Salesforce metadata parsing (Apex, objects, layouts, etc.) | `infrastructure/parsers/` |

### API Overview

**Base URL:** `/api/v1`  
**Total endpoints:** 62 REST + 1 WebSocket  
**Auth:** JWT Bearer token in `Authorization` header  
**Errors:** RFC 7807 ProblemResponse format

| Resource | Endpoints | Purpose |
|----------|-----------|---------|
| **Health** | `GET /health/live`, `/health/ready`, `/health/status` | Liveness, readiness, detailed status |
| **Auth** | `POST /auth/register`, `/auth/login`, `/auth/logout`, `/auth/refresh`, `GET /auth/me` | User authentication |
| **Organizations** | `POST /organizations`, `GET /organizations`, `POST /organizations/{id}/switch`, `GET /organizations/current` | Multi-tenant management |
| **Salesforce** | `POST /salesforce/connect`, `GET /salesforce/callback`, `POST /salesforce/disconnect`, `GET /salesforce/status`, `GET /salesforce/health` | Salesforce OAuth + connection |
| **Sync** | `POST /sync/start`, `GET /sync/jobs`, `GET /sync/jobs/{id}`, `POST /sync/jobs/{id}/cancel`, `POST /sync/jobs/{id}/pause`, `POST /sync/jobs/{id}/resume`, `GET /sync/history`, `GET /sync/statistics`, `GET /sync/retry-queue` | Metadata synchronization |
| **Graph** | `POST /graph/build`, `GET /graph/summary`, `GET /graph/dependencies/{type}/{name}`, `GET /graph/impact/{type}/{name}`, `GET /graph/cycles`, `GET /graph/nodes` | Dependency graph |
| **Dependencies** | `GET /dependencies`, `GET /dependencies/{type}/{name}`, `GET /dependencies/{type}/{name}/tree`, `GET /dependencies/{type}/{name}/reverse`, `GET /dependencies/{type}/{name}/graph` | Dependency queries |
| **Search** | `GET /search`, `GET /search/global`, `GET /search/autocomplete`, `GET /search/dependencies` | Metadata search |
| **Impact Analysis** | `POST /impact-analysis`, `POST /impact-analysis/simulate`, `GET /impact-analysis/{id}`, `GET /impact-analysis/{id}/report` | Impact analysis |
| **Documentation** | `GET /documentation`, `POST /documentation/generate`, `GET /documentation/export`, `GET /documentation/{type}/{name}` | Auto-generated docs |
| **AI** | `POST /ai/query`, `/ai/chat`, `/ai/explain`, `/ai/summarize`, `/ai/documentation`, `/ai/release-notes`, `/ai/search`, `GET /ai/providers`, `GET /ai/usage`, `GET /ai/tools` | AI features |
| **Jobs** | `GET /jobs`, `GET /jobs/{id}`, `POST /jobs/{id}/cancel`, `POST /jobs/{id}/retry`, `GET /jobs/{id}/progress`, `GET /jobs/metrics`, `GET /jobs/workers` | Job management |
| **Security** | `GET /security/status`, `GET /security/audit-log`, `GET /security/policies`, `POST /security/policies/evaluate` | Security management |
| **Admin** | `GET /admin/users`, `/admin/organizations`, `/admin/audit`, `/admin/system`, `/admin/configuration`, `/admin/cache/*`, `/admin/version` | Admin operations |
| **Observability** | `GET /observability/status` | Observability status |

### Authentication Flow

```
┌──────┐          ┌──────────┐          ┌───────────┐          ┌──────────┐
│ User │          │  Client  │          │  Backend  │          │    DB    │
└──┬───┘          └────┬─────┘          └─────┬─────┘          └────┬─────┘
   │                    │                      │                     │
   │   Register         │                      │                     │
   │───────────────────►│  POST /auth/register │                     │
   │                    │─────────────────────►│                     │
   │                    │                      │  INSERT user        │
   │                    │                      │────────────────────►│
   │                    │                      │  (bcrypt hash)      │
   │                    │                      │◄────────────────────│
   │                    │                      │  INSERT audit_log   │
   │                    │                      │────────────────────►│
   │                    │  Tokens + user       │                     │
   │                    │◄─────────────────────│                     │
   │◄───────────────────│                      │                     │
   │                    │                      │                     │
   │   Login            │                      │                     │
   │───────────────────►│  POST /auth/login    │                     │
   │                    │─────────────────────►│                     │
   │                    │                      │  SELECT user(email) │
   │                    │                      │────────────────────►│
   │                    │                      │◄────────────────────│
   │                    │                      │  bcrypt checkpw     │
   │                    │                      │  5 fails → lock 15m│
   │                    │                      │  CREATE session     │
   │                    │                      │  CREATE refresh_tok │
   │                    │  Access(30m)+Refresh │  JWT(sub,org,role)  │
   │                    │◄─────────────────────│                     │
   │◄───────────────────│                      │                     │
   │                    │                      │                     │
   │   API Call         │                      │                     │
   │───────────────────►│  GET /api/v1/...     │                     │
   │                    │  Authorization:      │                     │
   │                    │  Bearer <jwt>        │                     │
   │                    │─────────────────────►│                     │
   │                    │                      │  Validate JWT       │
   │                    │                      │  Extract org+role   │
   │                    │                      │  Check permission   │
   │                    │                      │  Return data        │
   │                    │◄─────────────────────│                     │
   │◄───────────────────│                      │                     │
```

### Salesforce Flow

```
┌──────────────┐   ┌──────────┐   ┌────────────────┐   ┌───────────────┐
│ Chrome Ext   │   │ Backend  │   │ Salesforce API  │   │   Database    │
└──────┬───────┘   └────┬─────┘   └───────┬────────┘   └───────┬───────┘
       │                 │                 │                     │
       │ POST /connect   │                 │                     │
       │────────────────►│                 │                     │
       │                 │                 │                     │
       │ Return auth URL │                 │                     │
       │◄────────────────│                 │                     │
       │                 │                 │                     │
       │ Open browser    │                 │                     │
       │────────────────►│                 │                     │
       │                 │ GET /callback   │                     │
       │                 │ (code+state)    │                     │
       │                 │                 │                     │
       │                 │                 │ POST /oauth2/token  │
       │                 │                 │ (code+verifier)     │
       │                 │                 │◄────────────────────│
       │                 │                 │                     │
       │                 │ Encrypt tokens  │ tokens               │
       │                 │────────────────►│                     │
       │                 │                 │                     │
       │                 │                 │                     │
       │                 │                 │                     │
```

### Deployment Architecture

```
                     ┌───────────────────────┐
                     │     Internet          │
                     └──────────┬────────────┘
                                │
                     ┌──────────▼────────────┐
                     │   Ingress (nginx)      │
                     │   api.sfir.dev         │
                     │   TLS (cert-manager)   │
                     └──────────┬────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                  │
     ┌────────▼───────┐ ┌──────▼───────┐  ┌──────▼───────┐
     │  API Pod 1     │ │  API Pod 2   │  │  API Pod 3   │
     │  (FastAPI)     │ │  (FastAPI)   │  │  (FastAPI)   │
     │  HPA 3-20      │ │              │  │              │
     └────────────────┘ └──────────────┘  └──────────────┘
              │                 │                  │
              └─────────────────┼──────────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                  │
     ┌────────▼───────┐ ┌──────▼───────┐  ┌──────▼───────┐
     │  PostgreSQL 16 │ │  Redis 7     │  │  Celery      │
     │  StatefulSet   │ │  StatefulSet  │  │  Workers     │
     │  100Gi PVC     │ │  50Gi PVC    │  │  3 pods       │
     │  single replica│ │  single      │  │  4 queues     │
     └────────────────┘ └──────────────┘  └──────────────┘
                                                  │
                                          ┌──────▼───────┐
                                          │  Celery Beat  │
                                          │  (scheduler)  │
                                          └──────────────┘
```

---

## Part 7 — Complete Developer Guide

### Prerequisites

#### Supported Operating Systems

- macOS 14+ (Sonoma/Sequoia)
- Ubuntu 22.04+ or Debian 12+
- Windows 11 with WSL2 (Ubuntu 22.04+)

#### Required Software

| Software | Version | Purpose |
|----------|---------|---------|
| Python | **3.13+** | Runtime |
| PostgreSQL | **16+** | Primary database |
| Redis | **7+** | Cache, queue broker, rate limiting |
| Docker | **24+** | Containerization |
| Docker Compose | **2.24+** | Local orchestration |
| Git | **2.40+** | Version control |
| uv | **0.4+** | Python dependency management |
| Make | **4.0+** | Build automation |
| kubectl | **1.30+** | Kubernetes CLI (deployment only) |
| Helm | **3.15+** | Kubernetes package manager (deployment only) |

#### Python Version

```bash
python --version  # Must be 3.13+
```

Install via `pyenv` or `uv python install`:

```bash
# Using uv (recommended)
uv python install 3.13

# Or use pyenv
pyenv install 3.13.0
pyenv local 3.13.0
```

#### PostgreSQL Version

```bash
psql --version  # Must be 16+
```

#### Redis Version

```bash
redis-cli --version  # Must be 7+
```

### Installation

#### 1. Clone the Repository

```bash
git clone https://github.com/sfir/sfir-backend.git
cd sfir-backend
```

#### 2. Install Dependencies

**Using uv (recommended):**

```bash
# Install all dependencies (including dev)
uv sync --dev

# Or production-only
uv sync --no-dev
```

**Using pip (alternative):**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

#### 3. Configure Environment

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` with your configuration. See [Environment Variables](#environment-variables) for details.

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SFIR_ENVIRONMENT` | No | `development` | `development`, `staging`, `production`, `testing` |
| `SFIR_DATABASE_URL` | Yes | `postgresql+asyncpg://sfir:sfir@localhost:5432/sfir` | PostgreSQL connection string |
| `SFIR_DATABASE_ECHO` | No | `False` | Log all SQL queries |
| `SFIR_DATABASE_POOL_SIZE` | No | `10` | Database connection pool size |
| `SFIR_DATABASE_MAX_OVERFLOW` | No | `20` | Max overflow connections |
| `SFIR_REDIS_URL` | Yes | `redis://localhost:6379/0` | Redis connection string |
| `SFIR_CELERY_BROKER_URL` | Yes | `redis://localhost:6379/1` | Celery broker URL |
| `SFIR_CELERY_RESULT_BACKEND` | Yes | `redis://localhost:6379/2` | Celery result backend |
| `SFIR_CELERY_WORKER_CONCURRENCY` | No | `4` | Celery worker concurrency |
| `SFIR_JWT_SECRET_KEY` | Yes | *(dev default)* | JWT signing key (CHANGE IN PRODUCTION) |
| `SFIR_JWT_ALGORITHM` | No | `HS256` | JWT algorithm |
| `SFIR_JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | No | `30` | Access token expiry |
| `SFIR_JWT_REFRESH_TOKEN_EXPIRE_DAYS` | No | `7` | Refresh token expiry |
| `SFIR_ENCRYPTION_KEY` | Yes | *(dev default)* | AES-256-GCM master key (CHANGE IN PRODUCTION) |
| `SFIR_SALESFORCE_CLIENT_ID` | No | — | Salesforce Connected App client ID |
| `SFIR_SALESFORCE_CLIENT_SECRET` | No | — | Salesforce Connected App client secret |
| `SFIR_SALESFORCE_REDIRECT_URI` | No | — | OAuth redirect URI |
| `SFIR_OPENAI_API_KEY` | No | — | OpenAI API key |
| `SFIR_ANTHROPIC_API_KEY` | No | — | Anthropic API key |
| `SFIR_GEMINI_API_KEY` | No | — | Google Gemini API key |
| `SFIR_AZURE_OPENAI_*` | No | — | Azure OpenAI configuration |
| `SFIR_OPENROUTER_API_KEY` | No | — | OpenRouter API key |
| `SFIR_AWS_*` | No | — | AWS Bedrock configuration |
| `SFIR_OTLP_ENDPOINT` | No | — | OpenTelemetry collector endpoint |
| `SFIR_LOG_LEVEL` | No | `INFO` | Logging level |
| `SFIR_LOG_FORMAT` | No | `json` | `json` or `console` |
| `SFIR_CORS_ORIGINS` | No | `["http://localhost:8000"]` | Allowed CORS origins |

### Database Setup

#### Start PostgreSQL

**Using Docker:**

```bash
make docker-up-infra
# or manually:
docker run -d \
  --name sfir-postgres \
  -e POSTGRES_USER=sfir \
  -e POSTGRES_PASSWORD=sfir \
  -e POSTGRES_DB=sfir \
  -p 5432:5432 \
  postgres:16-alpine
```

**Using local install (Ubuntu/WSL):**

```bash
sudo apt install postgresql-16
sudo service postgresql start
sudo -u postgres createuser sfir -P  # password: sfir
sudo -u postgres createdb sfir -O sfir
```

**Using macOS (Homebrew):**

```bash
brew install postgresql@16
brew services start postgresql@16
createuser sfir -P  # password: sfir
createdb sfir -O sfir
```

#### Run Migrations

```bash
make migrate
# or:
uv run alembic upgrade head
```

> **Note:** Migration files are not yet created. Run `make alembic-autogen name="initial"` to generate the first migration from current model definitions.

### Redis Setup

**Using Docker:**

```bash
docker run -d \
  --name sfir-redis \
  -p 6379:6379 \
  redis:7-alpine
```

**Using local install (Ubuntu/WSL):**

```bash
sudo apt install redis-server
sudo service redis-server start
```

**Using macOS (Homebrew):**

```bash
brew install redis@7
brew services start redis@7
```

### Salesforce Connected App Setup

1. In Salesforce Setup, navigate to **App Manager → New Connected App**
2. Configure:
   - **Connected App Name:** SF Inspector Backend
   - **API Name:** SF_Inspector_Backend  
   - **Enable OAuth Settings:** Checked
   - **Callback URL:** `http://localhost:8000/api/v1/salesforce/callback`
   - **Selected OAuth Scopes:**
     - `Access your basic information (id, profile, email, address, phone)`
     - `Access and manage your data (api)`
     - `Perform requests on your behalf at any time (refresh_token, offline_access)`
   - **Require Secret for Web Server Flow:** Checked
   - **Require Proof Key for Code Exchange (PKCE):** Checked
3. Save and note the **Consumer Key** and **Consumer Secret**
4. Set environment variables:
   ```bash
   SFIR_SALESFORCE_CLIENT_ID=<consumer_key>
   SFIR_SALESFORCE_CLIENT_SECRET=<consumer_secret>
   SFIR_SALESFORCE_REDIRECT_URI=http://localhost:8000/api/v1/salesforce/callback
   ```

### Running the Application

#### Start the API Server

```bash
# Development mode (auto-reload)
uv run uvicorn sfir_backend.main:app --reload --host 0.0.0.0 --port 8000

# Production mode
uv run uvicorn sfir_backend.main:app \
  --host 0.0.0.0 --port 8000 \
  --workers 4 \
  --loop uvloop \
  --http httptools
```

#### Start Background Workers

```bash
# Start Celery worker
uv run celery -A sfir_backend.workers.celery worker \
  --loglevel=INFO \
  --concurrency=4 \
  -Q default,metadata,graph,ai

# Start Celery beat scheduler
uv run celery -A sfir_backend.workers.celery beat --loglevel=INFO
```

#### Using Docker Compose

```bash
# Start infrastructure only (Postgres + Redis)
make docker-up-infra

# Start full stack
make docker-up

# Start production-like stack
make docker-up-prod
```

#### Using Makefile

```bash
make install       # Install dependencies
make dev-install   # Install with dev dependencies
make lint          # Run Ruff linter
make typecheck     # Run MyPy
make test          # Run all tests
make test-cov      # Run tests with coverage
make migrate       # Run database migrations
```

### Verifying the Application

#### Health Endpoints

```bash
# Liveness probe
curl http://localhost:8000/api/v1/health/live
# → {"status": "healthy"}

# Readiness probe
curl http://localhost:8000/api/v1/health/ready
# → {"status": "healthy", "database": "connected"}

# Detailed status
curl http://localhost:8000/api/v1/health/status
# → {"status": "healthy", "version": "0.1.0", ...}
```

#### API Version

```bash
curl http://localhost:8000/version
# → {"service": "sfir-backend", "version": "0.1.0", "environment": "development"}
```

#### Authentication Flow

```bash
# Register a new user
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "password123", "display_name": "Test User"}'

# Login
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "password123"}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# Use token
curl http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer $TOKEN"
```

### Running Tests

```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run specific test file
uv run pytest tests/unit/test_auth.py -v

# Run AI tests
uv run pytest tests/unit/ai/ -v

# Run security tests
uv run pytest tests/unit/security/ -v

# Run with specific marker
uv run pytest -m "asyncio" -v
```

### Debugging

#### Logs

```bash
# Development logs (console format)
SFIR_LOG_FORMAT=console uv run uvicorn sfir_backend.main:app --reload

# Follow Docker logs
make docker-logs

# View Celery worker logs
docker compose logs -f celery-worker
```

#### Health Endpoints

- `GET /api/v1/health/live` — Simple liveness check (no DB required)
- `GET /api/v1/health/ready` — Readiness check (verifies DB connection)
- `GET /api/v1/health/status` — Detailed health status

#### Metrics

```bash
# Prometheus metrics
curl http://localhost:8000/metrics
```

#### OpenAPI Documentation

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

### Troubleshooting

| Problem | Check | Solution |
|---------|-------|----------|
| Database connection error | PostgreSQL running? | `docker compose up -d postgres` |
| Redis connection error | Redis running? | `docker compose up -d redis` |
| "Table not found" | Migrations run? | `make migrate` |
| JWT errors | `SFIR_JWT_SECRET_KEY` set? | Check `.env` file |
| Salesforce connection fails | Client ID/Secret correct? | Check Salesforce Connected App |
| AI returns "not configured" | API key set? | Set `SFIR_OPENAI_API_KEY` or other provider |
| Celery tasks not running | Worker started? | Start worker with `uv run celery -A sfir_backend.workers.celery worker` |
| Permission denied | User has correct role? | Check `OrgMember` role in database |

### Recovery Procedures

See `ops/runbooks/` for detailed recovery procedures:

| Runbook | Covers |
|---------|--------|
| `DATABASE_FAILURE.md` | Connection loss, corruption, replication lag |
| `REDIS_FAILURE.md` | Memory pressure, data loss, replica promotion |
| `API_DEGRADATION.md` | Latency spikes, error rate increase, scaling |
| `SALESFORCE_OUTAGE.md` | Sync failures, OAuth errors, API rate limits |

---

## Part 8 — How to Run the Application

### Complete Step-by-Step Guide

#### 1. Clone Repository

```bash
git clone https://github.com/sfir/sfir-backend.git
cd sfir-backend
```

#### 2. Install Dependencies

```bash
# Ensure Python 3.13+ is available
python --version  # Must be >= 3.13

# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install all dependencies
uv sync --dev

# Activate virtual environment
source .venv/bin/activate  # Linux/macOS
# or:
.venv\Scripts\activate     # Windows
```

#### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your settings
# At minimum, ensure database and Redis URLs are correct:
# SFIR_DATABASE_URL=postgresql+asyncpg://sfir:sfir@localhost:5432/sfir
# SFIR_REDIS_URL=redis://localhost:6379/0
```

#### 4. Start PostgreSQL

```bash
# Option A: Docker
docker run -d \
  --name sfir-postgres \
  -e POSTGRES_USER=sfir \
  -e POSTGRES_PASSWORD=sfir \
  -e POSTGRES_DB=sfir \
  -p 5432:5432 \
  postgres:16-alpine

# Option B: Make target
make docker-up-infra
```

Verify:
```bash
pg_isready -h localhost -p 5432 -U sfir
# → localhost:5432 - accepting connections
```

#### 5. Start Redis

```bash
# Option A: Docker
docker run -d \
  --name sfir-redis \
  -p 6379:6379 \
  redis:7-alpine

# Option B: Make target (already included in docker-up-infra)
```

Verify:
```bash
redis-cli ping
# → PONG
```

#### 6. Run Migrations

```bash
make migrate
# If no migrations exist yet, generate initial:
make alembic-autogen name="initial"
make migrate
```

Verify:
```bash
uv run alembic current
# → Should show current migration head
```

#### 7. Seed Initial Data (if applicable)

```bash
# Create admin user via API
curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@sfir.dev", "password": "admin123!", "display_name": "Admin"}' \
  | python -m json.tool
```

Log the token:
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@sfir.dev", "password": "admin123!"}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
echo "TOKEN=$TOKEN"
```

#### 8. Configure Salesforce Connected App

1. Create a Connected App in Salesforce (see Part 7 section)
2. Set environment variables:
   ```bash
   export SFIR_SALESFORCE_CLIENT_ID=<your_consumer_key>
   export SFIR_SALESFORCE_CLIENT_SECRET=<your_consumer_secret>
   export SFIR_SALESFORCE_REDIRECT_URI=http://localhost:8000/api/v1/salesforce/callback
   ```

#### 9. Start Backend

```bash
# Development mode with auto-reload
make dev-install
uv run uvicorn sfir_backend.main:app --reload --host 0.0.0.0 --port 8000

# (In a separate terminal, or use background)
```

#### 10. Start Background Workers

```bash
# Terminal 2: Celery worker
uv run celery -A sfir_backend.workers.celery worker \
  --loglevel=INFO \
  --concurrency=4 \
  -Q default,metadata,graph,ai

# Terminal 3: Celery beat scheduler
uv run celery -A sfir_backend.workers.celery beat --loglevel=INFO
```

#### 11. Verify Health Endpoints

```bash
# Liveness
curl http://localhost:8000/api/v1/health/live
# Expected: {"status":"healthy"}

# Readiness
curl http://localhost:8000/api/v1/health/ready
# Expected: {"status":"healthy","database":"connected"}

# Detailed
curl http://localhost:8000/api/v1/health/status
# Expected: {"status":"healthy","version":"0.1.0","environment":"development"}
```

#### 12. Connect Salesforce

```bash
# Get the OAuth URL (requires auth token)
curl http://localhost:8000/api/v1/salesforce/connect \
  -H "Authorization: Bearer $TOKEN"
# → Returns authorization URL — open in browser

# After authorizing, Salesforce redirects to:
# http://localhost:8000/api/v1/salesforce/callback?code=...&state=...
# The backend handles the callback automatically
```

#### 13. Check Connection Status

```bash
curl http://localhost:8000/api/v1/salesforce/status \
  -H "Authorization: Bearer $TOKEN"
# Expected: {"connected":true,"org_id":"00D...","org_name":"My Org"}
```

#### 14. Run First Metadata Sync

```bash
# Start full metadata sync
curl -X POST http://localhost:8000/api/v1/sync/start \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sync_type":"full"}'
# Expected: {"job_id":"...","status":"running"}

# Check sync status
curl http://localhost:8000/api/v1/sync/jobs \
  -H "Authorization: Bearer $TOKEN"
# Expected: {"jobs":[...],"total":1}
```

#### 15. Verify Metadata

```bash
# Search metadata
curl "http://localhost:8000/api/v1/search?q=Account" \
  -H "Authorization: Bearer $TOKEN"
# Expected: {"results":[...],"total":...}
```

#### 16. Build Dependency Graph

```bash
# Build the graph
curl -X POST http://localhost:8000/api/v1/graph/build \
  -H "Authorization: Bearer $TOKEN"
# Expected: {"job_id":"...","status":"building"}

# Check graph summary
curl http://localhost:8000/api/v1/graph/summary \
  -H "Authorization: Bearer $TOKEN"
# Expected: {"node_count":...,"edge_count":...}
```

#### 17. Verify Search

```bash
# Full-text search
curl "http://localhost:8000/api/v1/search?q=ClassName&type=ApexClass" \
  -H "Authorization: Bearer $TOKEN"

# Autocomplete
curl "http://localhost:8000/api/v1/search/autocomplete?q=Acc" \
  -H "Authorization: Bearer $TOKEN"

# Global search
curl "http://localhost:8000/api/v1/search/global?q=Account" \
  -H "Authorization: Bearer $TOKEN"
```

#### 18. Verify Impact Analysis

```bash
# Analyze impact of changing a component
curl -X POST http://localhost:8000/api/v1/impact-analysis \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"component_type":"ApexClass","component_name":"MyController"}'
```

#### 19. Generate Documentation

```bash
# Generate documentation for a component
curl http://localhost:8000/api/v1/documentation/ApexClass/MyController \
  -H "Authorization: Bearer $TOKEN"

# Generate all documentation
curl -X POST http://localhost:8000/api/v1/documentation/generate \
  -H "Authorization: Bearer $TOKEN"
```

#### 20. Test AI

```bash
# Explain a component
curl -X POST http://localhost:8000/api/v1/ai/explain \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"component_type":"ApexClass","component_name":"AccountController","provider":"openai"}'

# Chat with AI
curl -X POST http://localhost:8000/api/v1/ai/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"What are the top-level dependencies of AccountController?","feature":"dependency_analysis","provider":"openai"}'

# Get available AI providers
curl http://localhost:8000/api/v1/ai/providers \
  -H "Authorization: Bearer $TOKEN"

# Get AI usage stats
curl http://localhost:8000/api/v1/ai/usage \
  -H "Authorization: Bearer $TOKEN"
```

#### 21. Verify Production Readiness

```bash
# Run production checks
make prod-check
# → Runs lint + typecheck + tests with coverage

# Build production Docker image
make prod-build

# Run security scan (requires Trivy)
make security-scan
```

#### 22. Full Stack with Docker Compose

```bash
# Start everything
make docker-up

# Or production-like stack
make docker-up-prod

# View logs
make docker-logs

# Stop
make docker-down
```

---

## Part 9 — Production Deployment Guide

### Deployment Checklist

Pre-deployment checks:

- [ ] All tests pass: `make test`
- [ ] Lint passes: `make lint`
- [ ] Type check passes: `make typecheck`
- [ ] Security scan passes: `make security-scan`
- [ ] Production image built: `make prod-build`
- [ ] Environment variables configured for production
- [ ] Database migrations generated and tested
- [ ] Secrets configured (Vault/AWS Secrets Manager)
- [ ] CORS origins locked to specific extension IDs
- [ ] JWT secret key changed from default
- [ ] Encryption key changed from default
- [ ] Rate limiting configured for production scale
- [ ] Logging configured (JSON format, log aggregation)
- [ ] Monitoring configured (Prometheus + Grafana)

### Production Deployment Steps

#### 1. Build and Push Docker Image

```bash
# Build
docker build -f Dockerfile.prod -t ghcr.io/sfir/sfir-backend:latest .
docker build -f Dockerfile.prod -t ghcr.io/sfir/sfir-backend:v0.1.0 .

# Push
docker push ghcr.io/sfir/sfir-backend:latest
docker push ghcr.io/sfir/sfir-backend:v0.1.0
```

#### 2. Deploy to Kubernetes

```bash
# Using Kustomize
kubectl apply -k deploy/k8s/base/

# Using Helm
helm upgrade --install sfir-backend deploy/helm/sfir-backend/ \
  --namespace sfir \
  --create-namespace \
  --set secrets.SFIR_JWT_SECRET_KEY="<production-key>" \
  --set secrets.SFIR_ENCRYPTION_KEY="<production-key>" \
  --set secrets.SFIR_DB_PASSWORD="<production-password>" \
  --set secrets.SFIR_OPENAI_API_KEY="<openai-key>" \
  --set ingress.host="api.sfir.dev"

# Verify deployment
kubectl -n sfir get pods
kubectl -n sfir get svc
kubectl -n sfir get ingress
```

#### 3. Run Database Migrations

```bash
# Run as a job or via kubectl exec
kubectl -n sfir exec deploy/sfir-api -- alembic upgrade head
```

#### 4. Verify Health

```bash
# External health check
curl https://api.sfir.dev/api/v1/health/live
curl https://api.sfir.dev/api/v1/health/ready
```

### Rollback Procedure

```bash
# Kubernetes: Roll back to previous revision
kubectl -n sfir rollout undo deploy/sfir-api

# Helm: Roll back to previous release
helm rollback sfir-backend 1 --namespace sfir

# Docker Compose: Revert to previous image tag
docker compose -f docker-compose.prod.yml down
# Edit docker-compose.prod.yml to use previous tag
docker compose -f docker-compose.prod.yml up -d

# Database: Downgrade migration
kubectl -n sfir exec deploy/sfir-api -- alembic downgrade -1
```

### Backup Procedure

```bash
# Database backup
pg_dump -h <host> -U sfir -d sfir > sfir_backup_$(date +%Y%m%d).sql

# Kubernetes: Backup using pg_dump
kubectl -n sfir exec deploy/sfir-postgres-0 -- pg_dump -U sfir sfir > sfir_backup.sql

# Automate backups (cron)
0 2 * * * pg_dump -h localhost -U sfir sfir | gzip > /backups/sfir_$(date +\%Y\%m\%d).sql.gz
```

### Disaster Recovery

| Scenario | RTO | RPO | Recovery Steps |
|----------|-----|-----|----------------|
| Database loss | < 15 min | < 5 min | Restore from WAL + latest backup |
| Redis loss | < 5 min | < 1 min | Restart Redis, cache will rebuild |
| API failure | < 5 min | 0 | Kubernetes auto-heals (HPA + rolling update) |
| Worker failure | < 10 min | 0 | Kubernetes reschedules pods |
| Full region failure | < 1 hr | < 15 min | Restore from cross-region backup + re-deploy |

### Monitoring Setup

**Prometheus:** `http://prometheus:9090`  
**Grafana:** `http://grafana:3000` (admin/admin)  
**OpenTelemetry Collector:** `http://otel-collector:4318`

Pre-built dashboards are not yet included. Create Grafana dashboards for:

1. **API Performance:** Request rate, latency (p50/p95/p99), error rate
2. **Database:** Connection count, query time, active queries, cache hit ratio
3. **Redis:** Memory usage, hit rate, evictions, connected clients
4. **Celery:** Queue depth, task duration, success/failure rate
5. **Cache:** Hit ratio per cache service, invalidation rate
6. **AI:** Request rate, latency per provider, token usage
7. **Business:** Active orgs, sync jobs, search queries

### Alert Configuration

Define Prometheus alerting rules for:

| Alert | Condition | Severity | Channel |
|-------|-----------|----------|---------|
| API Down | `up{job="api"} == 0` | Critical | PagerDuty |
| High Error Rate | `rate(http_errors[5m]) > 0.01` | Critical | PagerDuty |
| High Latency | `http_latency_p99 > 2s` | Warning | Slack |
| Database Down | `pg_up == 0` | Critical | PagerDuty |
| Redis Down | `redis_up == 0` | Critical | PagerDuty |
| High Redis Memory | `redis_memory_used_bytes / redis_memory_max_bytes > 0.85` | Warning | Slack |
| High DB Connections | `pg_stat_activity_count > 50` | Warning | Slack |
| Error Budget Depleted | Error budget < 30% remaining | Warning | Slack |
| Cache Hit Ratio Low | `cache_hit_ratio < 0.50` | Warning | Slack |
| AI Error Rate | `ai_error_rate > 0.05` | Warning | Slack |

### Scaling Guide

| Component | Scale Strategy | Max |
|-----------|---------------|-----|
| API (FastAPI) | Horizontal (K8s HPA) | 20 pods |
| Celery Workers | Horizontal (manual/adjust concurrency) | 10 pods, concurrency 8 |
| PostgreSQL | Vertical (bigger instance) + read replicas | 32 vCPU, 128GB RAM |
| Redis | Vertical (bigger instance) + cluster mode | 64GB RAM |
| AI Providers | Horizontal (per-provider API keys/rate limits) | N/A (external) |

### Maintenance Guide

#### Routine Maintenance (Weekly)

```bash
# Database maintenance
VACUUM ANALYZE;
REINDEX DATABASE sfir;

# Check connection pool usage
SELECT count(*) FROM pg_stat_activity WHERE datname = 'sfir';

# Review slow queries
SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10;

# Check Redis memory
INFO memory | grep used_memory_human

# Check Redis hit rate
INFO stats | grep keyspace_hits
```

#### Routine Maintenance (Monthly)

```bash
# Review error budgets
# Check SLO compliance in monitoring dashboard

# Rotate encryption keys (if not automated)
# via security endpoint

# Review audit logs
# Identify abuse patterns, adjust rate limits

# Review Prometheus metrics
# Identify trends, adjust scaling thresholds
```

#### Routine Maintenance (Quarterly)

```bash
# Full DR drill
# Restore from backup, verify data integrity

# Security audit
# Review access patterns, update blocked patterns in SafetyFilter

# Dependency updates
# Update all Python dependencies
# Review deprecation notices

# Load testing
# Re-run Locust tests, compare against baseline
```

---

## Part 10 — Final Report

### Architecture Scores

| Dimension | Score | Rationale |
|-----------|-------|-----------|
| **Overall Architecture** | **8.5/10** | Clean hexagonal architecture, strong separation of concerns. Deductions for layer violations in metadata_sync.py and empty stub directories. |
| **Production Readiness** | **6.5/10** | Deployment artifacts exist but no CI/CD pipeline, no migration files, no integration tests. Small fixes needed for production hardening. |
| **Maintainability** | **8.0/10** | Well-organized folder structure, consistent naming, strong typing. Deduction for 873-line metadata_sync.py and 620-line container.py. |
| **Security** | **8.0/10** | Strong encryption, RBAC, tenant isolation, audit logging. Deductions for CORS wildcard, PBKDF2 config, regex-only SafetyFilter. |
| **Performance** | **7.0/10** | Good async coverage, connection pooling, Redis caching. Deductions for N+1 query risk, no eager loading, OFFSET pagination, no bulk operations. |
| **Scalability** | **7.5/10** | Stateless API design, Redis for distributed state, Celery for async jobs. Deductions for single-replica Postgres/Redis in k8s manifests, no read replicas. |
| **Code Quality** | **8.0/10** | SOLID principles followed, good error handling, consistent patterns. Some files too large, some dead code. |
| **Testing** | **7.0/10** | Strong unit test coverage (~1,336 tests). Deductions for zero integration tests, zero API tests, no performance benchmarks. |

### Technical Debt Assessment

| Category | Debt Level | Details |
|----------|------------|---------|
| **Missing CI/CD** | Critical | No automated build/test/deploy for backend |
| **Missing migrations** | Critical | No way to track or roll back schema changes |
| **Dead code stubs** | Low | 6 empty directories should be removed |
| **Layer violations** | Medium | 2 application files import infrastructure directly |
| **N+1 queries** | Medium | No eager loading in repository layer |
| **Large files** | Medium | Split `metadata_sync.py` and `container.py` |
| **No integration tests** | High | Cannot validate DB/Redis interactions |
| **CORS wildcard** | Medium | Should lock to specific extension IDs |
| **PBKDF2 config** | Low | Fix `_is_production` hardcoded value |
| **Redis pool config** | Low | Move hardcoded values to settings |

### Top 20 Improvement Recommendations

| # | Priority | Category | Recommendation | Effort | Impact |
|---|----------|----------|---------------|--------|--------|
| 1 | **CRITICAL** | CI/CD | Create backend CI pipeline (lint, typecheck, test, build, scan) | 1 day | Production enabler |
| 2 | **CRITICAL** | CI/CD | Create backend CD pipeline (build, push, deploy) | 1 day | Production enabler |
| 3 | **CRITICAL** | Database | Generate initial Alembic migration from current models | 1 hour | Schema management |
| 4 | **HIGH** | Performance | Add `selectinload()` to all repository list methods | 1 day | N+1 fix |
| 5 | **HIGH** | Testing | Write integration tests for repositories (Postgres + Redis) | 2 days | Test coverage |
| 6 | **HIGH** | Testing | Write API endpoint tests using FastAPI TestClient | 2 days | Test coverage |
| 7 | **HIGH** | Security | Lock CORS origins to specific Chrome extension IDs | 15 min | Security |
| 8 | **HIGH** | Performance | Implement `session.add_all()` + single flush in `save_many()` | 30 min | Bulk insert perf |
| 9 | **HIGH** | Security | Add password strength validation to registration | 30 min | Security |
| 10 | **HIGH** | Code Quality | Split `metadata_sync.py` into separate strategy files | 2 hours | Maintainability |
| 11 | **HIGH** | Code Quality | Split `container.py` into domain-specific container modules | 2 hours | Maintainability |
| 12 | **MEDIUM** | Security | Fix `_is_production` in encryption service | 15 min | Security |
| 13 | **MEDIUM** | Architecture | Remove infrastructure imports from application layer | 2 hours | Architecture |
| 14 | **MEDIUM** | Security | Move WebSocket auth from query parameter to header | 1 hour | Security |
| 15 | **MEDIUM** | Performance | Add composite indexes for common query patterns | 1 hour | Query performance |
| 16 | **MEDIUM** | Performance | Implement keyset pagination for high-volume endpoints | 1 day | Pagination perf |
| 17 | **MEDIUM** | Code Quality | Remove dead code directories (services/*, scripts, event_bus, etc.) | 30 min | Cleanup |
| 18 | **LOW** | Deployment | Add `.dockerignore` file | 5 min | Build optimization |
| 19 | **LOW** | Performance | Move Redis pool config into settings (not hardcoded) | 15 min | Configurability |
| 20 | **LOW** | Deployment | Add Grafana dashboard JSONs for key metrics | 1 day | Observability |

### Future Roadmap

#### Short-term (1-2 weeks)

1. ✅ CI/CD pipelines for backend
2. ✅ Initial Alembic migration
3. ✅ N+1 query fixes in repositories
4. ✅ Integration tests
5. ✅ API endpoint tests
6. ✅ CORS origin lockdown
7. ✅ Password strength validation

#### Medium-term (2-4 weeks)

8. ✅ Bulk insert optimization
9. ✅ Keyset pagination
10. ✅ Composite database indexes
11. ✅ Split large files
12. ✅ Security fixes (PBKDF2, WebSocket auth, layer violations)
13. ✅ Load test automation in CI
14. ✅ Performance benchmark suite
15. ✅ Prometheus alerting rules
16. ✅ Grafana dashboards

#### Long-term (1-3 months)

17. ✅ Database read replicas + PgBouncer
18. ✅ Redis cluster/sentinel for HA
19. ✅ Multi-AZ Kubernetes deployment
20. ✅ Terraform/Pulumi IaC for cloud resources
21. ✅ Log aggregation (Loki/ELK)
22. ✅ ML-based content moderation for AI safety
23. ✅ Chaos engineering automation in CI
24. ✅ Database Row-Level Security
25. ✅ E2E test suite for full workflows

### Final Assessment

The SFIR Backend is a **well-architected, production-capable platform** built on solid foundations:

- **Hexagonal architecture** with clean domain isolation
- **Strong security posture** with encryption, RBAC, audit logging, and tenant isolation
- **Comprehensive feature set** covering metadata sync, dependency graphs, impact analysis, search, documentation generation, and AI
- **Good test coverage** at the unit level
- **Production deployment artifacts** (Docker, K8s, Helm, runbooks, SLOs)

The primary gaps are **operational infrastructure** (CI/CD, migrations, integration tests) and **database query optimization** (N+1, pagination, bulk operations). These are well-understood, well-scoped, and addressable in a focused 1-2 week sprint.

**Overall Platform Readiness: 7.5/10**

The platform is suitable for staging/early-production use. With the top 10 recommendations addressed, it is suitable for full production deployment at scale.
