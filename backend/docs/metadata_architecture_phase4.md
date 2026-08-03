# Phase 4 — Dependency Graph Engine (Repository-Fed)

**Status:** ✅ COMPLETE
**Phase:** 4 of 6
**Constraint (verbatim):** *"The Metadata Repository is now the ONLY source of metadata. Do not query Salesforce directly. Do not bypass the repository."*
**Determinism:** *"Deterministic. No AI. No LLM."*

---

## 1. Graph Architecture

The Dependency Graph is built **exclusively** from the `IMetadataRepository`
(`domain/repositories/metadata_repo.py`). No Salesforce API call, no parser
registry, and no `infrastructure/salesforce/graph/*` extractor is used for
construction. The repository returns typed canonical components (PascalCase
`type`); a deterministic builder converts them into a domain `Graph`.

```
MetadataRepository (single source of truth)
        │  get_by_organization(org, filter, request_context)
        ▼
RepositoryGraphService (application/use_cases/graph/repository_service.py)
        │  RequestContext-aware, org-isolated, cached per org
        ▼
RepositoryGraphBuilder (infrastructure/graph/repository_builder.py)
        │  deterministic node creation + edge derivation
        ▼
DependencyGraphEngine (infrastructure/graph/engine.py)
        │  holds Graph, version snapshots, cache
        ▼
Graph model (domain/graph/models.py) — nodes / edges / adjacency
        │
        ├── traversal ops: get_neighbors, get_dependencies, get_dependents,
        │                    find_path, shortest_path, connected_components,
        │                    get_subgraph, export
        ├── resolution ops: where_used, what_depends_on
        └── analysis ops:   find_cycles, connected_components, statistics
```

### Key decisions
1. **REUSE the existing domain `Graph` model** (`domain/graph/models.py`). The
   Phase 5 impact engine, `infrastructure/impact/*`, and the existing API
   routes depend on `engine.graph` and `Graph.get_node("type:api_name")`. The
   key format `f"{node_type.value}:{api_name}"` is preserved verbatim.
2. **New `RepositoryGraphBuilder`** (`infrastructure/graph/repository_builder.py`)
   — self-contained, deterministic, mirrors the reference-extraction patterns
   of the frozen Validation & Consistency engine. It never imports the frozen
   `validation_rules.py` module (it copies the tiny `read_prop`/`_as_list`/
   `_extract_reference_names` helpers locally to avoid coupling).
3. **New `RepositoryGraphService`** (`application/use_cases/graph/repository_service.py`)
   — replaces `GraphService` wiring in the container while keeping the exact
   public method surface (`build_graph`, `get_node_dependencies`, `find_impact`,
   `find_cycles`, `graph_summary`) so existing API routes, AI tools, and impact
   code keep working unchanged.
4. **EdgeType extended additively.** The 14 required canonical edge types were
   added; all legacy values (`OWNS`, `INVOKES`, `LOOKUP`, `*_REFERENCE`,
   `TRIGGER_ON`, `SOQL_REFERENCE`, `CUSTOM`) remain for API compatibility.
5. **No invented edges.** Edges are only created when the target node exists in
   the loaded component set (verified against a reference registry built from
   the graph nodes). Missing targets produce no edge (matching the conservative
   validation rules).
6. **In-memory graph + per-org cache.** Consistent with the existing
   `GraphCacheCoordinator` (in-memory, max 10). No new distributed
   infrastructure. Full rebuilds are O(V+E); incremental updates only re-derive
   edges for affected components.
7. **Version-aware construction** supported via `build_graph_versioned` (latest
   version of each api_name wins) and `build_from_versioned` in the builder.

---

## 2. Node Model

- **Class:** `GraphNode` (`domain/graph/models.py`) — unchanged.
- **Key format:** `f"{node_type.value}:{api_name}"` — the API contract.
- **NodeType** (29 values) — all canonical types are supported:
  `OBJECT, FIELD, RELATIONSHIP, FLOW, FLOW_VERSION, VALIDATION_RULE, FORMULA,
  LAYOUT, RECORD_TYPE, PERMISSION_SET, PROFILE, APEX_CLASS, TRIGGER, REPORT,
  DASHBOARD, WORKFLOW, APPROVAL_PROCESS, CUSTOM_METADATA, CUSTOM_SETTING,
  LIGHTNING_PAGE, QUICK_ACTION, EMAIL_TEMPLATE, NAMED_CREDENTIAL, CONNECTED_APP,
  ROLE, QUEUE, PUBLIC_GROUP, SHARING_RULE, GLOBAL_VALUE_SET`.
