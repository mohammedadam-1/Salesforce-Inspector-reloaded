# Phase 3.1 — Metadata Intelligence Engine: Architecture Audit & Single-Architecture Recommendation

**Status:** AUDIT ONLY — ZERO production code changes made.
**Scope:** Backend metadata pipeline, parsers, graph, persistence, repositories, search, sync.
**Date:** Phase 3.1 (understanding, not implementation).

---

## Executive Summary

The codebase currently contains **two complete parser frameworks**, **two graph-building
frameworks**, and **three metadata model layers** running in parallel. One parser framework
(narrow, 5 types) is wired into production and has **zero tests**; the other (broad, 29 types)
is fully built, fully tested, and **zero-wired**. The graph engine is wired but its dependency
scoring is silently disconnected from search. The persistence layer writes to a generic JSON
version table while 16 dedicated ORM tables exist and are only reachable through a new,
in-progress, unwired repository.

**The recommendation of this audit:** adopt the **Broad Parser Framework
(`infrastructure/parsers/`) + the Graph Engine (`infrastructure/graph/`) + the dedicated ORM
tables via the new `IMetadataRepository`** as the single production architecture, and retire
the narrow runtime parser path. **GO for Phase 3.2** is conditional on the wiring work
described in Output 9.

---

## Output 1 — Current Metadata Architecture

### Layers present today (all exist simultaneously)

```
Salesforce Org
   │  REST / Tooling / SOQL
   ▼
MetadataDownloadManager (infrastructure/salesforce/sync/downloader.py)
   │  223 KNOWN_METADATA_TYPES enumerated (domain/value_objects/metadata.py)
   ▼
SyncCoordinator (application/use_cases/metadata_sync.py)
   │  FULL / INCREMENTAL / METADATA_TYPE / ... → batches by type
   ▼
MetadataPipeline (application/pipeline/metadata_pipeline.py)
   ├─ ParserStage          → infrastructure/salesforce/parsers/  (NARROW, 5 parsers + Generic fallback)
   ├─ CanonicalMappingStage→ application/pipeline/mapper/strategies/ (19 strategies)
   ├─ ValidationStage      → canonical validator (9 rules)
   ├─ NormalizationStage   → canonical normalizer (8 rules) → NormalizedDocument
   ├─ PersistenceStage     → metadata_versions (generic JSONB) via IMetadataVersionRepository
   ├─ GraphStage           → infrastructure/graph/ DependencyGraphEngine (BROAD engine)
   └─ SearchStage          → SearchEngine (index_components with graph_engine=None)
```

### Three metadata model layers

| Layer | Location | Models | Producer |
|---|---|---|---|
| **Legacy parsed models** | `domain/metadata/` | ApexClass, ApexTrigger, CustomObject, CustomField, Layout, ValidationRule, Flow, Profile, PermissionSet, Report, Dashboard, Role, Queue, SharingRule, EmailTemplate, StaticResource, etc. | Narrow parsers |
| **Canonical models** | `domain/canonical/` | ~29 `Metadata*` components + base `MetadataComponent` | Broad parsers **directly** OR mapper strategies (from legacy models) |
| **Normalized docs** | `application/pipeline/normalizer/normalized_model.py` | `NormalizedDocument` (search/persistence shape) | NormalizationStage |

### The two parser frameworks

| | **System A — narrow, WIRED** | **System B — broad, UNWIRED** |
|---|---|---|
| Location | `infrastructure/salesforce/parsers/` | `infrastructure/parsers/` |
| Parsers | ApexClass, ApexTrigger, CustomObject, Layout, ValidationRule (+ Generic passthrough) | 29 parsers across 12 modules (access, code, core, custom, flows, integration, layouts, permissions, reporting, ui, validation_rules, workflows) |
| Output | `ParsingResult[domain.metadata.X]` (legacy models) | `ParseResult` with canonical `MetadataComponent` + `references` + `relationships` + warnings/errors/metrics |
| Extras | `parse_body()` XML→dict helper | `ParserEngine`, `ValidationEngine`, `NormalizationEngine`, `ReferenceExtractor`, `RelationshipExtractor`, `ParserMetrics` |
| Wired? | YES — container `_make_parser_registry` (5), used by `ParserStage` + `GraphService.build_graph` | **NO** — zero production imports outside its own directory |
| Tests | **NONE** | YES — `test_parsers.py` (29 test classes) + `test_engine.py` |

