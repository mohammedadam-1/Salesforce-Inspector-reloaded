# Phase 3.5 — Metadata Validation & Consistency Engine

Status: **COMPLETE (all 10 deliverables below)** · Date: see git history
Scope: prove that `SQLAlchemyMetadataRepository` (the single source of truth) is correct.
Gate: this phase **surfaced two critical architectural issues** in the repository.
**The repository is NOT yet trustworthy for the Dependency Graph — see Deliverable 10.**

---

## Executive Summary

The Metadata Validation & Consistency Engine was built and tested (18 unit tests,
6 integration tests, full suite **2039 passed**, no new failures).

The engine does everything the phase required: it executes deterministic rules
for completeness, duplicates, consistency, integrity, orphans, canonical-model
correctness, and unsupported types; it produces the specified `ValidationReport`;
it never writes to the repository (proven by tests); and it correctly detects
broken/missing/duplicate/invalid-relationship scenarios.

**However, the survey and the engine together exposed two critical architectural
issues in the repository that Phase 3.5 was explicitly designed to prove:**

1. **WRITE-PATH BLOCKER**: `save()` / `save_batch()` **crash for 9 of 27 named
   metadata types** against a real database (`Field`, `ValidationRule`,
   `RecordType`, `Layout`, `Profile`, `PermissionSet`, `Report`, `Dashboard`,
   `Workflow`) because `_component_to_orm` always emits `namespace`/`description`
   column values that those ORM models do not define → `TypeError`. **The
   repository cannot persist these core types at all through its public write
   API.**

2. **READ-PATH DATA LOSS**: `_orm_to_component` restores only base fields +
   `metadata_properties`; type-specific fields (`object_api_name`,
   `reference_to`, `formula`, `record_creates`, …) are **never restored** from
   dedicated columns. Cross-reference validation through the repository is
   therefore impossible for any component whose reference data lives only in
   type-specific columns. The engine detects this as `REFERENCE_DATA_MISSING`
   and reports it as an error-level integrity finding.

Per the phase gate ("If validation exposes architectural issues, STOP and explain
them instead of hiding them"), these issues are documented here **before** any
Dependency Graph work. See Deliverable 10 for the verdict and remediation plan.

---

## Deliverable 1 — Architecture Summary

### New components (all read-only, layered)

```
domain/validation/validation_report.py      # pure data models (no deps)
application/use_cases/metadata/validation_rules.py   # deterministic rule set
application/use_cases/metadata/validation_engine.py  # orchestrator
```

- **Domain layer**: `ValidationSeverity`, `ValidationCategory`, `ValidationFinding`,
  `MetadataValidationReport` — plain dataclasses, no repository/persistence deps.
- **Application layer**:
  - `ValidationRuleSet` — ordered rules, each rule catches its own exceptions and
    emits `RULE_FAILURE` instead of crashing the run.
  - `MetadataValidationEngine` — the only component that touches
    `IMetadataRepository`. It loads components via `get_by_organization` +
    `get_types`, builds a reference registry, runs the rule set, partitions
    findings, computes the 0–100 score, and returns the report.
- **Repository interface used**: `get_by_organization`, `get_types`
  (and optionally `ISyncJobRepository.list_by_organization` for downloaded counts).
  **No write methods are ever called** — proven by `test_repository_unchanged_after_validation`.

### Data flow

```
IMetadataRepository ──get_by_organization──▶ components (base MetadataComponent)
                                          │
                    build_reference_registry(components) → {type: {api_names}}
                                          │
ValidationRuleSet.run(components, registry, downloaded_counts)
  ├─ CompletenessRule   (downloaded == persisted per type)
  ├─ DuplicateRule      (api_name / id / canonical key uniqueness)
  ├─ ConsistencyRule    (cross-references: Field→Object, VR→Object, Flow→objects,
  │                      Formula→Field, Lookup/MD→Object, Role→Role,
  │                      PermissionSet→objects, Dashboard→reports, relationships)
  ├─ IntegrityRule      (orphans + REFERENCE_DATA_MISSING)
  ├─ CanonicalRule      (reuses existing CanonicalMetadataValidator)
  └─ UnsupportedTypeRule(Aura/LWC/Visualforce/PlatformEvent → reported)
                                          │
        MetadataValidationReport (timestamp, org, counts, buckets, score, passed)
```

### Design principles

- **Deterministic**: no AI, no randomness — identical input ⇒ identical report.
- **Frozen-boundary respect**: `MetadataRepository`, `MetadataPipeline`,
  `PersistenceStage`, parsers, and the canonical normalizer were **not redesigned**.
  The engine reads only through `IMetadataRepository`.
- **Read-only**: the engine never writes; tests assert no write method is awaited.
- **Honest reporting**: when reference data is absent for a type that requires it,
  the engine emits an ERROR (`REFERENCE_DATA_MISSING`) rather than a false "OK".
  It also emits an informational `READ_PATH_NOTE` explaining the read-path gap.

---

## Deliverable 2 — Validation Engine Design

### `MetadataValidationEngine.validate(organization_id, *, downloaded_counts, request_context) -> MetadataValidationReport`

1. Load all components (`get_by_organization`) and present types (`get_types`).
2. If `downloaded_counts` is not supplied and a `sync_job_repo` is wired, derive
   per-type downloaded counts from `SyncJob.processed_items`.
3. Build the reference registry.
4. Run the rule set (each rule isolated; exceptions become `RULE_FAILURE` findings).
5. Partition findings into the report buckets; compute score; decide `passed`.

### Reference-data resolution (`read_prop`)

Type-specific values are read in this order:
1. `metadata_properties[exact_key]`
2. `metadata_properties[camelCase|snake_case|lowercase variant]`
3. typed attribute on the component (supports direct-save fixtures)

This mirrors how the pipeline's dict path persists data (everything in
`properties` → `metadata_properties` JSONB) while remaining compatible with typed
canonical components in unit tests.