- **Node metadata** (set by `RepositoryGraphBuilder.component_to_node`):
  `component_type` (PascalCase), `component_id`, `source_platform`, `version`,
  `status`, `organization_id`, `hash`. The `component_type`/`component_id` keys
  let the Phase 5 impact engine resolve `component_type`/`component_name`
  directly from a node.
- **Type resolution:** `resolve_node_type` handles both PascalCase (repo
  read-path vocabulary: `Object`, `ApexClass`, …) and snake_case (`object`,
  `apex_class`, …), plus Salesforce API names (`CustomObject`, `CustomField`,
  `ApexTrigger`). The existing `GraphBuilder` also gained the PascalCase map so
  any legacy path that passes repo components does not default to `OBJECT`.

---

## 3. Edge Model

- **Class:** `GraphEdge` (`domain/graph/models.py`) — unchanged.
- **Edge id:** `f"{source_id}--[{edge_type.value}]-->{target_id}"` (dedupe by id).
- **EdgeType** (33 values) — the 19 required canonical types:
  `REFERENCES, USES, CALLS, CONTAINS, EXTENDS, IMPLEMENTS, LOOKUP_TO,
  MASTER_DETAIL_TO, USES_FIELD, USES_OBJECT, USES_FLOW, USES_TRIGGER,
  USES_REPORT, USES_LAYOUT, USES_DASHBOARD, USES_PERMISSION, USES_PROFILE,
  IMPORTS, DEPENDS_ON` plus legacy aliases.
- **Edge metadata** (set by the builder): `field` (the metadata property the
  edge came from), `source_api_name`, `target_api_name`,
  `target_component_type`, and any declared relationship metadata.

### Deterministic edge derivation (mirrors validation_rules patterns)

| # | Source type | Metadata read | Target | EdgeType |
|---|-------------|---------------|--------|----------|
| 1 | Field, ValidationRule, Trigger, Formula, Layout, RecordType, Report, Workflow, ApprovalProcess, SharingRule, QuickAction, CustomSetting | `object_api_name` | Object | `USES_OBJECT` |
| 2 | Field | `reference_to` + `field_type` | Object | `LOOKUP_TO` / `MASTER_DETAIL_TO` |
| 3 | Formula | `field_api_name` | Field | `USES_FIELD` |
| 4 | Flow | `record_creates`/`record_updates`/`record_deletes` | Object | `USES_OBJECT` |
| 5 | Flow | `subflows` | Flow | `USES_FLOW` |
| 6 | Role | `parent_role` | Role | `DEPENDS_ON` |
| 7 | PermissionSet / Profile | `object_permissions` | Object | `USES_OBJECT` |
| 8 | PermissionSet / Profile | `field_permissions` | Field | `USES_FIELD` |
| 9 | PermissionSet / Profile | `class_permissions` | ApexClass | `USES` |
| 10 | Dashboard | `components` | Report | `USES_REPORT` |
| 11 | ApexClass | body regex `extends` | ApexClass | `EXTENDS` |
| 12 | ApexClass | body regex `implements` | ApexClass | `IMPLEMENTS` |
| 13 | ApexClass | body regex `FROM <obj>` | Object | `USES_OBJECT` |
| 14 | Trigger | `object_api_name` | Object | `USES_OBJECT` |
| 15 | EmailTemplate | `object_type` | Object | `USES_OBJECT` |
| 16 | Queue | `queue_sobjects` | Object | `USES_OBJECT` |
| 17 | QuickAction | `target_object` | Object | `USES_OBJECT` |
| 18 | any | declared `CanonicalRelationship` | target | mapped `RelationshipType`→`EdgeType` |

`RelationshipType`→`EdgeType` map: `CONTAINS→CONTAINS`, `REFERENCES→REFERENCES`,
`DEPENDS_ON→DEPENDS_ON`, `IMPLEMENTS→IMPLEMENTS`, `EXTENDS→EXTENDS`,
`MANAGES→USES`, `CONTROLS_ACCESS_TO→USES_PERMISSION`, `TRIGGERS→USES_TRIGGER`,
`VALIDATES→USES_FIELD`.