### The two graph frameworks

| | **Graph 1 — engine, WIRED** | **Graph 2 — extractor, partially WIRED** |
|---|---|---|
| Location | `infrastructure/graph/` | `infrastructure/salesforce/graph/` |
| Core | `DependencyGraphEngine` + `GraphBuilder` (29 node types, 20+ edge types), traversal/resolver/cycle/validator/statistics/versioning/cache | `CompositeExtractor` + per-type `DependencyExtractor` (Apex, Profile, Layout, ValidationRule, Flow) |
| Wired? | YES — `GraphStage` (pipeline) + impact engine + (weakly) search | YES for 4 extractors via `GraphService.build_graph`; **Flow extractor exists but NOT registered** |

Both share the **unified domain graph model** `domain/graph/models.py` (`Graph`, `NodeType` 29
values, `EdgeType` ~20, and `DependencyGraph = Graph` type alias for backward compat).

---

## Output 2 — Recommended Metadata Architecture

**Single production architecture = Broad Parser Framework + Graph Engine + Dedicated ORM tables.**

```
Salesforce Org
   │
   ▼
MetadataDownloadManager
   │
   ▼
SyncCoordinator → batches by type
   │
   ▼
MetadataPipeline (re-wired)
   ├─ ParserStage        → infrastructure/parsers/ ParserEngine (29 parsers → canonical + refs/rels)
   ├─ ValidationStage    → reuse canonical validator (9 rules) [or broad ValidationEngine]
   ├─ NormalizationStage → reuse canonical normalizer (8 rules)
   ├─ PersistenceStage   → IMetadataRepository (dedicated ORM tables; metadata_versions as audit log only)
   ├─ GraphStage         → DependencyGraphEngine (from canonical relationships)
   └─ SearchStage        → SearchEngine (WIRED with graph_engine → real dep scores)
   │
   ▼
Dedicated ORM tables (16) via SQLAlchemyMetadataRepository
Search index (search_documents) with dependency scores
Graph cache + impact engine (existing infrastructure/graph/)
```

**Key architectural decisions:**
1. **Parsers:** `infrastructure/parsers/` (System B) survives. It is the only framework that
   produces canonical `MetadataComponent` objects **with references and relationships in one
   step**, has engine-level validation/normalization/metrics, and has full test coverage. It
   mirrors the `domain/canonical/` model set 1:1.
2. **Graph:** `infrastructure/graph/` `DependencyGraphEngine` survives as the engine (it already
   powers the pipeline + impact analysis). The `CompositeExtractor` remains as the
   dependency-extraction mechanism on the rebuild path and **must register
   `FlowDependencyExtractor`**.
3. **Persistence:** `IMetadataRepository`/`SQLAlchemyMetadataRepository` (the in-progress
   repository) becomes the single write path to the 16 dedicated ORM tables. `metadata_versions`
   remains as the immutable version/audit log (it is already written by PersistenceStage and
   consumed by GraphService).
4. **Search:** `SearchEngine` must be constructed with the `DependencyGraphEngine` and
   `SearchStage` must pass it through so dependency scores/edge counts are populated.
5. **Retire:** narrow `infrastructure/salesforce/parsers/` runtime path (System A) — its 5
   parsers are a subset of System B's 29; the legacy `domain/metadata/` models and the mapper
   strategies become dead code once System B is wired (they may be kept for backward-compat
   read paths, but the pipeline no longer routes through them).

---

## Output 3 — Metadata Coverage Matrix

Legend: ✅ implemented/wired · ⚠️ partially or indirectly · ❌ absent · — n/a
Columns: **DL**=Downloader SOQL, **PA**=Narrow Parser (runtime), **PB**=Broad Parser, **CA**=Canonical model, **ORM**=Dedicated table, **ND**=NodeType, **SW**=Search weight, **EX**=Graph extractor, **T**=Tests