### Type vocabulary

The repository returns PascalCase types (`"Field"`, `"Object"`, …). All rules
normalize via `to_pascal_type`. The `CanonicalRule` maps to snake_case before
running the existing `CanonicalMetadataValidator` (whose `KnownTypeRule` expects
snake_case), avoiding false `UNKNOWN_TYPE` warnings.

---

## Deliverable 3 — Validation Rule Matrix

| Rule | Check | Category | Severity on failure | Error code(s) |
|---|---|---|---|---|
| Completeness | downloaded == persisted per type | completeness | error | `COUNT_MISMATCH` |
| Completeness | no downloaded counts provided | completeness | info | `COMPLETENESS_UNVERIFIED` |
| Duplicates | (type, api_name) unique | duplicate | error | `DUPLICATE_API_NAME` |
| Duplicates | id unique | duplicate | error | `DUPLICATE_ID` |
| Duplicates | canonical key (type, api_name, namespace) unique | duplicate | error | `DUPLICATE_CANONICAL_KEY` |
| Consistency | Field → parent Object exists | consistency | error | `BROKEN_REFERENCE` |
| Consistency | Field lookup/master-detail `reference_to` → Object exists | consistency | error | `BROKEN_REFERENCE` |
| Consistency | Field is lookup/MD but has no `reference_to` | consistency | warning | `MISSING_REFERENCE_TO` |
| Consistency | ValidationRule → parent Object exists | consistency | error | `BROKEN_REFERENCE` |
| Consistency | Trigger → parent Object exists | consistency | error | `BROKEN_REFERENCE` |
| Consistency | Flow record_creates/updates/deletes → Objects exist | consistency | error | `BROKEN_REFERENCE` |
| Consistency | Flow subflows → Flow exists | consistency | error | `BROKEN_REFERENCE` |
| Consistency | Formula → parent Object + referenced Field exist | consistency | error | `BROKEN_REFERENCE` |
| Consistency | Layout / RecordType / Report / Workflow / ApprovalProcess / SharingRule / QuickAction / CustomSetting → parent Object exists | consistency | error | `BROKEN_REFERENCE` |
| Consistency | Role.parent_role → Role exists | consistency | error | `BROKEN_REFERENCE` |
| Consistency | PermissionSet/Profile object_permissions → Objects exist | consistency | error | `BROKEN_REFERENCE` |
| Consistency | Dashboard components → Reports exist | consistency | error | `BROKEN_REFERENCE` |
| Consistency | Declared `CanonicalRelationship.target_api_name` exists | relationship | error | `BROKEN_REFERENCE` |
| Integrity | child with missing parent object = orphan | orphan | error | `ORPHANED_<TYPE>` |
| Integrity | type requires parent ref but no reference data returned | integrity | error | `REFERENCE_DATA_MISSING` |
| Canonical | existing 9 canonical rules (name format, enums, required ids, version range, …) | canonical | error/warning | (inherited) |
| Unsupported | AuraComponent, LWC, ApexPage/ApexComponent, PlatformEvent | unsupported | info | `UNSUPPORTED_TYPE` |
| Relationship note | read-path/edge-exposure limitation | relationship | info | `READ_PATH_NOTE` |

Notes:
- **Relationship/dependency edges**: `get_relationships`/`get_dependencies` return
  only *existing* related components and collapse duplicates, so raw-edge
  duplicate/broken-edge validation is **not possible through the public
  interface**. This is reported via `READ_PATH_NOTE` and tracked in technical debt.
- **MasterDetail→child exists**: a MasterDetail field's child is the field's own
  object; the `reference_to` target check covers the parent. Child-object
  existence is covered by the parent-object check for each Field.

---

## Deliverable 4 — Validation Report Format