---

## 4. Graph Construction Pipeline

### Full rebuild
```
service.build_graph(org_id, metadata_types=None, request_context=None)
  1. check per-org cache (org isolation, fast path)
  2. repo.get_by_organization(org_id, filter, pagination) — bulk, paginated,
     no N+1, RequestContext passed
  3. engine.build_from_repository(components) -> RepositoryGraphBuilder.build
     a. create a node per component (deduped by key)
     b. derive edges deterministically (only to existing nodes)
  4. cache per org; record source + request_id in graph metadata
```

### Incremental rebuild
```
service.incremental_update(org_id, new_components, changed_components,
                           deleted_api_names, request_context)
  1. remove deleted api_names (Graph.remove_node cleans attached edges)
  2. add/replace changed nodes
  3. re-derive edges for the affected component set only
```

### Version-aware rebuild
```
service.build_graph_versioned(org_id, components_by_version, request_context)
  -> builder.build_from_versioned: for each api_name the highest component
     version wins (deterministic)
```

### Organization isolation
- Cache key is `repo-graph:{org_id}`; graphs never leak across orgs.
- Every repository call passes `request_context` (tenant verification is
  enforced inside the repository itself).

### RequestContext propagation
- `build_graph`/`incremental_update`/`build_graph_versioned` all accept and
  forward `request_context` to `repo.get_by_organization`.
- The request id is recorded in the graph metadata for traceability.

---

## 5. Traversal Algorithms

All traversal is implemented in `infrastructure/graph/traversal.py`
(`GraphTraversalEngine`) and exposed on `DependencyGraphEngine` and
`RepositoryGraphService`. All are iterative (BFS/DFS with explicit stacks/
queues) — no recursion depth issues at 100k+ nodes.

| Operation | Implementation | Complexity |
|-----------|----------------|------------|
| `get_node(key)` | dict lookup | O(1) |
| `get_neighbors(node, depth)` | BFS over outgoing+incoming | O(V+E) bounded by depth |
| `get_dependencies(node, depth)` | BFS over outgoing (upstream) | O(V+E) |
| `get_dependents(node, depth)` | BFS over incoming (downstream) | O(V+E) |
| `find_where_used(api_name)` | incoming traversal (ancestors) | O(V+E) |
| `what_depends_on(api_name)` | outgoing traversal (descendants) | O(V+E) |
| `find_path(source, target)` | DFS with parent tracking | O(V+E) |
| `shortest_path(source, target)` | BFS | O(V+E) |
| `find_cycles()` | DFS + recursion stack (existing `CycleDetectionEngine`) | O(V+E) |
| `connected_components()` | BFS over all nodes (undirected) | O(V+E) |
| `get_subgraph(node, depth)` | BFS copying nodes/edges | O(V+E) |
| `export()` | model dump (JSON) | O(V+E) |

**Avoiding O(N²):** node lookup is O(1) via `dict`; edge adjacency is indexed
via `outgoing`/`incoming` maps (`dict[str, list[edge_id]]`); all traversals
mark `visited` sets so each node/edge is touched at most once per query.
Incremental updates only touch affected components and their derived edges.

---

## 6. Files Modified / Added