| Type | DL | PA | PB | CA | ORM | ND | SW | EX | T |
|---|---|---|---|---|---|---|---|---|---|
| CustomObject | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Field | ✅ (describe) | ⚠️ (in CustomObject) | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ |
| Relationship | ⚠️ | ⚠️ | ✅ | ✅ | ✅ | ✅ | — | — | ✅ |
| ApexClass | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| ApexTrigger | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Flow / FlowVersion | ✅ | — | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ (unregistered) | ✅ |
| Layout | ✅ (per obj) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| RecordType | ✅ (per obj) | — | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ |
| ValidationRule | ✅ (per obj) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Profile | ✅ | — | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| PermissionSet | ✅ | — | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Report | ✅ | — | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ |
| Dashboard | ✅ | — | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ |
| WorkflowRule | ✅ | — | ✅ | ✅ | ✅ | ✅ | ✅ | — | ✅ |
| ApprovalProcess | ✅ (ProcessDefinition) | — | ✅ | ✅ | ❌ | ✅ | ✅ | — | ✅ |
| EmailTemplate | ✅ | — | ✅ | ✅ | ❌ | ✅ | ✅ | — | ✅ |
| CustomMetadata | ❌ | — | ✅ | ✅ | ❌ | ✅ | ✅ | — | ✅ |
| CustomSetting | ❌ | — | ✅ | ✅ | ❌ | ✅ | ✅ | — | ✅ |
| LightningPage | ❌ | — | ✅ | ✅ | ❌ | ✅ | ✅ | — | ✅ |
| QuickAction | ❌ | — | ✅ | ✅ | ❌ | ✅ | ✅ | — | ✅ |
| NamedCredential | ❌ | — | ✅ | ✅ | ❌ | ✅ | ✅ | — | ✅ |
| ConnectedApp | ❌ | — | ✅ | ✅ | ❌ | ✅ | ✅ | — | ✅ |
| GlobalValueSet | ✅ | — | ✅ | ✅ | ❌ | ✅ | ✅ | — | ✅ |
| Role | ✅ (UserRole) | — | ✅ | ✅ | ❌ | ✅ | ✅ | — | ✅ |
| Queue | ✅ (QueueSobject) | — | ✅ | ✅ | ❌ | ✅ | ✅ | — | ✅ |
| PublicGroup | ❌ | — | ✅ | ✅ | ❌ | ✅ | ✅ | — | ✅ |
| SharingRule | ✅ | — | ✅ | ✅ | ❌ | ✅ | ✅ | — | ✅ |
| Formula | ⚠️ (in ValidationRule) | — | ✅ | ✅ | ❌ | ✅ | ✅ | — | ✅ |
| StaticResource / Content | ⚠️ | — | ⚠️ | ❌ | ❌ | ❌ | ❌ | — | ⚠️ |
| LWC/Aura/Visualforce | ❌ | — | ❌ | ❌ | ❌ | ❌ | ❌ | — | ❌ |

**Read-out:**
- **Full stack (download → parse → canonical → ORM → graph → search → tests):**
  CustomObject, Field, ApexClass, ApexTrigger, Flow, Layout, RecordType, ValidationRule,
  Profile, PermissionSet, Report, Dashboard, WorkflowRule — **13 types**.
- **Complete in broad parser + canonical + NodeType but NO dedicated ORM table (13 types):**
  ApprovalProcess, EmailTemplate, CustomMetadata, CustomSetting, LightningPage, QuickAction,
  NamedCredential, ConnectedApp, GlobalValueSet, Role, Queue, PublicGroup, SharingRule, Formula
  → fall back to `metadata_versions` JSON payload today.
- **Not covered anywhere:** StaticResource, LWC, Aura, Visualforce, and the remaining ~190 of
  223 `KNOWN_METADATA_TYPES` (only generic download + GenericDictStrategy passthrough).

---

## Output 4 — Parser Comparison