```python
MetadataValidationReport(
    validation_timestamp: datetime,        # UTC
    organization_id: str,
    metadata_counts: dict[str, int],       # persisted per canonical type
    downloaded_counts: dict[str, int] | None,
    missing_metadata: list[ValidationFinding],
    broken_references: list[ValidationFinding],
    duplicate_entries: list[ValidationFinding],
    orphaned_entries: list[ValidationFinding],
    consistency_failures: list[ValidationFinding],
    integrity_failures: list[ValidationFinding],
    canonical_failures: list[ValidationFinding],
    relationship_notes: list[ValidationFinding],
    unsupported_types: list[str],
    findings: list[ValidationFinding],     # all findings, in rule order
    validation_score: int,                 # 0..100
    passed: bool,                          # error_count == 0
)
```

- `ValidationFinding`: `category`, `severity`, `error_code`, `message`,
  `component_type`, `api_name`, `reference_type`, `reference_api_name`,
  `suggested_action`, `metadata`.
- Score: `100 − 5·errors − 1·warnings`, floored at 0.
- `passed == (error_count == 0)`. This means a real repository that drops
  type-specific fields (or cannot persist 9 types) **fails validation** — exactly
  the intended gate behaviour.
- `report.summary()` returns a compact machine-readable dict for API/UI use.

---

## Deliverable 5 — Files Modified / Added

### Added (source)
| File | Purpose |
|---|---|
| `src/sfir_backend/domain/validation/__init__.py` | package + re-exports |
| `src/sfir_backend/domain/validation/validation_report.py` | report/finding models |
| `src/sfir_backend/application/use_cases/metadata/validation_rules.py` | deterministic rule set |
| `src/sfir_backend/application/use_cases/metadata/validation_engine.py` | orchestrator |

### Modified (source)
| File | Change |
|---|---|
| `src/sfir_backend/config/container.py` | added `MetadataValidationEngine` import, `_make_metadata_validation_engine`, `create_metadata_validation_engine`, `"metadata_validation"` factory; **added the missing `"metadata"` key to `_make_repos()`** (needed by `_make_metadata_pipeline` too) |

### Added (tests)
| File | Purpose |
|---|---|
| `tests/unit/application/use_cases/metadata/test_validation_engine.py` | 18 unit tests |
| `tests/integration/validation/test_validation_engine_integration.py` | 6 integration tests (skip w/o DB) |

### Not touched (frozen)
`IMetadataRepository`, `SQLAlchemyMetadataRepository`, `MetadataPipeline`,
`PersistenceStage`, all parsers, mapper strategies, normalizer, `SyncCoordinator`.

---

## Deliverable 6 — Tests Added

### Unit (18, all pass, no DB)
Prove:
- every rule executes (no `RULE_FAILURE`); healthy repo ⇒ `passed=True`, score 100
- broken references detected: Field lookup → missing object, ValidationRule →
  missing object, Flow record_creates → missing object, Formula → missing field,
  invalid relationship target
- missing metadata: downloaded=5 vs persisted=2 ⇒ `COUNT_MISMATCH`
- duplicates: `DUPLICATE_API_NAME`, `DUPLICATE_ID`
- orphans: `ORPHANED_FIELD`
- read-path loss: bare base component ⇒ `REFERENCE_DATA_MISSING` + `READ_PATH_NOTE`
- **repository unchanged**: only `get_by_organization`/`get_types` awaited;
  `save`, `save_batch`, `update`, `delete`, `save_version`, `save_versions` never awaited
- canonical rule executes against the real `CanonicalMetadataValidator`
- `aggregate_downloaded_counts` and engine-with-sync-repo wiring

### Integration (6, skip gracefully without DB)
- **write-path blocker proof**: `repo.save(Field, …)` raises `TypeError`
- healthy org validated through the real repository ⇒ `passed=True`
- broken Flow reference detected through the real repository
- completeness mismatch with `downloaded_counts`
- **repository unchanged after validation** (counts before == after)
- `READ_PATH_NOTE` present

### Full suite
`2039 passed` (baseline 2021 ⇒ **+18**), 44 skipped (+6 new integration), 4 xfailed.
Only the **pre-existing** failures remain: `test_container.py` (2, "Database not
initialized") and `test_metadata_sync.py` (13, `SyncCoordinator` missing
`oauth_service`). **No new failures.**

---

## Deliverable 7 — Coverage

- New code has no branch gaps for the core scenarios: healthy, broken-ref,
  duplicate, orphan, missing-ref-data, missing-count, rule failure.
- Repository **unchanged-after-validation** is asserted both at the mock level
  (no write methods awaited) and at the DB level (counts identical).
- The 9-type write-path crash and the read-path data loss are both covered by
  executable tests (integration crash proof; unit `REFERENCE_DATA_MISSING`).