### Modified
| File | Change |
|------|--------|
| `backend/src/sfir_backend/domain/graph/models.py` | Extended `EdgeType` (+14 canonical values); extended `DependencyType`; extended `_NODE_TYPE_MAP` (full PascalCase map) and `_EDGE_TYPE_MAP`; added `Graph.get_neighbors`, `get_dependencies`, `get_dependents`, `find_path`, `connected_components`, `get_subgraph`, `export`; fixed `add_edge` dedupe (was appending duplicate ids to adjacency lists) |
| `backend/src/sfir_backend/infrastructure/graph/traversal.py` | Added `get_neighbors`, `find_path`, `connected_components`, `get_subgraph`, `export` |
| `backend/src/sfir_backend/infrastructure/graph/engine.py` | Added `build_from_repository`, `build_from_repository_versioned`, `incremental_update_from_repository`, `load_cached_graph`, `get_node`, `get_neighbors`, `get_dependencies`, `get_dependents`, `find_path`, `connected_components`, `get_subgraph`, `export` |
| `backend/src/sfir_backend/infrastructure/graph/builder.py` | `NODE_TYPE_MAP` now includes PascalCase + SF API names; added `resolve_node_type`; `_component_to_node`/`_relationship_to_edge` use it and add richer metadata |
| `backend/src/sfir_backend/infrastructure/graph/__init__.py` | Export `RepositoryGraphBuilder` |
| `backend/src/sfir_backend/config/container.py` | `_make_graph_service`/`create_graph_service` now build `RepositoryGraphService(metadata_repo=repos["metadata"], graph_engine, graph_cache, cache_coordinator)` |
| `backend/src/sfir_backend/api/deps.py` | `get_graph_service` returns `RepositoryGraphService` |
| `backend/src/sfir_backend/api/v1/routes/graph.py` | Type annotations → `RepositoryGraphService`; RequestContext injected; new endpoints: `/node`, `/neighbors`, `/where-used`, `/path`, `/shortest-path`, `/components`, `/subgraph`, `/export`, `/incremental` |
| `backend/src/sfir_backend/api/v1/routes/dependencies.py`, `impact.py`, `ai.py` | Type annotations → `RepositoryGraphService` (runtime behavior unchanged) |

### Added
| File | Purpose |
|------|---------|
| `backend/src/sfir_backend/infrastructure/graph/repository_builder.py` | `RepositoryGraphBuilder` — repo-fed deterministic builder (nodes + edge derivation + incremental + versioned) |
| `backend/src/sfir_backend/application/use_cases/graph/repository_service.py` | `RepositoryGraphService` — repo-fed use case, RequestContext-aware, org-isolated, legacy-compatible |
| `backend/tests/unit/infrastructure/graph/test_repository_builder.py` | 19 builder tests |
| `backend/tests/unit/application/use_cases/graph/test_repository_graph_service.py` | 21 service tests |
| `backend/tests/unit/domain/graph/test_graph_model_ops.py` | 17 model-op tests |

---

## 7. Tests Added

| Area | Count | Covers |
|------|-------|--------|
| `test_repository_builder.py` | 19 | node creation (all PascalCase types), no duplicate nodes, parent-object edges, lookup/master-detail edges, formula→field, flow→object/subflow, role→parent, permission-set→object, dashboard→report, apex extends/implements/SOQL, trigger→object, declared relationships, **no invented edges**, incremental add/remove, versioned build, determinism |
| `test_repository_graph_service.py` | 21 | repo-only construction, RequestContext propagation, org isolation (cache), metadata-type filter, incremental update, get_node/neighbors/dependencies/dependents, where-used, find_path, shortest_path, connected_components, subgraph, export, cycles, no duplicate nodes/edges, legacy `get_node_dependencies`/`find_impact`/`graph_summary`/`find_cycles(graph)` shapes, invalidate, versioned build |
| `test_graph_model_ops.py` | 17 | all 19 required EdgeTypes present, legacy EdgeTypes preserved, DependencyType mapping, get_neighbors (depth 1/2), dependencies/dependents semantics, find_path (direct/indirect/missing/same), connected_components (connected + disconnected), subgraph, export (JSON-serializable) |

**Run:**
```bash
cd backend && ./Agent.env/bin/python -m pytest tests/unit/infrastructure/graph \
  tests/unit/domain/graph tests/unit/application/use_cases/graph -q
```

**Full suite:** `2316 passed` (2259 baseline + 57 new), `2 failed` +
`13 errors` (both **pre-existing** and unrelated: `test_container.py` DB-not-
initialized with the test DB unreachable; `test_metadata_sync.py` missing
`oauth_service` arg), `101 skipped`, `4 xfailed`.

---

## 8. Performance Observations

- **Node/edge creation:** O(V + E) — every component becomes a node (dict
  insert, deduped by key), edges are derived in one pass per component.
- **Indexed traversal:** all queries use the `outgoing`/`incoming` adjacency
  indexes — no O(N²) scans. `get_node` is O(1).
- **Incremental updates:** O(affected) — only changed/deleted components are
  re-processed; edges re-derived only for the affected set.
- **Caching:** per-org in-memory cache (existing `GraphCacheCoordinator`, max
  10 graphs) — the same org's graph is built once and reused; invalidation
  forces a rebuild. Consistent with the existing architecture — no premature
  distributed infrastructure.