| Dimension | System A — narrow (`infrastructure/salesforce/parsers/`) | System B — broad (`infrastructure/parsers/`) |
|---|---|---|
| Coverage | 5 types + generic fallback | 29 types |
| Output model | Legacy `domain.metadata.*` (5 types) | Canonical `domain.canonical.Metadata*` (29) |
| References/relationships | Not extracted (except inline in graph extractors) | Extracted (`ExtractedReference`, `ExtractedRelationship`) |
| Validation engine | None | `ValidationEngine` |
| Normalization engine | None | `NormalizationEngine` |
| Metrics | None | `ParserMetrics` |
| Error taxonomy | ok/fail + error strings | `FatalParserError` vs `ParserError`, typed warnings |
| Registry | `ParserRegistry` (get/has/parse/fallback Generic) | `ParserRegistry` (register_all, `UnsupportedMetadataTypeError`) |
| Engine | None (used directly) | `ParserEngine.parse/parse_many/parse_batch` |
| Wired in container | ✅ `_make_parser_registry` | ❌ |
| Wired in pipeline | ✅ `ParserStage` | ❌ |
| Wired in GraphService | ✅ `build_graph` re-parses | ❌ |
| Unit tests | ❌ none | ✅ 29 parser test classes + engine tests |
| Name collision | `ParserRegistry` (same class name as B) | `ParserRegistry` (same class name as A) |

**Conclusion:** System B is the intended target architecture — it is complete, tested, mirrors
the canonical domain, and produces parse results that flow directly into the graph. System A
appears to be the earlier, narrower implementation that was wired first. There is no
justification for maintaining both after Phase 3.2.

---

## Output 5 — Repository Comparison

| Repository | Interface | Impl | Tables | Wired? | Tests |
|---|---|---|---|---|---|
| `IMetadataVersionRepository` | `domain/repositories/sync_repos.py` | `infrastructure/persistence/repositories/sync_repos.py` (SQLAlchemy) | `metadata_versions` (generic JSONB) | ✅ pipeline PersistenceStage, SyncCoordinator, GraphService | ⚠️ (pre-existing failures in test_metadata_sync) |
| `IMetadataRepository` (new, in-progress) | `domain/repositories/metadata_repo.py` | `infrastructure/persistence/repositories/metadata_repo.py` (SQLAlchemy, 13-type ORM mapping) | 13 dedicated tables + relationships/dependencies | ⚠️ registered in container `_make_repos_from_session` as `"metadata"` but **not called by pipeline** | ⚠️ untracked `test_metadata_repo.py` |
| `ISyncJob/History/Retry/Statistics` | `sync_repos.py` | `sync_repos.py` | `sync_jobs`, `sync_history`, `sync_retry_queue`, `sync_statistics` | ✅ | ✅ |
| `ISalesforceConnectionRepository` | `salesforce_repos.py` | — | connections | ✅ | ✅ |
| Search index | in-memory `SearchIndex` + `SearchDocumentModel` | — | `search_documents` | ✅ | ✅ |

**Key gap:** Two metadata repositories write to two different persistence targets. The
pipeline writes **only** to `metadata_versions` (JSON); the 16 dedicated ORM tables are only
reachable through `SQLAlchemyMetadataRepository`, which the pipeline never calls. This is the
central persistence discontinuity.

---

## Output 6 — Runtime Wiring Diagram

```mermaid
flowchart LR
    subgraph Inbound
        DL[MetadataDownloadManager<br/>223 types]
        SC[SyncCoordinator<br/>FULL/INCREMENTAL/...]
    end

    subgraph Pipeline
        PS[ParserStage<br/>NARROW registry 5 parsers]
        CM[CanonicalMapping<br/>19 strategies]
        VS[ValidationStage<br/>9 rules]
        NS[NormalizationStage<br/>8 rules]
        PES[PersistenceStage<br/>→ metadata_versions]
        GS[GraphStage<br/>DependencyGraphEngine]
        SS[SearchStage<br/>index_components(graph_engine=None)]
    end

    subgraph Rebuild
        GRS[GraphService.build_graph<br/>narrow parser + CompositeExtractor]
    end

    DL --> SC
    SC --> PS
    PS --> CM --> VS --> NS --> PES --> GS --> SS
    NS -.-> SEARCH[SearchEngine<br/>NO graph_engine wired]
    PES -.-> MV[(metadata_versions)]
    GS -.-> GRAPH_ENGINE[graph_engine<br/>same instance]
    GRAPH_ENGINE -.x SS
    MV --> GRS
    GRS --> GRAPH_ENGINE

    subgraph Unwired
        PE[ParserEngine 29 parsers] -.x PS
        MR[SQLAlchemyMetadataRepository<br/>16 tables] -.x PES
        FE[FlowDependencyExtractor] -.x GRS
    end
```

