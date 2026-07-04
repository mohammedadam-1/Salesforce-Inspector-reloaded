# Phase 2: Backend Folder Structure

This backend is intentionally isolated under `backend/` so the existing Salesforce Inspector Reloaded extension can remain lightweight and independently releasable.

The package uses a `src/` layout to prevent accidental imports from the repository root and to make packaging, testing, and deployment behavior match production.

## Top-Level Layout

```text
backend/
  alembic/
    versions/
  docker/
  docs/
    architecture/
  scripts/
  src/
    sfir_backend/
  tests/
    api/
    fixtures/
      salesforce/
    integration/
    load/
    security/
    unit/
```

## Application Package

```text
backend/src/sfir_backend/
  api/
    dependencies/
    v1/
      routes/
  application/
    dto/
    use_cases/
  config/
  domain/
    entities/
    events/
    policies/
    value_objects/
  infrastructure/
    cache/
    database/
      models/
      repositories/
    llm/
      providers/
    observability/
    queue/
    salesforce/
      clients/
      mappers/
    security/
  repositories/
  schemas/
  services/
    actions/
    ai/
    audit/
    auth/
    dependency_graph/
    deployments/
    metadata/
  utils/
  workers/
    tasks/
```

## Layer Responsibilities

`api/`
: FastAPI routers, request/response wiring, dependency injection adapters, authentication guards, versioned HTTP contracts, OpenAPI tagging, and HTTP error mapping.

`application/`
: Use cases that coordinate domain services and repositories. This layer owns business workflows such as starting metadata syncs, asking metadata questions, creating action plans, approving deployments, and tracking job progress.

`domain/`
: Pure business concepts with no FastAPI, SQLAlchemy, Redis, Celery, or Salesforce SDK coupling. This layer contains entities, value objects, domain events, and policies such as action safety rules and risk classification.

`services/`
: Business services grouped by product capability. These services implement metadata indexing, dependency analysis, AI orchestration, safe actions, deployments, audit logging, and auth workflows. Services depend on repository interfaces and infrastructure adapters through explicit boundaries.

`repositories/`
: Repository interfaces and shared repository contracts. Concrete SQLAlchemy implementations live under `infrastructure/database/repositories/`.

`infrastructure/`
: External systems and framework-specific implementations: PostgreSQL models, SQLAlchemy repositories, Redis cache, Celery queue integration, Salesforce API clients, LLM providers, encryption, metrics, tracing, and structured logging.

`schemas/`
: Pydantic v2 API schemas and validation models. These are transport-facing models, not database models and not domain entities.

`workers/`
: Celery application setup and task entry points. Worker tasks should be thin orchestration wrappers that call application use cases.

`config/`
: Typed settings, environment configuration, feature flags, and deployment profiles. No secrets are hardcoded here.

`utils/`
: Small cross-cutting utilities that do not belong to business logic. Anything substantial should graduate into a service or infrastructure adapter.

## Dependency Direction

The intended dependency direction is:

```text
api -> application -> domain
api -> schemas
application -> services
services -> repositories interfaces
infrastructure -> repositories interfaces
infrastructure -> external systems
workers -> application
```

Domain code must not import FastAPI, SQLAlchemy, Celery, Redis, Salesforce clients, or LLM providers.

Infrastructure code may depend outward on external libraries, but application and domain logic should remain portable and testable.

## Why This Structure

- Keeps the extension and backend cleanly separated.
- Supports a commercial multi-org SaaS backend without forcing browser-extension assumptions into the server.
- Makes AI providers replaceable by keeping provider code under `infrastructure/llm/providers/`.
- Makes Salesforce API support replaceable/testable through `infrastructure/salesforce/clients/`.
- Keeps long-running processing explicit under `workers/`.
- Keeps database migrations and ORM models separated from domain entities.
- Allows Phase 3 database work to proceed without rewriting API or domain boundaries.

## Phase Boundary

This phase defines structure only. No database models, authentication logic, Salesforce clients, AI providers, workers, or API handlers are implemented here. Those belong to later approved phases.