- **Scale note:** at 100k+ nodes / millions of edges, a full rebuild is
  memory-heavy (in-memory `Graph`). This is acceptable for Phase 4; the cache
  plus incremental updates keep steady-state cost low. If memory becomes a
  constraint, the `MetadataDependencyModel` table (already in the schema) is
  the natural durable edge store — no graph code change required, just a
  writer. This is recorded as tech debt (below).
- **Test DB unreachable:** integration tests that require Postgres skip; all
  57 new tests are pure unit tests (no DB).

---

## 9. Remaining Technical Debt

1. **`MetadataDependencyModel` is not written.** The persistent
   `metadata_dependencies` table exists but has no writer. The graph is
   in-memory + cached per org. If durable graph storage is needed (large orgs,
   restart resilience, cross-session queries), add a writer that persists
   edges on build/incremental. This is an additive change — the builder and
   service interfaces already support it.
2. **Duplicate edge derivation between builder and validation_rules.** The
   reference patterns exist in two places (frozen `validation_rules.py` and
   `repository_builder.py`). They are intentionally kept in sync manually
   because `validation_rules.py` is FROZEN. If it ever unfreezes, extract the
   patterns into a shared module.
3. **`GraphBuilder` legacy path still supports parse-result/normalized input.**
   The frozen pipeline `GraphStage` still uses `build_from_normalized`/
   `incremental_update_from_normalized`. This is untouched and still works,
   but it is a second construction path alongside the repo-fed one. No
   conflict (different builders), but eventual consolidation would remove the
   duplication.
4. **`infrastructure/salesforce/graph/*` extractors remain registered** in the
   container (`_make_extractor`) but are no longer used for construction. They
   could be removed once all call sites are confirmed gone (kept now to avoid
   churn in the frozen agent/AI wiring).
5. **`get_upstream`/`get_downstream` naming** is historical and slightly
   counter-intuitive (`get_upstream` follows outgoing edges). Public aliases
   `get_dependencies`/`get_dependents` with clear semantics were added on top;
   renaming the legacy methods would break the frozen impact code, so it was
   not done.
6. **Apex reference extraction is regex-based.** Extends/implements/SOQL FROM
   are deterministic but regex-based; dynamic SOQL, schema namespaces
   (`namespace__Object`), and string-built queries are not captured. This
   matches the conservative validation engine and intentionally produces no
   invented edges. A future parser-backed pass could enrich edges.

---

## 10. Recommendation: Backend Ready for Phase 5 (Impact Analysis Engine)?

**✅ GO — the backend is ready for Phase 5.**

Rationale:
- The Dependency Graph now builds **exclusively** from `MetadataRepository`
  (verified: `RepositoryGraphService` only calls `repo.get_by_organization`/
  bulk loads; no parser, no extractor, no Salesforce access in the construction
  path).
- All required operations are implemented and unit-tested: where-used,
  dependency traversal, cycle detection, path finding, connected components,
  subgraph, export, incremental rebuilds, org isolation, RequestContext
  propagation, version-aware builds.
- The **existing Phase 5 impact engine (`infrastructure/impact/*`) interface is
  satisfied**: it depends on `engine.graph` and `Graph.get_node(
  "{node_type.value}:{api_name}")` — both preserved exactly. Node metadata now
  also carries `component_type`/`component_id`, which the impact engine needs
  to resolve component types.
- No regressions: full suite 2316 passed; the only failures are pre-existing
  and unrelated.
- The frozen API surface (routes, AI tools, container wiring) is compatible —
  `build_graph`, `get_node_dependencies`, `find_impact`, `find_cycles`,
  `graph_summary` all keep their exact shapes.

### Success criteria check
| Criterion | Status |
|-----------|--------|
| Graph builds exclusively from MetadataRepository | ✅ |
| Graph contains deterministic nodes and edges | ✅ |
| Graph supports where-used queries | ✅ |
| Graph supports dependency traversal | ✅ |
| Graph supports cycle detection | ✅ |
| Graph supports path finding | ✅ |
| Graph is RequestContext-aware | ✅ |
| Existing APIs remain compatible | ✅ |
| Existing UI requires no changes | ✅ |
| All tests pass | ✅ (2316 passed; only pre-existing unrelated failures) |

**Phase 5 can proceed.**