**Disconnects found (dashed red/✕):**
1. `ParserEngine` (System B) — complete, tested, **not referenced** by `ParserStage`.
2. `SQLAlchemyMetadataRepository` — wired into container, **never called** by pipeline.
3. `SearchEngine` constructed **without** `graph_engine` → dependency scores/edge counts are
   never computed; `SearchStage` also passes `graph_engine=None`.
4. `FlowDependencyExtractor` exists but is **not registered** in `_make_extractor`.

---

## Output 7 — Missing Components

1. **ParserEngine wiring** — replace the narrow registry in `ParserStage` with
   `infrastructure/parsers/engine.ParserEngine` (or a thin adapter) so all 29 types parse to
   canonical + references/relationships.
2. **Reference/relationship propagation** — the pipeline's `GraphStage` currently builds from
   `normalized_components`; the broad parsers already emit `ExtractedReference`/
   `ExtractedRelationship` that should feed `DependencyGraphEngine` directly.
3. **Dedicated-table persistence** — wire `IMetadataRepository` into `PersistenceStage` (or a
   new stage) so 16 tables are populated; keep `metadata_versions` as audit log.
4. **ORM tables for 13 types** — ApprovalProcess, EmailTemplate, CustomMetadata, CustomSetting,
   LightningPage, QuickAction, NamedCredential, ConnectedApp, GlobalValueSet, Role, Queue,
   PublicGroup, SharingRule, Formula.
5. **Search ↔ graph wiring** — construct `SearchEngine(graph_engine=...)` and pass the engine
   through `SearchStage`.
6. **FlowDependencyExtractor registration** in `_make_extractor`.
7. **Tests for the narrow parser path** (before retirement) and **wiring tests** for the new
   pipeline path.
8. **StaticResource / LWC / Aura / Visualforce** parsers (if in scope for the Intelligence
   Engine) — currently absent everywhere.
9. **`KNOWN_METADATA_TYPES` reconciliation** — 223 types vs 29 parsers vs 13 full-stack types;
   decide the canonical supported-type list and prune/annotate.

---

## Output 8 — Technical Debt

| # | Debt | Impact | Location |
|---|---|---|---|
| 1 | Two parser frameworks with identical class name `ParserRegistry` | Import confusion, risk of wiring the wrong one | `infrastructure/salesforce/parsers/registry.py` vs `infrastructure/parsers/registry.py` |
| 2 | Narrow parser framework has zero tests | Regression risk on the only wired path | `infrastructure/salesforce/parsers/` |
| 3 | Pipeline writes only to `metadata_versions` JSON | 16 dedicated tables dead in the runtime path; typed queries impossible | `PersistenceStage` |
| 4 | `SearchEngine` has no `graph_engine` | Dependency scores always 0 in search results | `container.py:418`, `SearchStage` |
| 5 | 12 mapper strategies are dead at runtime (no producer parsers for Flow/Profile/PermissionSet/EmailTemplate/Report/Dashboard/Role/Queue/SharingRule/WorkflowRule/Lightning/StaticResource) | Confusing surface area; two-step mapping unnecessary once System B is wired | `application/pipeline/mapper/strategies/` |
| 6 | `CompositeExtractor` matches by parsed class name; Flow extractor unregistered | Flow dependencies missing from rebuild graph | `_make_extractor` |
| 7 | `GraphService.build_graph` re-parses stored payloads with narrow parsers only (5 types) | Rebuild path under-extracts dependencies | `application/use_cases/graph/service.py` |
| 8 | `metadata_versions` payload duplicates normalized data | Storage bloat; risk of drift | `PersistenceStage`/`metadata_sync.py` |
| 9 | Pre-existing failing tests (`test_container.py` `_get_session` in testing mode, `test_metadata_sync.py` 13 errors) | CI noise; hides real regressions | `tests/unit/test_container.py`, `tests/unit/test_metadata_sync.py` |
| 10 | In-progress uncommitted metadata-repo work (untracked) | Not yet integrated; risk if abandoned | `domain/repositories/metadata_repo.py`, `infrastructure/persistence/repositories/metadata_repo.py`, `test_metadata_repo.py` |

