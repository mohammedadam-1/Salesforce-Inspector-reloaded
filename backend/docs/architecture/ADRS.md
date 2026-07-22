# SFIR Backend — Architecture Decision Records

## Status: Final

This document catalogs all major architectural decisions made across 21 phases of the SFIR Backend implementation.

---

## ADR-001: Domain-Driven Design with Clean Architecture

**Status**: Accepted | **Phase**: 1-3

**Context**: The platform must handle complex Salesforce metadata hierarchies, multi-tenancy, and evolving business rules.

**Decision**: Adopt Domain-Driven Design (DDD) with hexagonal architecture (ports/adapters). Layers: `domain` (entities, value objects, ports), `application` (use cases), `infrastructure` (adapters), `api` (presentation). Each layer depends only inward.

**Consequences**:
- Clear separation of concerns; business logic is framework-agnostic
- Testable in isolation; domain layer has zero external dependencies
- Higher initial complexity, but significantly lower maintenance cost

---

## ADR-002: PostgreSQL with SQLAlchemy 2.0 Async

**Status**: Accepted | **Phase**: 1

**Context**: Need a relational database for structured metadata, user data, and audit logs. Must support complex queries and migrations.

**Decision**: PostgreSQL 16 as primary database, SQLAlchemy 2.0 async with `asyncpg` driver, Alembic for migrations.

**Consequences**:
- Native async support via `asyncio` extension
- Type-safe queries with ORM and Core APIs
- Mature migration tooling (Alembic)
- Connection pooling via `async_sessionmaker`

---

## ADR-003: Redis for Caching, Queue, and Rate Limiting

**Status**: Accepted | **Phase**: 2

**Context**: Need distributed caching, Celery message broker, and rate limiting state.

**Decision**: Redis 7 for all three concerns, using separate logical databases (0=cache, 1=broker, 2=result backend).

**Consequences**:
- Single infrastructure dependency for multiple concerns
- Atomic operations enable accurate rate limiting
- AOF persistence for cache durability
- Separate DBs prevent key collisions

---

## ADR-004: Celery for Background Jobs

**Status**: Accepted | **Phase**: 3

**Context**: Metadata synchronization, impact analysis, and AI processing are long-running tasks that must not block API requests.

**Decision**: Celery with Redis broker, multiple queues (`default`, `metadata`, `graph`, `ai`), task routing by type.

**Consequences**:
- Async task execution with retry and backoff
- Queue isolation prevents metadata sync from blocking AI queries
- Task result storage enables status polling
- Flower for monitoring (optional)

---

## ADR-005: Pydantic Throughout for Validation

**Status**: Accepted | **Phase**: 1-5

**Context**: Need consistent validation at API boundaries, domain models, and configuration.

**Decision**: Use Pydantic v2 for all data validation: `BaseModel` for domain models, `BaseSettings` for configuration, request/response schemas.

**Consequences**:
- Single validation library across all layers
- Automatic OpenAPI schema generation via FastAPI
- Strict typing with `Field` constraints
- Custom validators for complex business rules

---

## ADR-006: Canonical Metadata Models

**Status**: Accepted | **Phase**: 6

**Context**: Salesforce metadata comes in many formats (XML, JSON, SOAP). Need a unified representation.

**Decision**: Define canonical Pydantic models in `domain/canonical/` that abstract Salesforce-specific formats. Parsers convert raw metadata to canonical form.

**Consequences**:
- Salesforce format changes affect only parsers
- UI and AI layers consume stable canonical models
- Supports multiple source platforms (Salesforce, future)
- Extensible via subclassing `MetadataComponent`

---

## ADR-007: AES-256-GCM Envelope Encryption

**Status**: Accepted | **Phase**: 18

**Context**: Must encrypt sensitive data (Salesforce tokens, API keys) at rest. Need key rotation and versioning.

**Decision**: AES-256-GCM with envelope encryption: data key per record, master key in Vault/AWS/Azure. PBKDF2 for key derivation. Replaced Fernet (AES-128-CBC).

**Consequences**:
- Authenticated encryption prevents tampering
- Key rotation without re-encrypting all data
- Provider abstraction (Dev/Vault/AWS) for environment flexibility
- Slightly higher per-operation cost (~2x)

---

## ADR-008: RBAC with Hierarchical Roles

**Status**: Accepted | **Phase**: 18

**Context**: Need granular permission control across organizations with different access levels.

**Decision**: Hierarchical role model (owner > admin > editor > developer > viewer > readonly). Resources owned by organizations, access validated via `validate_tenant_access`.

**Consequences**:
- Role hierarchy enables intuitive permission inheritance
- Tenant isolation guaranteed at authorization level
- Resource ownership enables fine-grained access
- Cross-tenant access explicitly denied

---

## ADR-009: OpenTelemetry for Observability

**Status**: Accepted | **Phase**: 17

**Context**: Need distributed tracing, metrics, and structured logging for a microservices-like architecture.

**Decision**: OpenTelemetry SDK with OTLP exporter, structlog for structured logging, Prometheus for metrics, Grafana for visualization.

**Consequences**:
- Vendor-neutral observability data
- Automatic instrumentation for FastAPI, SQLAlchemy, httpx
- Correlation IDs across all services
- Single pipeline for traces, metrics, and logs

---

## ADR-010: AI as Explanation Layer Only

**Status**: Accepted | **Phase**: 20

**Context**: AI must never become the source of truth or connect to Salesforce directly.

