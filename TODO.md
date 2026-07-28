# Architecture Fix Implementation Plan

## Priority 1 — Connection Manager & Connection Pool
- [x] Create `infrastructure/salesforce/connection_manager.py` — `ConnectionManager` with ConnectionPool, per-tenant caching, token refresh, health check, disconnect flow
- [x] Add per-tenant `SalesforceClient` factory
- [x] Add connection pool with max connections per org
- [x] Add token expiry auto-refresh on 401 in connection lifecycle
- [x] Add instance URL validation and health check

## Priority 2 — Normalized Metadata Database Tables
- [x] Create `infrastructure/persistence/models/metadata_components.py` — SQLAlchemy models for all normalized metadata types
- [ ] Create Alembic migration for metadata component tables
- [ ] Create domain entities for all normalized models
- [ ] Create repositories for all normalized models

## Priority 3 — Missing Metadata Collectors
- [ ] Add to `sync/downloader.py`:
  - [ ] `get_apex_pages()` — Visualforce page collection via Tooling API
  - [ ] `get_lightning_components()` — LWC bundle collection
  - [ ] `get_aura_components()` — Aura definition bundle collection
  - [ ] `get_formula_fields()` — Formula expression extraction
  - [ ] `get_process_builder()` — ProcessDefinition/ProcessInstance collection
  - [ ] `get_named_credentials()` — NamedCredential collection
  - [ ] `get_connected_apps()` — ConnectedApp collection
  - [ ] `get_custom_metadata_types()` — CustomMetadataType collection
  - [ ] `get_custom_metadata_records()` — CustomMetadata record collection
  - [ ] `get_static_resources()` — StaticResource list collection
  - [ ] `get_experience_cloud_sites()` — Site/Network collection
- [ ] Create mapper strategies for new collector types
- [ ] Register in `KNOWN_METADATA_TYPES`

## Priority 4 — Metadata SOAP API + Composite API + Bulk API
- [ ] Create `infrastructure/salesforce/soap_client.py` — SOAP-based Metadata API client
  - [ ] `retrieve()` — Retrieve metadata XML
  - [ ] `listMetadata()` — List metadata components
  - [ ] `describeMetadata()` — Describe metadata types
- [ ] Create `infrastructure/salesforce/composite_client.py` — Composite API client
  - [ ] `composite()` — Batch REST requests
  - [ ] `sObjectTree()` — Hierarchical create
- [ ] Create `infrastructure/salesforce/bulk_client.py` — Bulk API 2.0 client
  - [ ] `create_job()` — Create bulk ingestion job
  - [ ] `upload_data()` — Upload CSV data
  - [ ] `query()` — Bulk query for large datasets

## Priority 5 — Rate Limiting Implementation
- [ ] Create `infrastructure/rate_limiter/` module:
  - [ ] `redis_rate_limiter.py` — Sliding window rate limiter with Redis
  - [ ] `middleware.py` — Rate limiting FastAPI middleware
  - [ ] Per-endpoint rate limits (AI, operations, general API)

## Priority 6 — SSO/SAML Authentication
- [ ] Create `infrastructure/security/sso/` module:
  - [ ] `saml_service.py` — SAML 2.0 SP integration
  - [ ] `saml_routes.py` — ACS, metadata endpoints
  - [ ] `oauth_service.py` — OAuth 2.0/OIDC provider integration

## Priority 7 — API Key Authentication
- [ ] Create `infrastructure/security/api_key_auth.py`:
  - [ ] API key generation with hashing
  - [ ] API key verification middleware
  - [ ] API key CRUD endpoints
  - [ ] Per-key permission scoping

## Priority 8 — Vault Secrets Integration
- [ ] Implement actual HashiCorp Vault integration:
  - [ ] `infrastructure/vault/vault_client.py` — HVAC-based Vault client
  - [ ] Token encryption key rotation from Vault
  - [ ] Salesforce client credentials from Vault
  - [ ] Database credentials from Vault

## Priority 9 — Health Check Dependencies
- [ ] Enhance health check endpoint:
  - [ ] Database connectivity check
  - [ ] Redis connectivity check
  - [ ] Celery worker availability check
  - [ ] Salesforce connection health check
  - [ ] External dependency status

## Priority 10 — Graph Persistence to Database
- [ ] Create graph persistence layer:
  - [ ] `infrastructure/persistence/models/graph.py` — Graph node + edge tables
  - [ ] GraphRepository for save/load graph snapshots
  - [ ] GraphStage integration to persist after build

## Priority 11 — Search Document Persistence
- [ ] Create search persistence layer:
  - [ ] `infrastructure/persistence/models/search.py` — Search document table
  - [ ] SearchDocumentRepository
  - [ ] SearchStage integration to persist documents

## Priority 12 — Dead Letter Queue for Sync Retries
- [ ] Implement DLQ for failed sync items:
  - [ ] `sync_retry_dlq` table
  - [ ] Automatic escalation after max retries
  - [ ] DLQ monitoring endpoints

## Priority 13 — Observability Enhancements
- [ ] Add structured logging for all missing paths
- [ ] Add Prometheus metrics for sync jobs, connections, API calls
- [ ] Add distributed tracing spans for pipeline stages
- [ ] Add audit logging for all security-critical operations

## Priority 14 — Tenant Isolation Enforcement
- [ ] Add repository-level tenant filters
- [ ] Add middleware-level tenant context validation
- [ ] Add per-tenant cache key namespacing
- [ ] Add cross-org access prevention in all queries