---

## Output 9 — Recommended Implementation Order (for Phase 3.2)

1. **Retire narrow parser path in the pipeline** — swap `ParserStage` to `ParserEngine`
   (System B) with a backward-compat adapter that still returns legacy objects where
   consumers require them (GraphService rebuild).
2. **Register `FlowDependencyExtractor`** in `_make_extractor` (1-line).
3. **Wire search ↔ graph** — construct `SearchEngine(graph_engine=...)`, update `SearchStage`
   to pass the engine; verify dependency scores appear.
4. **Persist to dedicated tables** — make `PersistenceStage` (or a new stage) call
   `IMetadataRepository.save_batch` for the 13 supported types; keep `metadata_versions` writes
   for audit/versioning.
5. **Feed graph from parse references** — extend `GraphStage` to use `ExtractedReference`/
   `ExtractedRelationship` from System B (fill gaps in `GraphBuilder` node/edge maps if needed).
6. **Add ORM tables for the 13 missing types** + extend `_TYPE_TO_ORM_MODEL`.
7. **Reconcile `KNOWN_METADATA_TYPES`** with actual support; document unsupported types.
8. **Cleanup pass** — remove dead mapper strategies / legacy `domain.metadata` from the hot path
   (keep read-compat), delete or port the 5 narrow parsers, rename the two `ParserRegistry`
   classes to remove collision.
9. **Fix pre-existing test failures** (`test_container.py`, `test_metadata_sync.py`) and add
   wiring tests for the new pipeline (ParserEngine → canonical → ORM → graph → search).
10. **Regression run** — full unit + audit suites must stay green (currently 1755 passed,
    7 failed, 13 errors, 4 xfailed — all failures pre-existing).

---

## Output 10 — GO / NO GO for Phase 3.2

### ✅ GO — **with conditions**

**Rationale:**
- The target architecture is already **fully implemented and tested** (System B parsers +
  graph engine + canonical models + dedicated ORM tables + repository interface). Phase 3.2 is
  predominantly **wiring**, not building.
- No greenfield design risk: the broad framework's test suite (29 parser classes + engine) and
  the graph engine's tests give a safety net.

**Conditions (blockers for a clean Phase 3.2):**
1. The in-progress, uncommitted `IMetadataRepository` work must be **completed and committed
   first** (it is the persistence backbone of the recommendation). Do NOT discard it.
2. A **single owner decision** on the `ParserRegistry` name collision (rename one) before both
   are wired, to avoid silent wrong-registry wiring.
3. Pre-existing test failures (`test_container.py`, `test_metadata_sync.py`) must be triaged and
   fixed **before** the pipeline rewiring, so new regressions are detectable.
4. Scope of the Metadata Intelligence Engine must confirm which of the 223 `KNOWN_METADATA_TYPES`
   are in-scope; the audit recommends a **core set of 29 types** (the System B set) as v1.

**If conditions 1–3 are not met before Phase 3.2 starts, the answer is NO GO until they are.**

---

## Appendix — Evidence Summary

- **Counts:** `KNOWN_METADATA_TYPES` = 223 · broad parsers = 29 · narrow parsers = 5 · canonical
  models = 29 + base · NodeType enum = 29 · search weights = 27 · ORM tables = 16 · mapper
  strategies = 19 · extractors = 5 (4 registered).
- **Wiring proof:** `grep -rn "infrastructure\.parsers" src/` → only files inside
  `infrastructure/parsers/`; `infrastructure.graph` imported by `container.py`,
  `graph_stage.py`, `impact/engine.py`, `impact/analyzer.py`.
- **Test proof:** `tests/unit/infrastructure/parsers/test_parsers.py` (29 `Test*Parser`
  classes) + `test_engine.py`; zero tests reference `infrastructure.salesforce.parsers`.
- **Docs pattern:** this file follows `docs/request_context_phase2.md` /
  `docs/request_context_phase2_5.md`.