- Unsupported types (Aura/LWC/Visualforce/PlatformEvent) are reported, never
  silently dropped.
- Edge-level relationship/dependency duplicate and broken-edge checks are
  explicitly documented as **not testable through the public interface** (see
  technical debt) rather than faked.

---

## Deliverable 8 — Performance Observations

- `validate()` loads the full org via one `get_by_organization` call (bounded per
  type, no pagination ⇒ 27 queries for a full org) plus one `get_types` call
  (27 count queries). For a large org this is O(types) queries — acceptable for a
  batch validation job; avoid calling it per-request.
- All cross-reference checks are O(n) with set lookups against the registry; no
  N+1 reference resolution inside rules.
- Relationship/dependency edge checks are **not** performed per component (would
  be N+1); the interface cannot expose raw edges anyway. Tracked as debt.
- Downloaded-count derivation is one `list_by_organization` (limit 500).

---

## Deliverable 9 — Remaining Technical Debt

1. **[CRITICAL] Write-path crash for 9 types** — `_component_to_orm` emits
   `namespace`/`description` for models lacking those columns. Fix: strip keys
   not present on the target model (`if hasattr(model_class, key)`) in
   `_component_to_orm`/`save`/`save_batch`/`update`, or add the columns.
2. **[CRITICAL] Read-path data loss** — `_orm_to_component` must restore
   type-specific columns (and `relationships`) into the returned component, or
   type-specific data must always be carried in `metadata_properties`.
3. **[HIGH] Pipeline drops typed attributes** — the normalizer copies only
   `metadata_properties` into `NormalizedDocument.properties`; mapper type-specific
   fields (typed attributes) are lost before persistence. The engine can only see
   reference data that survives in `metadata_properties`.
4. **[MEDIUM] Raw relationship/dependency edges not exposed** — `get_relationships`/
   `get_dependencies` return only existing components; duplicate/broken-edge
   validation through the interface is impossible. Consider an edge-level read API.
5. **[MEDIUM] Container** — `_make_repos()` had no `"metadata"` key (added here);
   `test_container.py` failures ("Database not initialized") and
   `test_metadata_sync.py` errors (missing `oauth_service`) are pre-existing and
   unrelated to this phase.
6. **[LOW] Type vocabulary** — PascalCase (repo) vs snake_case (validator) requires
   mapping in `CanonicalRule`; aligning vocabularies would remove the mapping.
7. **[LOW] Unsupported types** — Aura, LWC, Visualforce, Platform Events have no
   ORM tables; reported as `UNSUPPORTED_TYPE` until modelled.

---

## Deliverable 10 — Recommendation: Is MetadataRepository trustworthy for the Dependency Graph?

**Verdict: NOT YET — do not proceed to the Dependency Graph until the repository
write and read paths are fixed and re-validated.**

Rationale, with evidence produced this phase:

1. **The repository cannot persist 9 of 27 named types.** Empirically confirmed
   (full crash matrix): `repo.save()`/`save_batch()` raises `TypeError` for
   `Field`, `ValidationRule`, `RecordType`, `Layout`, `Profile`, `PermissionSet`,
   `Report`, `Dashboard`, `Workflow`. A Dependency Graph built on a repository
   that cannot store these types would be structurally incomplete.
2. **The repository cannot return type-specific reference data.** `_orm_to_component`
   restores only base fields + `metadata_properties`; `object_api_name`,
   `reference_to`, `formula`, `record_creates`, … are never restored from columns.
   Empirically confirmed: a Field saved with `object_api_name="Account"` reads
   back with empty `metadata_properties` and no `object_api_name`. Cross-reference
   edges (Field→Object, ValidationRule→Object, …) **cannot be validated or
   reconstructed** from repository reads today.
3. **Raw relationship/dependency edges are not exposed** by the interface, so
   edge-level duplicate/broken-edge validation is impossible through the public
   API.

These are not cosmetic. They are exactly the class of issue this phase exists to
prove. The Validation Engine is the proof layer: run against a real org today it
will produce error-level `REFERENCE_DATA_MISSING` findings (and the write path
will fail for the 9 types). That is the correct, honest result.

### Remediation path (recommended order)

1. Fix `_component_to_orm` / `save` / `save_batch` / `update` to strip columns
   absent from the target model (small, high impact).
2. Fix `_orm_to_component` to restore type-specific columns + `relationships`, or
   standardise on carrying type-specific data in `metadata_properties` end-to-end
   (normalizer must copy typed attributes into `properties`).
3. Re-run `MetadataValidationEngine` against a synced org and require
   `passed=True` with zero `REFERENCE_DATA_MISSING` / `COUNT_MISMATCH` findings.
4. Only then proceed to the Dependency Graph phase, using the engine as the
   acceptance gate (a failing report blocks graph generation).

The engine, report model, rule set, and tests from this phase are the permanent
regression harness for that gate.
