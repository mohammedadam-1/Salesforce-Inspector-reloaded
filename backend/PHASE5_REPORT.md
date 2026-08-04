# Phase 5 — Real Salesforce Metadata Ingestion Validation Report

Date: 2026-08-03 | Scope: ingest path only (UI/AI/API-contract frozen)

## 1. Ingestion Pipeline Audit (call chain)
Verified end-to-end wiring in `config/container.py`:
- `POST /api/v1/sync/start` (`api/v1/routes/metadata_sync.py:28`) → `SyncCoordinator.start_sync` (creates `SyncJob`) → (was: queued only) → now dispatches Celery task.
- Celery tasks (`workers/tasks/metadata_sync.py`): `metadata.incremental_sync` / `metadata.full_sync` / `metadata.detect_stale` → `_execute_sync` → `SyncCoordinator.execute_sync` (`application/use_cases/metadata_sync.py:176`).
- `execute_sync`: Redis distributed lock → token decrypt → `SalesforceClient` → `MetadataDownloadManager` (real Tooling API) → manifest + change detection → `MetadataPipeline` (7 stages incl. PersistenceStage, GraphStage, SearchStage) → version/history/statistics writes.

## 2. OAuth Verification
- Real web-server Authorization Code + PKCE only: authorize URL `{login_url}/services/oauth2/authorize` (oauth.py:61-77), token POST `{login_url}/services/oauth2/token` (oauth.py:79-113, confidential client).
- Login URL per environment (`value_objects/salesforce.py:37-45`): login.salesforce.com (prod) / test.salesforce.com (sandbox).
- Refresh path exercised live: encrypted placeholder refresh token → `refresh_access_token` POSTed to https://na1.salesforce.com/services/oauth2/token → Salesforce rejected the fake token.

## 3. Real Salesforce Calls
Proven with live outbound HTTP: every metadata type query against na1.salesforce.com returned Salesforce's own 401 response `Token expired or invalid` (token is a placeholder — no real user OAuth exists in this environment). No mock downloader exists; `downloader.py` performs real `/tooling/sobjects` queries.

## 4. Normalization Verification
Pipeline stages wired in both container factory paths (`_make_sync_coordinator` container.py:651, `create_sync_coordinator` container.py:680): MetadataDownloadManager + MetadataHashCalculator + MetadataChangeDetector + ManifestGenerator + MetadataPipeline (PersistenceStage → GraphStage → SearchStage). Full normalization of real payloads cannot be demonstrated without real credentials; structure verified by code audit + unit coverage.

## 5. Database Verification
- Migration 002 head, 16 tables, both GIN pg_trgm indexes present, pg_trgm installed, `alembic current = 002`.
- Writes verified against real PostgreSQL (see #8).

## 6. Data Quality Findings
- DB contained placeholder seed data: `org_id=00D8E000000ABCD`, `username=admin@mycompany.com`, encrypted tokens literally `enc`, synthetic versions (`RecordType_N`, hash `hRecordTypeN`), QA-stamped sync jobs. Source: `backend/try_sf_auth.py`.
- Token primed to a validly-encrypted placeholder (192-char ciphertext) so the full path past decryption could be exercised.
- Defect found & fixed: total download failure previously mass-marked the whole manifest DELETED (probe inflated metadata_versions 497 → 994). Guard added: if every metadata type query fails, sync aborts with `All metadata type queries failed; aborting sync to avoid false deletion of the existing manifest` instead of deleting.

## 7. Multi-Tenancy Verification
- Only 1 (fake) connection + 19 orgs in DB; second real org unavailable → cannot demonstrate cross-tenant isolation with real data.
- Tenant scoping verified in repos (`organization_id` filters everywhere).
- Defect found & fixed: `ISalesforceConnectionRepository` lacked a global `list_active()`; added to interface + SQLAlchemy impl + test fakes.

## 8. Persistence Verification (defects fixed)
Core defect found: sync-layer repositories (SyncJob, SyncHistory, MetadataVersion, SyncRetryQueue, SyncStatistics, SalesforceConnection, SQLAlchemyMetadataRepository) were flush-only — sessions closed without commit → NOTHING persisted (empirically proven: probe jobs vanished on rollback). Fixed by adding `session.commit()` mirroring the existing sibling-repo convention (audit_log/org/refresh_token). Verified against real PostgreSQL:
- Sync job now persists: `8faf3f92…` failed job row present with correct error.
- Sync history row persisted (0 → 1).
- metadata_versions written during sync (probe runs), then cleaned back to baseline 497.
- 41 real-DB persistence integration tests pass (round-trips all metadata types).
- `Container.get_repository()` was a dead API (`self._repositories` never populated) — now lazily built (container.py:1054).

## 9. Defects Fixed (summary)
1. Flush-only sync repos → commits added (persistence was broken end-to-end).
2. `/sync/start` never dispatched a worker task → now dispatches full/incremental task with args + `metadata` queue.
3. Celery beat schedule had tasks with NO args (TypeError at runtime) → rewired to new dispatchers `metadata.dispatch_scheduled_syncs` / `metadata.dispatch_stale_detection` (scheduler.py).
4. Celery worker/beat containers lacked Salesforce client creds env → added to docker-compose.
5. `uuid.UUID(job.id)` crashed on asyncpg UUID objects in task path → `uuid.UUID(str(...))` fix.
6. `list_active()` missing from connection repository (dispatcher prerequisite) → added.
7. Mass-delete-on-total-download-failure → abort guard.
8. `get_repository` dead API → lazy repo build.
Test-infra fixes (pre-existing breakage): missing `oauth_service` in SyncCoordinator test fixture (13 tests), integration fixture inserted org without owner user (92 errors).

## 10. Validation Execution
- Compile: all changed modules OK.
- Unit + API tests: 2172 passed, 2 failed (pre-existing env-dependent container tests needing a live DB at localhost:5432; fail identically on pristine tree).
- Real sync probe (`scripts/phase5_real_sync_probe.py`): full path executed — job created → loaded → lock acquired → token decrypted → live HTTPS to na1.salesforce.com → 401 rejected → job failed with guard message → job + history persisted to PostgreSQL.
- Route dispatch tests: full → `full_sync_task.apply_async([org, conn], queue="metadata")`, incremental → `incremental_sync_task` (2 passed).
- Probe artifacts cleaned; DB restored to baseline (3 seed jobs, 497 versions).

## VERDICT: NO-GO (blocked, not broken)
The ingest path is proven end-to-end up to the Salesforce HTTP boundary: real outbound calls, clean error handling, and now real persistence (jobs, history, versions survive restart). Remaining blocker is environmental: the only connection in the DB is placeholder seed data (`admin@mycompany.com`, fake org id). A PASS requires a real Salesforce Connected App + completed OAuth for a real org, then a full sync run showing real components flowing into `metadata_objects` / `metadata_fields` / `metadata_versions` / `search_documents` / `metadata_dependencies`.