**Decision**: AI layer is strictly a consumer of deterministic backend services. `SafetyFilter` blocks any request/response referencing direct Salesforce access, metadata parsing, graph building, or impact calculation. All AI responses must cite backend data IDs.

**Consequences**:
- Backend remains the source of truth
- Hallucination risk reduced via citation verification
- Safety violations are logged and blocked at multiple levels
- AI can be replaced without affecting business logic

---

## ADR-011: Multi-Provider AI Abstraction

**Status**: Accepted | **Phase**: 20

**Context**: Need flexibility to use different LLM providers (OpenAI, Anthropic, Gemini, etc.) without code changes.

**Decision**: Abstract `BaseLLMProvider` with concrete implementations registered in `ProviderRegistry`. Runtime provider selection via request parameter.

**Consequences**:
- Providers are interchangeable (swap OpenAI for Anthropic without code changes)
- Cost tracking per-provider with configurable token pricing
- No-op fallback when no provider is configured
- Easy to add new providers (implement one ABC)

---

## ADR-012: FastAPI with Dependency Injection

**Status**: Accepted | **Phase**: 1

**Context**: Need a high-performance async web framework with automatic OpenAPI docs and dependency injection.

**Decision**: FastAPI with Starlette underyling, manual DI container (`Container` in `config/container.py`), `Depends()` for wiring.

**Consequences**:
- Automatic OpenAPI/Swagger documentation
- Async request handling throughout
- Clean DI via container + FastAPI depends
- Pydantic integration for request/response validation

---

## ADR-013: Multi-Stage Distroless Docker Build

**Status**: Accepted | **Phase**: 21

**Context**: Need minimal attack surface and small image size for production deployment.

**Decision**: Three-stage Docker build: base (python:3.13-slim), builder (install deps), runtime (gcr.io/distroless/python3-debian12). uv for dependency management.

**Consequences**:
- ~100MB final image size (vs ~1GB for full Python image)
- No shell, no package manager in runtime image
- Non-root user by default
- Slower build time (mitigated by layer caching)

---

## ADR-014: Kubernetes with Helm for Orchestration

**Status**: Accepted | **Phase**: 21

**Context**: Need production-grade container orchestration with auto-scaling, rolling deployments, and self-healing.

**Decision**: Kubernetes with Kustomize (base + overlays) and Helm chart. HorizontalPodAutoscaler for API. PodDisruptionBudget for availability.

**Consequences**:
- Declarative infrastructure as code
- Auto-scaling based on CPU/memory utilization
- Zero-downtime deployments via rolling update
- Multi-environment support (dev/staging/prod)

---

## ADR-015: Async-First Throughout

**Status**: Accepted | **Phase**: 1

**Context**: The platform handles I/O-heavy operations (database queries, API calls, AI requests) that benefit from non-blocking I/O.

**Decision**: All I/O paths use Python `asyncio`: asyncpg for database, httpx for HTTP, aiofiles for file I/O, async Celery tasks.

**Consequences**:
- Higher throughput under concurrent load
- Lower resource usage per request
- Async complexity (careful with blocking calls)
- uvloop for additional performance in production

---

## ADR-016: Credential and Secret Management via Provider Abstraction

**Status**: Accepted | **Phase**: 18

**Context**: Need to support different secret storage backends across environments (dev file, Vault, AWS Secrets Manager).

**Decision**: Abstract `SecretProvider` with concrete implementations: `DevSecretProvider` (in-memory/env), `VaultSecretProvider` (HashiCorp Vault), `AWSSecretsProvider`. Auto-resolution by environment.

**Consequences**:
- No hardcoded secrets in any environment
- Seamless transition from dev to production
- Audit trail for secret access in Vault/AWS
- Secret rotation supported at provider level

---

## ADR-017: Pagination and RFC 7807 Errors

**Status**: Accepted | **Phase**: 19

**Context**: Need consistent pagination and error handling across all API endpoints.

**Decision**: Standard `PaginationParams` / `PaginatedResponse[T]` for lists. RFC 7807 Problem Details (`ProblemResponse`) for all errors.

**Consequences**:
- Consistent API contract across 30+ endpoints
- Machine-readable error format for clients
- Correlation IDs in all error responses
- Field-level validation errors

---

## ADR-018: WebSocket for Real-Time Updates

**Status**: Accepted | **Phase**: 19

**Context**: Need to push status updates (sync progress, job completion, AI streaming) to connected clients.

**Decision**: FastAPI WebSocket with custom `WebSocketManager`, channel-based pub/sub, token-based auth, 30s heartbeat.

**Consequences**:
- Bi-directional real-time communication
- Channel isolation per feature/organization
- Automatic cleanup on disconnect
- Heartbeat prevents stale connections

---

## Appendix: Technology Stack Summary

| Component | Technology | Version |
|-----------|------------|---------|
| Language | Python | 3.13+ |
| Web Framework | FastAPI | 0.115+ |
| Database | PostgreSQL | 16 |
| Cache/Queue | Redis | 7 |
| ORM | SQLAlchemy | 2.0+ |
| Migrations | Alembic | 1.13+ |
| Validation | Pydantic | 2.9+ |
| Task Queue | Celery | 5.4+ |
| Encryption | cryptography | 43.0+ |
| LLM Providers | openai, anthropic, google-genai | latest |
| Observability | OpenTelemetry, structlog, Prometheus | latest |
| Container | Docker (distroless), Kubernetes | - |
| CI/CD | GitHub Actions | - |
| Auth | python-jose (JWT), passlib (bcrypt) | - |
| Testing | pytest, pytest-asyncio, locust | - |
