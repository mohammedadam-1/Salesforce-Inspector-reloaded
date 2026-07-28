# Canonical Metadata Normalization — Architecture Design

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Purpose](#2-purpose)
3. [Normalization Rules](#3-normalization-rules)
4. [Normalized Metadata Model](#4-normalized-metadata-model)
5. [Hashing Strategy](#5-hashing-strategy)
6. [Identity Strategy](#6-identity-strategy)
7. [Relationship Normalization](#7-relationship-normalization)
8. [Persistence Boundary](#8-persistence-boundary)
9. [Graph Boundary](#9-graph-boundary)
10. [Search Boundary](#10-search-boundary)
11. [AI Boundary](#11-ai-boundary)
12. [Performance & Scalability](#12-performance--scalability)
13. [Error Handling](#13-error-handling)
14. [Backward Compatibility](#14-backward-compatibility)
15. [Implementation Roadmap](#15-implementation-roadmap)
16. [Sequence Diagram](#16-sequence-diagram)
17. [Component Diagram](#17-component-diagram)
18. [Class Diagram](#18-class-diagram)
19. [Risk & Trade-off Analysis](#19-risk--trade-off-analysis)
20. [Architecture Readiness Assessment](#20-architecture-readiness-assessment)

---

## 1. Executive Summary

The Normalization layer transforms validated canonical metadata into a deterministic, storage-ready representation consumed by Persistence, Graph, Search, and AI. It is the last pure-transformation stage before data leaves the pipeline for specialized subsystems.

**Why it exists:** Downstream consumers each require the same metadata in different shapes. Persistence needs flat records with stable IDs. Graph needs adjacency lists with typed edges. Search needs tokenized text blobs with ranking metadata. AI needs resolved reference chains in structured context. Without normalization, each consumer would duplicate parsing, ordering, deduplication, and identity resolution logic — creating coupling, inconsistency, and maintenance burden.

**Key design decisions:**

- Normalization is **read-only**: canonical models are never mutated
- Every normalized document carries a **deterministic fingerprint** for change detection
- Identities are **stable across syncs**: based on natural keys, not database IDs
- Relationships are **flattened and deduplicated** into adjacency structures
- Collections are **deterministically ordered** to guarantee idempotent output
- The normalizer is **pure**: same input → same output, no I/O, no side effects

---

## 2. Purpose

### 2.1 Why a normalization layer exists

The pipeline produces canonical models that are rich, object-oriented, and interconnected. Downstream consumers cannot consume these directly for four reasons:

1. **Shape mismatch** — Persistence stores flat rows, Graph stores edges, Search stores inverted indices, AI stores context windows. A `MetadataApexClass` containing nested `MetadataComponent` objects and `CanonicalRelationship` lists is not directly insertable into any of these stores.

2. **Identity instability** — Canonical models carry a string `id` field that is a transient pipeline identifier. Downstream consumers require stable, deterministic, cross-sync identifiers derived from the component's natural key.

3. **Duplicate & inconsistent data** — Canonical models may contain duplicate references, unsorted collections, null fields, and inconsistent casing. Normalization guarantees every downstream consumer receives the same cleaned, ordered, deduplicated view.

4. **Cross-cutting concerns** — Hashing, fingerprinting, reference resolution, and fully-qualified name generation are needed by all consumers. Centralizing them prevents N reimplementations.

### 2.2 What problems normalization solves

| Problem | Solution |
|---------|----------|
| Downstream consumers couple to canonical model shape | Single normalization boundary isolates consumers from canonical model evolution |
| Transient IDs used as permanent references | Deterministic natural-key-based identity replaces transient IDs |
| Unordered collections cause non-deterministic output | Every collection is sorted by stable key before output |
| Duplicate references produce inconsistent graphs | References are deduplicated by target identity |
| Null handling differs per consumer | Normalization applies consistent null→default/omission rules |
| Change detection duplicated N times | Single fingerprint computed once, consumed by all |
| Fully-qualified names computed N times | Single FQN generated during normalization |

### 2.3 Why Persistence should never consume raw canonical models

Persistence requires flat, indexed records with immutable primary keys. Canonical models are nested object trees with transient `id` fields. If Persistence consumed canonical models directly, it would need to:

- Implement its own flattening logic
- Generate stable primary keys
- Order and deduplicate collections
- Compute content hashes for change detection
- Resolve fully-qualified names

This duplicates normalization logic across Persistence, Graph, Search, and AI, leading to drift, bugs, and maintenance overhead. Normalization centralizes this once.

### 2.4 Why Graph should consume normalized models

The dependency graph cares about typed edges between components, not the full metadata payload. A normalized model provides:
- Resolved `(source_type, source_key, target_type, target_key, relationship_type)` tuples
- Deduplicated relationship lists (no duplicate edges)
- Stable references that survive re-syncs

Consuming canonical models directly would force Graph to re-resolve every reference and handle transient identity mapping — logic that normalization already performs.

### 2.5 Why Search should consume normalized models

Search needs flat, tokenized documents with consistent field names for indexing. Normalized models provide:
- A flat key-value representation suitable for indexers
- Pre-computed search tokens (derived from labels, descriptions, API names)
- Consistent field naming across all metadata types

### 2.6 Why AI should consume normalized models

AI context builders need resolved, connected, self-contained metadata. Normalized models provide:
- Fully resolved parent-child chains (no unresolved `object_api_name`)
- Deterministic text representations suitable for prompt injection
- Fingerprinted components so AI can reason about staleness

---

## 3. Normalization Rules

Every rule below applies deterministically. The same canonical input always produces identical normalized output.

### 3.1 Deterministic Identifiers

**Rule:** Generate a stable, reproducible identifier for every component using its natural key.

**Why:** Downstream consumers require cross-sync identity stability. A component must have the same identity today, tomorrow, and after re-sync.

**Algorithm:** `normalized_id = hash_concat(normalize(organization_id), normalize(source_platform), normalize(type), normalize(api_name))`

The identity depends only on fields that do not change between syncs.

### 3.2 Canonical Component Keys

**Rule:** Every normalized model carries a `component_key` tuple `(type, api_name, namespace)` that uniquely identifies the component within an organization.

**Why:** Enables cross-reference resolution without hashing. Human-readable for debugging.

### 3.3 Qualified Names

**Rule:** Generate `qualified_name = f"{api_name}"` for top-level components, `qualified_name = f"{parent_api_name}.{api_name}"` for nested components (fields, validation rules).

**Why:** Persistence and Search require fully disambiguated names. A field `Name` on `Account` and a field `Name` on `Contact` must be distinguishable.

### 3.4 Fully Qualified API Names

**Rule:** Generate `fqdn = f"{namespace}___{api_name}"` when namespace is present, otherwise `fqdn = api_name`.

**Why:** Salesforce metadata uses `namespace___` prefix for managed package components. Cross-org syncs require this prefix to avoid collisions.

### 3.5 Namespace Handling

**Rule:** If `namespace` is `None` or empty string, omit namespace prefix from FQDN. If present, use `{namespace}___{api_name}`.

**Why:** Managed package components have different ownership and upgrade semantics.

### 3.6 Stable Ordering

**Rule:** Sort every collection by a deterministic key before output. For lists of components, sort by `(type, api_name)`. For lists of strings, sort alphabetically. For lists of dicts, sort by a type-specific stable key or serialized JSON.

**Why:** Guarantees idempotent output. Without stable ordering, the same sync run twice could produce different results, breaking change detection.

### 3.7 Reference Normalization

**Rule:** Replace all string-based references (`object_api_name`, `parent_role`, `reference_to`) with normalized identities.

**Why:** References must survive re-syncs. An `object_api_name` value of `"Account"` stored today must match the normalized identity of `Account` computed tomorrow.

### 3.8 Relationship Normalization

**Rule:** Flatten `CanonicalRelationship` objects into tuples of `(relationship_type, target_component_key, target_fqdn)`.

**Why:** Downstream consumers (especially Graph) need typed, resolved edges, not opaque dicts.

### 3.9 Metadata Type Normalization

**Rule:** Map `component.type` to a controlled vocabulary. E.g., `"apex_class" → "ApexClass"`, `"validation_rule" → "ValidationRule"`.

**Why:** Downstream consumers expect PascalCase type names matching Salesforce API conventions.

### 3.10 Version Normalization

**Rule:** Ensure `version` is a positive integer, defaulting to `1` if missing or invalid.

**Why:** Downstream consumers require numeric version for ordering and staleness checks.

### 3.11 Status Normalization

**Rule:** Map `status` to lowercase canonical form: `"active"`, `"inactive"`, `"deleted"`, `"deprecated"`, `"draft"`.

**Why:** Prevents casing mismatches across consumers.

### 3.12 Owner Normalization

**Rule:** If `metadata_properties` contains an owner reference (`CreatedById`, `LastModifiedById`), extract it to a top-level `owner_id` field.

**Why:** Persistence and Graph need owner as a first-class filterable attribute.

### 3.13 Timestamp Normalization

**Rule:** Convert all `datetime` fields to ISO 8601 UTC strings. If `None`, omit from output or use a sentinel epoch value.

**Why:** Downstream consumers expect string timestamps; timezone-naive datetimes cause ambiguity.

### 3.14 Default Values

**Rule:** Apply canonical model defaults for missing optional fields. E.g., `MetadataFlow.process_type` defaults to `"Flow"`, `MetadataComponent.status` defaults to `"active"`.

**Why:** Downstream consumers should never see `None` for fields with sensible defaults.

### 3.15 Null Handling

**Rule:** Strip `None` values from normalized output. Do not emit fields with null values unless the field is required.

**Why:** Reduces payload size; consumers can assume missing optional fields are absent.

### 3.16 String Normalization

**Rule:** Strip leading/trailing whitespace from all string fields. Normalize Unicode to NFC form. Do not change case.

**Why:** Prevents whitespace-induced false change detection. NFC ensures consistent Unicode representation.

### 3.17 Collection Ordering

**Rule:** Sort all list fields deterministically. See [Stable Ordering](#36-stable-ordering).

### 3.18 Collection Deduplication

**Rule:** Remove duplicate entries from all list fields. For lists of components, deduplicate by normalized identity. For lists of strings, deduplicate by value.

**Why:** Downstream consumers should not process the same reference twice.

### 3.19 Reference Deduplication

**Rule:** For lists of relationships/references, deduplicate by `(relationship_type, target_identity)`.

**Why:** A component should not declare the same relationship twice.

### 3.20 Relationship Flattening

**Rule:** Convert nested `MetadataField` objects inside `MetadataObject.fields` into separate normalized documents with a `parent_key` reference, and emit a `contains` relationship for each.

**Why:** Persistence and Graph operate on individual components, not nested trees. Flattening is essential for relational storage.

---

## 4. Normalized Metadata Model

### 4.1 MetadataComponentDocument (Base)

Every normalized component produces a `MetadataComponentDocument` with the following fields.

| Field | Type | Required | Generated | Derived | Optional | Purpose | Canonical Source |
|-------|------|----------|-----------|---------|----------|---------|------------------|
| `identity` | `str` (SHA-256 hex) | Yes | Yes | No | No | Deterministic, stable, cross-sync unique identifier | `hash(org_id, platform, type, api_name)` |
| `component_key` | `ComponentKey` | Yes | Yes | No | No | Human-readable tuple `(type, api_name, namespace)` | Derived from `type`, `api_name`, `namespace` |
| `type` | `str` | Yes | No | Yes | No | PascalCase metadata type name | `component.type` → normalized vocabulary |
| `api_name` | `str` | Yes | No | No | No | Original API name | `component.api_name` |
| `qualified_name` | `str` | Yes | Yes | No | No | Parent-qualified name for nested components | `{parent}.{api_name}` or `api_name` |
| `fully_qualified_name` | `str` | Yes | Yes | No | No | Namespace-prefixed API name | `{namespace}___{api_name}` or `api_name` |
| `label` | `str` | No | No | No | Yes | Human-readable label | `component.label` |
| `namespace` | `str\|None` | No | No | No | Yes | Managed package namespace | `component.namespace` |
| `description` | `str\|None` | No | No | No | Yes | Description text | `component.description` |
| `version` | `int` | Yes | No | Yes | No | Schema version, defaults to 1 | `component.version` |
| `status` | `str` | Yes | No | Yes | No | Normalized status | `component.status` → lowercase canonical |
| `source_platform` | `str` | Yes | No | Yes | No | Platform identifier | `component.source_platform.value` |
| `organization_id` | `str` | Yes | No | No | No | Owning org UUID | `component.organization_id` |
| `owner_id` | `str\|None` | No | No | Yes | Yes | Extracted owner reference | `metadata_properties` extraction |
| `created_at` | `str\|None` | No | No | No | Yes | ISO 8601 UTC created timestamp | `component.created_at` |
| `updated_at` | `str\|None` | No | No | No | Yes | ISO 8601 UTC updated timestamp | `component.updated_at` |
| `fingerprint` | `str` (SHA-256 hex) | Yes | Yes | No | No | Deterministic hash of all content fields | Hash of serialized content |
| `content_hash` | `str` (SHA-256 hex) | Yes | Yes | No | No | Hash of code/body content only | Hash of body/field/formula content |
| `properties` | `dict[str, Any]` | No | No | No | Yes | Normalized metadata properties | Filtered, ordered `metadata_properties` |
| `relationships` | `list[NormalizedRelationship]` | No | Yes | No | Yes | Flattened, deduplicated relationships | `component.relationships` + derived parent refs |
| `normalized_at` | `str` | Yes | Yes | No | No | ISO 8601 UTC normalization timestamp | Generated at normalization time |

### 4.2 NormalizedRelationship

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `type` | `str` | Yes | Relationship type from controlled vocabulary (`contains`, `references`, `depends_on`, etc.) |
| `target_identity` | `str` | Yes | Deterministic identity of the target component |
| `target_component_key` | `ComponentKey` | Yes | Human-readable key of the target |
| `target_fqdn` | `str` | Yes | Fully qualified name of the target |
| `metadata` | `dict[str, Any]` | No | Optional relationship metadata (cascade delete, etc.) |

### 4.3 ComponentKey

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `type` | `str` | Yes | Normalized PascalCase type |
| `api_name` | `str` | Yes | API name |
| `namespace` | `str\|None` | No | Namespace |

### 4.4 Type-Specific Normalized Documents

Each canonical model subclass maps to a `Normalized{Type}` document that extends `MetadataComponentDocument` with type-specific flattened fields.

Example — `NormalizedApexClass`:

| Field | Type | Canonical Source |
|-------|------|------------------|
| `body` | `str` | `MetadataApexClass.body` |
| `api_version` | `int\|None` | `MetadataApexClass.api_version` |
| `length` | `int\|None` | `MetadataApexClass.length` |

Example — `NormalizedObject`:

| Field | Type | Canonical Source |
|-------|------|------------------|
| `plural_label` | `str` | `MetadataObject.plural_label` |
| `sharing_model` | `str` | `MetadataObject.sharing_model` |
| `deployment_status` | `str` | `MetadataObject.deployment_status` |
| `child_components` | `list[str]` | Derived: identities of contained fields, validation rules, etc. |

Type-specific fields repeat the same pattern for every canonical subclass, flattening nested structures to top-level key-value pairs.

---

## 5. Hashing Strategy

### 5.1 Component Hash (identity)

**Purpose:** Uniquely identify a component across syncs.

**Algorithm:**
```
component_hash = SHA-256(
    normalize(organization_id)   ||
    ":"                          ||
    normalize(source_platform)   ||
    ":"                          ||
    normalize(type)              ||
    ":"                          ||
    normalize(api_name)          ||
    (":" + normalize(namespace) if namespace else "")
)
```

**Properties:**
- Deterministic: same org + platform + type + api_name → same hash
- Stable across syncs: changing body does NOT change component hash
- Globally unique within the system (org-scoped)

### 5.2 Content Hash

**Purpose:** Detect actual metadata changes between syncs.

**Algorithm:**
```
content_hash = SHA-256(
    canonical_json(component, exclude_fields=["id", "relationships", "metadata_properties", "created_at", "updated_at"])
)
```

Where `canonical_json` produces a stable, sorted-key JSON serialization.

**Properties:**
- Changes when any functional field changes
- Ignores transient fields (id, timestamps)
- Used for change detection in incremental sync

### 5.3 Relationship Hash

**Purpose:** Detect changes in component connectivity.

**Algorithm:**
```
relationship_hash = SHA-256(
    deterministic_json(sorted([
        (rel.type, rel.target_identity)
        for rel in normalized_relationships
    ]))
)
```

**Properties:**
- Changes only when relationships change
- Ignores relationship metadata that doesn't affect connectivity

### 5.4 Version Hash

**Purpose:** Version-stamped change detection for optimistic concurrency.

**Algorithm:**
```
version_hash = SHA-256(content_hash + ":" + str(version))
```

**Properties:**
- Combines content with version number
- Enables optimistic locking in Persistence

### 5.5 Fingerprint

**Purpose:** Single hash representing the complete state of a normalized component.

**Algorithm:**
```
fingerprint = SHA-256(
    content_hash   ||
    ":"            ||
    relationship_hash
)
```

**Properties:**
- Changes when content OR relationships change
- Used by Graph and Search for cache invalidation
- Stored in Persistence for efficient staleness checks

### 5.6 Change Detection Strategy

| Scenario | Component Hash | Content Hash | Fingerprint | Action |
|----------|---------------|--------------|-------------|--------|
| New component | Not found | New | New | Insert |
| No changes | Match | Match | Match | Skip |
| Content changed | Match | Different | Different | Update |
| Relationship changed | Match | Match | Different | Update relationships only |
| Moved/renamed | Different | N/A | N/A | Delete old + insert new |

### 5.7 Incremental Sync Support

The fingerprint enables efficient incremental sync:
- Query by `component_hash` to find existing records
- Compare fingerprints; if match → skip
- If fingerprint differs, compare content_hash and relationship_hash to determine scope of update
- No need to load full records for change detection

---

## 6. Identity Strategy

### 6.1 Internal IDs

**What:** The `identity` field in the normalized document (SHA-256 hash).

**Properties:**
- 64-character hex string
- Not a database auto-increment or UUID
- Generated deterministically from natural key
- Never changes after first generation

### 6.2 Natural Keys

**What:** The `component_key` tuple `(type, api_name, namespace)`.

**Used by:**
- Cross-reference resolution in normalization
- Human-readable logging and debugging
- Query filters in Persistence and Graph

**Properties:**
- Unique within an organization
- Not globally unique across orgs (different orgs can have the same key)
- Stable across syncs

### 6.3 Composite Keys

**What:** `(organization_id, component_key)` or equivalently `(organization_id, identity)`.

**Used by:**
- Persistence primary key
- Cross-tenant isolation
- Partitioning strategy

### 6.4 Cross-tenant Uniqueness

Since `organization_id` is part of the composite key, components in different orgs never collide. The `identity` alone is globally unique only because SHA-256 provides collision resistance, but the composite key is the authoritative uniqueness constraint.

### 6.5 Cross-org Uniqueness

If an org reconnects with a different Salesforce org (different `organization_id`), all identities change because the hash includes `organization_id`. This is correct — the new org's metadata is distinct.

### 6.6 Cross-version Identity

The `component_hash` (identity) does NOT include version. A component at version 1 and version 2 have the same identity. Versioning is tracked separately via `version` field and `version_hash`.

### 6.7 Stable Identity Across Syncs

Identity stability relies on:
1. `organization_id` never changes for a given connection
2. `api_name` never changes for a given metadata component
3. `type` never changes for a given component
4. `namespace` never changes

If a component is renamed in Salesforce, the next sync produces a new identity. The old identity is orphaned and should be garbage-collected.

---

## 7. Relationship Normalization

Every canonical metadata type produces specific normalized relationships.

### 7.1 Object Relationships

```
MetadataObject "Account"
  ├── contains  → MetadataField "Account.Name"
  ├── contains  → MetadataField "Account.Industry"
  ├── contains  → MetadataValidationRule "Account.VAT_Validation"
  ├── contains  → MetadataRecordType "Account.Business"
  ├── references → MetadataLayout "Account.Account-Layout" (via object_api_name)
  ├── references → MetadataReport "Account Analysis" (via object_api_name)
  └── references → MetadataSharingRule "Account.SharingRule1" (via object_api_name)
```

**Normalization:** For each field, validation rule, record type — emit a `contains` relationship. For each layout, report, sharing rule referencing this object — emit a `referenced_by` relationship (or inverted `references` from the referencing component).

### 7.2 Field Relationships

```
MetadataField "Account.Industry"
  └── references → MetadataField "Account.Industry_Code__c" (via reference_to)
```

**Normalization:** If `reference_to` is populated, emit a `references` relationship to the target field/object.

### 7.3 Validation Rule Relationships

```
MetadataValidationRule "Account.VAT_Validation"
  ├── references → MetadataObject "Account" (via object_api_name)
  └── references → MetadataField "Account.VAT_Number__c" (derived from formula parsing)
```

**Normalization:** Emit `references` to the parent object. If formula references are parsed (optional), emit `references` to referenced fields.

### 7.4 Flow Relationships

```
MetadataFlow "Opportunity_Approval"
  ├── references → MetadataObject "Opportunity" (derived from flow variables)
  ├── references → MetadataApexClass "OpportunityHelper" (via subflow/class refs)
  ├── depends_on → MetadataFlow "Shared_Subflow" (via subflows)
  └── triggers   → MetadataObject "Opportunity" (via record_creates/updates/deletes)
```

**Normalization:** Extract object references from flow variables, `record_creates`, `record_updates`, `record_deletes`. Extract class references from class permissions. Extract subflow references from `subflows`.

### 7.5 Trigger Relationships

```
MetadataTrigger "AccountTrigger"
  ├── references → MetadataObject "Account" (via object_api_name)
  └── references → MetadataApexClass "AccountTrigger" (self, body contains class)
```

**Normalization:** Emit `references` to parent object. Optionally parse body for referenced classes.

### 7.6 Permission Set / Profile Relationships

```
MetadataPermissionSet "Finance"
  ├── references → MetadataObject "Account" (via object_permissions)
  ├── references → MetadataField "Account.Revenue__c" (via field_permissions)
  ├── references → MetadataApexClass "FinancialCalc" (via class_permissions)
  ├── references → MetadataLightningPage "Account-Record-Page" (via page_permissions)
  └── controls_access_to → MetadataObject "Account" (via object_permissions)
```

**Normalization:** Emit `references` for each permitted entity. Emit `controls_access_to` for objects with non-read permissions.

### 7.7 Report / Dashboard Relationships

```
MetadataReport "Account Analysis"
  └── references → MetadataObject "Account" (via object_api_name)

MetadataDashboard "Executive Overview"
  ├── references → MetadataReport "Account Analysis" (via components)
  └── references → MetadataReport "Revenue Forecast" (via components)
```

**Normalization:** Reports reference their primary object. Dashboards reference their source reports.

### 7.8 Layout / Record Type Relationships

```
MetadataLayout "Account-Account-Layout"
  ├── references → MetadataObject "Account" (via object_api_name)
  └── references → MetadataRecordType "Account.Business" (via record type assignments)

MetadataRecordType "Account.Business"
  └── references → MetadataObject "Account" (via object_api_name)
```

**Normalization:** Both reference the parent object directly.

### 7.9 Lightning Page Relationships

```
MetadataLightningPage "Account-Record-Page"
  └── references → MetadataObject "Account" (derived from page_type + assigned objects)
```

**Normalization:** Reference objects that this page is assigned to (if derivable).

### 7.10 Relationship Flattening Output

After normalization, every relationship becomes a `NormalizedRelationship` tuple. These tuples are:

- **Deduplicated**: identical `(type, target_identity)` pairs are collapsed
- **Directional**: each relationship has a clear source and target
- **Typed**: relationship types come from a controlled vocabulary
- **Self-contained**: no unresolved references (all targets have identities)

---

## 8. Persistence Boundary

### 8.1 What Persistence Receives

Persistence receives `NormalizedDocument` objects only. These are:

- `MetadataComponentDocument` — the base normalized record for every component
- Type-specific extensions — `NormalizedApexClass`, `NormalizedObject`, `NormalizedField`, etc.
- `NormalizedRelationship` — flattened adjacency list, separate from component records

**Persistence never receives:**
- Raw Salesforce JSON
- Canonical `MetadataComponent` objects
- Parser domain models
- Unresolved string references

### 8.2 Why

1. **Schema stability.** The normalized document schema is under our control. The canonical model schema evolves independently. Persistence should not break when canonical models gain new fields.

2. **Storage efficiency.** Normalized documents are flat, deduplicated, and ordered. Storing canonical nested objects directly would require complex serialization and prevent indexed queries on nested fields.

3. **Change detection.** Persistence stores the `fingerprint` alongside every row. Incremental sync compares fingerprints without deserializing full records. This is only possible because normalization pre-computes the fingerprint.

4. **Cross-consumer consistency.** Persistence, Graph, Search, and AI all hash, identify, and reference components the same way because normalization is shared.

### 8.3 Persistence Contract

```
Input:  list[NormalizedDocument]
Output: list[PersistResult(success, identity, fingerprint, action)]

Actions: insert | update | delete | skip
```

Persistence compares fingerprints to decide the action. If `fingerprint` matches the stored fingerprint, the record is skipped. If different, it's updated. If missing, it's inserted.

---

## 9. Graph Boundary

### 9.1 What Graph Receives

Graph receives a `NormalizedGraphInput` containing:

- A `list[NormalizedRelationship]` — typed, directed, deduplicated edges
- Component metadata for node display: `identity`, `type`, `api_name`, `label`, `qualified_name`, `fully_qualified_name`
- The `fingerprint` for cache invalidation

**Graph never receives:**
- Raw canonical models
- Unresolved string references
- Transient pipeline IDs

### 9.2 Why

1. **Graph is about structure, not content.** It does not need body text, field formulas, or validation rule error messages. It needs to know which components connect to which others.

2. **Resolved references.** Graph cannot resolve `object_api_name` strings into node references. Normalization does this once. Graph consumes already-resolved edges.

3. **Deduplicated edges.** If a canonical model lists the same relationship twice (possible due to mapper bugs or data quality), normalization deduplicates before Graph sees it.

### 9.3 Graph Contract

```
Input:  NormalizedGraphInput( nodes, edges, fingerprint )
Output: GraphResult( nodes_added, nodes_removed, edges_added, edges_removed )
```

---

## 10. Search Boundary

### 10.1 What Search Receives

Search receives `NormalizedSearchDocument` containing:

| Field | Purpose |
|-------|---------|
| `identity` | Document ID |
| `type` | Metadata type (filter facet) |
| `api_name` | API name (exact match) |
| `label` | Display label (fuzzy match) |
| `qualified_name` | Qualified name (exact + prefix) |
| `fully_qualified_name` | FQDN for cross-org search |
| `description` | Description text (full-text) |
| `namespace` | Namespace (filter) |
| `status` | Status (filter) |
| `body` | Code/formula content (full-text, truncated) |
| `tags` | Auto-generated search tokens |
| `keywords` | Extracted keywords from labels, descriptions |
| `aliases` | Known aliases from relationship traversal |
| `fingerprint` | Cache invalidation token |

**Search never receives:**
- Canonical models
- Binary content
- Full dependency graphs

### 10.2 Why

1. **Search is about discoverability, not fidelity.** It needs enough context to find and rank results, but does not need the full metadata payload.

2. **Token generation is normalization's job.** Extracting search tokens from descriptions, labels, and relationships is a deterministic transformation that must occur once.

3. **Truncation boundaries.** Content bodies (Apex class code, Flow XML) may be megabytes. Search should index a truncated preview, not the full body.

### 10.3 Search Contract

```
Input:  NormalizedSearchDocument[]
Output: SearchIndexResult( indexed_count, errors )
```

---

## 11. AI Boundary

### 11.1 How Normalized Metadata Becomes AI Context

The AI subsystem consumes normalized metadata through a `ContextBuilder` that:

1. **Retrieves** normalized documents by component key or identity
2. **Resolves references** by following `NormalizedRelationship` chains
3. **Builds context windows** by concatenating resolved documents into structured text
4. **Stamps staleness** by including `fingerprint` in context (AI can detect outdated information)
5. **Prunes irrelevant detail** by filtering relationships and properties based on the query

### 11.2 Context Generation

```
Prompt = f"""
Component: {normalized_doc.api_name}
Type: {normalized_doc.type}
Description: {normalized_doc.description or '(none)'}

Relationships:
{formatted_relationships}

Body:
{truncated_body(2000)}
"""
```

### 11.3 Why Normalized Models Are Preferable

1. **Resolved references.** AI never sees `object_api_name="Account"` that it cannot resolve. Normalization provides `target_identity` and `target_fqdn` for every reference.

2. **Deterministic context.** The same component always produces the same context. AI can cache reasoning about a component.

3. **Controlled size.** Normalization truncates and prunes, preventing prompt overflow.

4. **Relationship traversal.** AI can ask "what depends on this?" and the answer is a pre-computed, deduplicated relationship list.

---

## 12. Performance & Scalability

### 12.1 Batch Normalization

The normalizer processes a batch of canonical components in a single pass:

```
for each component in batch:
    identity = hash(org_id, platform, type, api_name)
    fingerprint = hash(content, relationships)
    normalized = flatten(component, identity, fingerprint)
    batch_collector.append(normalized)

# Second pass for cross-references
for each normalized in batch_collector:
    resolve_references(normalized, batch_index)
    deduplicate_relationships(normalized)
    deterministically_sort_collections(normalized)
```

**Complexity:** O(N log N) due to sorting. O(N) for all other operations.

### 12.2 Streaming Normalization

For large orgs (10,000+ components), the normalizer can operate in a streaming mode:

1. **Phase 1:** Compute identities and fingerprints for all components (map-only, no sorting needed)
2. **Phase 2:** Collect all component keys into a trie for cross-reference resolution
3. **Phase 3:** Flatten, sort, deduplicate, and emit each normalized document

Memory peaks during Phase 2 (the key index), which is proportional to the number of unique component keys (~100 bytes per key → ~1 MB for 10,000 keys).

### 12.3 Memory Usage

| Operation | Memory per Component | Notes |
|-----------|---------------------|-------|
| Identity computation | ~256 bytes | SHA-256 state |
| Fingerprint computation | ~component size | Full serialization |
| Flattening | ~2x component size | Intermediate representation |
| Reference resolution | ~100 bytes per key | Key index entry |
| Final output | ~component size | Serialized normalized document |

For a 100,000-component org with average 2 KB per component:
- Peak memory: ~200 MB (intermediate) + 10 MB (key index)
- Final output: ~200 MB

### 12.4 Parallel Execution

Normalization is embarrassingly parallel at the batch level. Each batch can be processed independently:

```
ThreadPoolExecutor(max_workers=4):
    for each batch:
        future = submit(normalize_batch, batch)
```

Cross-batch reference resolution requires a shared key index (concurrent dict) or a post-processing pass.

### 12.5 Caching Opportunities

| Cache Key | Cache Value | Benefit |
|-----------|-------------|---------|
| `(org_id, type, api_name)` | `identity` | Avoid recomputing hashes for unchanged components |
| `identity` | `fingerprint` | Fast staleness check without full normalization |
| `(org_id, platform)` | `SourcePlatform` instance | Singleton reuse |

Identity caching is the highest-value cache. For incremental sync, ~95% of components are unchanged. Caching identities avoids ~95% of normalization work.

### 12.6 Large Org Processing

For orgs with 100,000+ metadata components:

1. **Batch by type:** Process all Apex classes together, then all objects, etc. Enables type-specific normalization logic to be loaded once.
2. **Two-pass reference resolution:** First pass computes identities for all components. Second pass resolves references using a shared key index.
3. **Streaming output:** Write normalized documents to a staging area as they complete, rather than holding the full output in memory.
4. **Backpressure:** The normalizer respects downstream consumer throughput via bounded buffer queues.

---

## 13. Error Handling

### 13.1 Recoverable Failures

| Failure | Handling | Effect |
|---------|----------|--------|
| Missing optional field | Apply default value | Component normalized with defaults |
| Unrecognized metadata type | Emit warning, use generic base document | Component stored as generic, graph edges skipped |
| Failed relationship resolution | Skip the relationship, emit warning | Component normalized, relationship dropped |
| Collection contains null | Filter nulls, emit debug log | Component normalized without null entries |

### 13.2 Fatal Failures

| Failure | Handling | Effect |
|---------|----------|--------|
| Missing required field (`api_name`, `type`) | Raise, fail the batch | Batch not normalized, error in pipeline context |
| Null component in input | Skip, emit error | Component omitted from batch |
| Hash computation failure | Raise, fail the batch | Batch not normalized |
| Key index inconsistency | Raise, fail the batch | Batch not normalized |

### 13.3 Skipped Records

Components that fail normalization are recorded in `context.normalization_errors` with:
- Component identity (if derivable)
- Error code and message
- Severity

Skipped records are NOT added to `context.normalized_components`.

### 13.4 Partial Batches

If a batch of 1000 components has 3 normalization failures:
- 3 are reported as errors
- 997 are normalized and added to `context.normalized_components`
- Pipeline continues with 997 components

### 13.5 Logging

| Event | Level | Payload |
|-------|-------|---------|
| Normalization start | INFO | batch_size, component_type |
| Component normalized | DEBUG | identity, type, api_name |
| Component skipped | WARNING | identity/type/api_name, error_code |
| Relationship skipped | WARNING | source_identity, target_key, reason |
| Batch complete | INFO | total, normalized, skipped, elapsed_ms |
| Fatal failure | ERROR | error, batch_range |

### 13.6 Metrics

| Metric | Type | Purpose |
|--------|------|---------|
| `normalizer.components.total` | Counter | Total components processed |
| `normalizer.components.normalized` | Counter | Successfully normalized |
| `normalizer.components.skipped` | Counter | Skipped due to errors |
| `normalizer.relationships.total` | Counter | Total relationships processed |
| `normalizer.relationships.deduplicated` | Counter | Deduplicated relationships |
| `normalizer.batch.duration_ms` | Histogram | Batch processing time |
| `normalizer.batch.size` | Histogram | Batch size distribution |
| `normalizer.memory.peak_bytes` | Gauge | Peak memory during normalization |

### 13.7 Tracing

Each normalization batch produces a trace span:
- `normalize_batch` — parent span
  - `compute_identities` — identity generation for all components
  - `build_key_index` — key index construction
  - `normalize_component` — per-component flattening (one child span per component)
  - `resolve_references` — cross-reference resolution
  - `sort_and_deduplicate` — final ordering pass

---

## 14. Backward Compatibility

The normalization layer introduces zero changes to existing components:

| Component | Impact |
|-----------|--------|
| OAuth | Unchanged. Normalization occurs after auth. |
| Authentication | Unchanged. |
| Metadata Download | Unchanged. Normalization occurs after download. |
| Parser | Unchanged. Normalization receives canonical models, not parser output. |
| Canonical Mapper | Unchanged. Normalization receives mapper output. |
| Validator | Unchanged. Normalization receives validated canonical models. |
| Persistence APIs | Unchanged. Normalization contract matches existing expectations. |
| Graph APIs | Unchanged. Normalization produces the same edge format. |
| Search APIs | Unchanged. Normalization produces the same document format. |
| AI APIs | Unchanged. Normalization produces the same context format. |

**Stage order change:** NormalizationStage is already in the pipeline (placeholder), positioned correctly after ValidationStage. No pipeline reconfiguration needed.

**PipelineContext changes required:**
- Add `normalized_components: list[NormalizedDocument]`
- Add `normalization_errors: list[str]`

---

## 15. Implementation Roadmap

### Story N1: Normalization Data Models

**Objective:** Define `NormalizedDocument`, `NormalizedRelationship`, `ComponentKey`, and type-specific normalized documents as frozen dataclasses/Pydantic models.

**Files:**
- `backend/src/sfir_backend/application/pipeline/normalizer/normalized_model.py`
- `backend/src/sfir_backend/application/pipeline/normalizer/__init__.py`

**Dependencies:** None (pure data model).

**Acceptance Criteria:**
- `NormalizedDocument` base class with all required fields
- `NormalizedRelationship` with type, target_identity, target_component_key, target_fqdn
- `ComponentKey` with type, api_name, namespace
- Type-specific models for each canonical type (ApexClass, Object, Field, etc.)
- Deterministic serialization (sorted keys, no None values)

**Verification:** Unit tests for construction, serialization, field defaults.

**Risk:** Low.

---

### Story N2: Identity & Hashing Engine

**Objective:** Implement `IdentityService` and `FingerprintService` with all hash algorithms.

**Files:**
- `backend/src/sfir_backend/application/pipeline/normalizer/identity_service.py`
- `backend/src/sfir_backend/application/pipeline/normalizer/fingerprint_service.py`

**Dependencies:** Story N1.

**Acceptance Criteria:**
- `compute_component_hash(org_id, platform, type, api_name, namespace) → str`
- `compute_content_hash(component) → str`
- `compute_relationship_hash(relationships) → str`
- `compute_fingerprint(content_hash, relationship_hash) → str`
- All hashes are deterministic (same input → same output)
- Cross-org inputs produce different hashes

**Verification:** Property-based tests for determinism, collision resistance validation.

**Risk:** Low.

---

### Story N3: Normalization Rule Engine

**Objective:** Implement `NormalizationRule` interface and core normalization rules.

**Files:**
- `backend/src/sfir_backend/application/pipeline/normalizer/i_normalization_rule.py`
- `backend/src/sfir_backend/application/pipeline/normalizer/rules/`

**Dependencies:** Stories N1, N2.

**Acceptance Criteria:**
- `INormalizationRule` interface with `can_handle` and `normalize`
- Rules for string normalization, collection ordering, collection deduplication
- Rules for null handling, default values, timestamp normalization
- Rules for version normalization, status normalization, metadata type normalization
- Rules for qualified name generation, FQDN generation
- Rules for namespace handling

**Verification:** Unit tests for each rule independently (determinism, edge cases).

**Risk:** Low.

---

### Story N4: Relationship Normalizer

**Objective:** Build relationship extraction and normalization logic for all metadata types.

**Files:**
- `backend/src/sfir_backend/application/pipeline/normalizer/relationship_normalizer.py`
- `backend/src/sfir_backend/application/pipeline/normalizer/rules/relationships/`

**Dependencies:** Stories N1, N2, N3.

**Acceptance Criteria:**
- Extract `contains` relationships from parent-child hierarchies (objects → fields)
- Extract `references` relationships from `object_api_name` fields
- Extract `references` relationships from permission sets (object, field, class, page perms)
- Extract `references` relationships from flows (record operations, subflows)
- Extract `references` from reports, dashboards, layouts, record types
- Extract `controls_access_to` from permission sets with write/delete permissions
- Detect and handle circular parent_role in roles
- Deduplicate relationships by `(type, target_identity)`
- Reference deduplication: identical relationships collapsed

**Verification:** Integration tests with realistic canonical models.

**Risk:** Medium. Complex relationship extraction logic, especially for flows and permission sets.

---

### Story N5: CanonicalNormalizer Implementation

**Objective:** Implement the `CanonicalNormalizer` (registry of normalization rules + relationship normalizer).

**Files:**
- `backend/src/sfir_backend/application/pipeline/normalizer/canonical_normalizer.py`

**Dependencies:** Stories N1–N4.

**Acceptance Criteria:**
- `CanonicalNormalizer` accepts list of canonical components
- Applies all normalization rules in order
- Runs relationship normalizer
- Produces `NormalizationReport` with valid and invalid components
- Handles empty input gracefully
- Handles rule failures gracefully (log and continue)
- Deterministic: same input → same output
- Batch processing with stable ordering

**Verification:** Property-based tests for determinism, regression tests for each rule.

**Risk:** Low.

---

### Story N6: NormalizationStage Implementation

**Objective:** Implement the `NormalizationStage` that wires the normalizer into the pipeline.

**Files:**
- `backend/src/sfir_backend/application/pipeline/stages/normalization_stage.py` (modify existing)

**Dependencies:** Story N5.

**Acceptance Criteria:**
- Replaces `raise NotImplementedError`
- Accepts `CanonicalNormalizer`
- Reads `context.canonical_components`
- Writes `context.normalized_components` and `context.normalization_errors`
- Produces warnings for skipped records
- Produces errors for fatal failures
- Handles empty canonical_components gracefully

**Verification:** Integration tests with PipelineContext.

**Risk:** Low.

---

### Story N7: Container Wiring

**Objective:** Register the normalizer and its dependencies in the DI container.

**Files:**
- `backend/src/sfir_backend/config/container.py` (modify existing)

**Dependencies:** Story N6.

**Acceptance Criteria:**
- `_make_canonical_normalizer()` registers all rules
- NormalizationStage wired with normalizer
- Pipeline order: Parser → CanonicalMapper → ValidationStage → **NormalizationStage** → PersistenceStage → GraphStage → SearchStage

**Verification:** Container startup test.

**Risk:** Low.

---

### Story N8: PipelineContext Update

**Objective:** Add `normalized_components` and `normalization_errors` to PipelineContext.

**File:**
- `backend/src/sfir_backend/application/pipeline/pipeline_context.py` (modify existing)

**Dependencies:** Story N1.

**Acceptance Criteria:**
- `normalized_components: list[NormalizedDocument]`
- `normalization_errors: list[str]`
- Existing fields unchanged
- No import cycles

**Verification:** Unit tests for PipelineContext construction.

**Risk:** Low.

---

### Story N9: Performance Testing

**Objective:** Validate batch normalization performance with realistic data volumes.

**Files:** Test files only.

**Dependencies:** Story N6.

**Acceptance Criteria:**
- 100,000 components normalized in < 10 seconds
- Peak memory < 500 MB for 100,000 components
- 1000-component batch normalized in < 100 ms
- Incremental sync (10,000 new, 90,000 cached) processes in < 2 seconds

**Verification:** Performance benchmark tests.

**Risk:** Low. Normalization is CPU-bound, not I/O-bound. SHA-256 is hardware-accelerated on modern CPUs.

---

### Story N10: Integration Testing

**Objective:** End-to-end test: canonical mapper → validator → normalizer.

**Files:** Test files only.

**Dependencies:** Story N6.

**Acceptance Criteria:**
- Full flow produces normalized documents with correct identities, fingerprints, relationships
- Fingerprint changes when content changes
- Fingerprint unchanged when only ordering changes
- Relationships correctly resolved across types
- Mixed valid/invalid batch produces correct split

**Verification:** Integration tests.

**Risk:** Low.

---

## 16. Sequence Diagram

```
Pipeline                     NormalizationStage          CanonicalNormalizer       IdentityService      FingerprintService
    │                              │                          │                        │                     │
    │  context.canonical_components │                          │                        │                     │
    │─────────────────────────────>│                          │                        │                     │
    │                              │  normalize(batch)        │                        │                     │
    │                              │─────────────────────────>│                        │                     │
    │                              │                          │  compute_component_hash │                     │
    │                              │                          │────────────────────────>│                     │
    │                              │                          │<────────────────────────│                     │
    │                              │                          │                        │                     │
    │                              │                          │  for each component:    │                     │
    │                              │                          │    apply rules          │                     │
    │                              │                          │    flatten fields       │                     │
    │                              │                          │    sort collections     │                     │
    │                              │                          │    deduplicate          │                     │
    │                              │                          │                        │                     │
    │                              │                          │  normalize relationships│                     │
    │                              │                          │    extract edges        │                     │
    │                              │                          │    resolve targets      │                     │
    │                              │                          │    deduplicate edges    │                     │
    │                              │                          │                        │                     │
    │                              │                          │  compute_fingerprint    │                     │
    │                              │                          │──────────────────────────────────────────────>│
    │                              │                          │<──────────────────────────────────────────────│
    │                              │                          │                        │                     │
    │                              │  ValidationReport        │                        │                     │
    │                              │<─────────────────────────│                        │                     │
    │                              │                          │                        │                     │
    │  context.normalized_components│                          │                        │                     │
    │<─────────────────────────────│                          │                        │                     │
    │                              │                          │                        │                     │
    │  [continue to Persistence]   │                          │                        │                     │
```

---

## 17. Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Normalization Layer                                  │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                        NormalizationStage                              │   │
│  │  ┌───────────┐   ┌──────────────┐   ┌──────────────────┐            │   │
│  │  │   Input   │   │    Execute   │   │  Output Mapping  │            │   │
│  │  │ (context) │──>│  (delegates) │──>│ (context update) │            │   │
│  │  └───────────┘   └──────────────┘   └──────────────────┘            │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                      CanonicalNormalizer                              │   │
│  │                                                                       │   │
│  │  ┌─────────────────┐  ┌──────────────────┐  ┌────────────────────┐   │   │
│  │  │  Rule Engine    │  │  Relationship    │  │  Hashing Engine   │   │   │
│  │  │                 │  │  Normalizer      │  │                   │   │   │
│  │  │  ┌───────────┐  │  │                  │  │  ┌─────────────┐  │   │   │
│  │  │  │ Rule 1    │  │  │  Extract edges   │  │  │ Identity    │  │   │   │
│  │  │  │ Rule 2    │  │  │  Resolve targets │  │  │ Service     │  │   │   │
│  │  │  │ ...       │  │  │  Deduplicate     │  │  └─────────────┘  │   │   │
│  │  │  │ Rule N    │  │  │                  │  │  ┌─────────────┐  │   │   │
│  │  │  └───────────┘  │  │                  │  │  │ Fingerprint │  │   │   │
│  │  └─────────────────┘  └──────────────────┘  │  │ Service     │  │   │   │
│  │                                              │  └─────────────┘  │   │   │
│  │                                              └────────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                        Normalized Models                              │   │
│  │                                                                       │   │
│  │  ┌──────────────────┐  ┌────────────────────┐  ┌──────────────────┐   │   │
│  │  │ Normalized       │  │ Normalized         │  │ Normalized       │   │   │
│  │  │ Document         │  │ Relationship       │  │ ComponentKey     │   │   │
│  │  │ (Pydantic Base)  │  │ (Dataclass)        │  │ (Dataclass)      │   │   │
│  │  └──────────────────┘  └────────────────────┘  └──────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                    ┌───────────────┼───────────────┐
                    │               │               │
                    ▼               ▼               ▼
            ┌────────────┐  ┌────────────┐  ┌────────────┐
            │Persistence │  │   Graph    │  │   Search   │
            │   Stage    │  │   Stage    │  │   Stage    │
            └────────────┘  └────────────┘  └────────────┘
```

---

## 18. Class Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    PipelineStage (ABC)                          │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ + name: str                                              │ │
│  │ + execute(context: PipelineContext) -> PipelineContext    │ │
│  └───────────────────────────────────────────────────────────┘ │
└─────────────────────────┬───────────────────────────────────────┘
                          │ inherits
┌─────────────────────────────────────────────────────────────────┐
│                      NormalizationStage                          │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ - normalizer: ICanonicalNormalizer                        │ │
│  │ + __init__(normalizer)                                    │ │
│  │ + name -> "normalization"                                 │ │
│  │ + execute(context) -> context                             │ │
│  └───────────────────────────────────────────────────────────┘ │
└─────────────────────────┬───────────────────────────────────────┘
                          │ uses
┌─────────────────────────────────────────────────────────────────┐
│                   ICanonicalNormalizer (ABC)                     │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ + normalize(components) -> NormalizationReport            │ │
│  └───────────────────────────────────────────────────────────┘ │
└─────────────────────────┬───────────────────────────────────────┘
                          │ implements
┌─────────────────────────────────────────────────────────────────┐
│                    CanonicalNormalizer                            │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ - rules: list[INormalizationRule]                         │ │
│  │ - relationship_normalizer: RelationshipNormalizer          │ │
│  │ - identity_service: IdentityService                       │ │
│  │ - fingerprint_service: FingerprintService                 │ │
│  │ + register(rule)                                          │ │
│  │ + normalize(components) -> NormalizationReport            │ │
│  └───────────────────────────────────────────────────────────┘ │
└──────────────┬──────────────────────┬──────────────────────────┘
               │ uses                │ uses
               ▼                     ▼
┌────────────────────────┐  ┌────────────────────────┐
│   INormalizationRule   │  │ IdentityService        │
│        (ABC)           │  └────────────────────────┘
│ + can_handle(comp) bool│  ┌────────────────────────┐
│ + normalize(comp)      │  │ FingerprintService     │
└────────────────────────┘  └────────────────────────┘
               │
               │ implements (many)
               ▼
┌─────────────────────────────────────────────────┐
│  StringNormalizationRule                        │
│  CollectionOrderingRule                          │
│  CollectionDeduplicationRule                     │
│  NullHandlingRule                                │
│  DefaultValueRule                                │
│  TimestampNormalizationRule                      │
│  VersionNormalizationRule                        │
│  StatusNormalizationRule                         │
│  TypeNormalizationRule                           │
│  QualifiedNameRule                               │
│  FqdnRule                                       │
│  NamespaceRule                                   │
│  FlatteningRule                                  │
│  ...                                            │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    RelationshipNormalizer                        │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ - extractors: dict[type, RelationshipExtractor]           │ │
│  │ + extract(component, key_index) -> list[NormalizedRel]    │ │
│  │ + deduplicate(relationships) -> list[NormalizedRel]       │ │
│  └───────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                  NormalizationReport (Dataclass)                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ + normalized: list[NormalizedDocument]                    │ │
│  │ + skipped: list[tuple[component, list[ErrorRecord]]]      │ │
│  │ + errors: list[str]                                       │ │
│  └───────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                   NormalizedDocument (Pydantic)                  │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │ identity: str                                             │ │
│  │ component_key: ComponentKey                               │ │
│  │ type: str                                                 │ │
│  │ api_name: str                                             │ │
│  │ qualified_name: str                                       │ │
│  │ fully_qualified_name: str                                 │ │
│  │ label: str | None                                         │ │
│  │ namespace: str | None                                     │ │
│  │ description: str | None                                   │ │
│  │ version: int                                              │ │
│  │ status: str                                               │ │
│  │ source_platform: str                                      │ │
│  │ organization_id: str                                      │ │
│  │ owner_id: str | None                                      │ │
│  │ created_at: str | None                                    │ │
│  │ updated_at: str | None                                    │ │
│  │ fingerprint: str                                          │ │
│  │ content_hash: str                                         │ │
│  │ properties: dict[str, Any]                                │ │
│  │ relationships: list[NormalizedRelationship]                │ │
│  │ normalized_at: str                                        │ │
│  └───────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## 19. Risk & Trade-off Analysis

### 19.1 Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Identity collision (two distinct components produce same hash) | Very low (SHA-256 collision resistance) | Catastrophic (data corruption) | Use composite key `(org_id, identity)` as authoritative unique constraint. Collision would require same org, same platform, same type, same api_name, same namespace — which means they ARE the same component. |
| Relationship extraction misses edge cases for complex types (flows, permission sets) | Medium | Medium | Start with well-defined extractors (object_api_name-based). Add complex extractors iteratively with thorough testing. Use fallback: if no extractor registered for a type, emit no relationships. |
| Performance regression from deterministic sorting at scale | Low | Medium | Sorting is O(N log N). For 100K components, sorting 1000-element lists 10000 times is ~10M comparisons. Python's TimSort handles this in < 1 second. |
| Fingerprint changes when no semantic change occurred | Low | Low | Caused by non-deterministic serialization (dict key order, set iteration). Mitigated by using sorted-key JSON and sorted collections in normalization. |

### 19.2 Trade-offs

| Decision | Alternative | Rationale |
|----------|-------------|-----------|
| SHA-256 for hashing | UUIDv5, MD5, custom hash | SHA-256 provides cryptographic collision resistance at low cost. UUIDv5 is shorter but requires a namespace UUID. MD5 is faster but deprecated. |
| Normalized documents as Pydantic models | Dataclasses, TypedDict, Protocol | Pydantic provides validation, serialization, and schema generation. Dataclasses lack validation. TypedDicts are structurally typed but add no runtime safety. |
| Identity based on natural key | Database auto-increment, UUID4 | Natural key identity survives re-syncs. Auto-increment IDs are ephemeral. UUID4 is non-deterministic. |
| Two-pass normalization | Single-pass with lazy resolution | Two-pass is required for cross-reference resolution. Lazy resolution would leave dangling references that Persistence/Graph must resolve. |
| Flattening relationships into separate records | Storing nested hierarchies | Separate records enable indexed queries, partial updates, and graph traversal. Nested hierarchies require full-document reads for any relationship query. |

---

## 20. Architecture Readiness Assessment

### 20.1 Design Completeness

| Aspect | Status |
|--------|--------|
| Normalized data model | ✅ Fully specified with field-level rationale |
| Normalization rules | ✅ 20 rules defined with algorithm and purpose |
| Identity strategy | ✅ Natural-key-based deterministic hashing |
| Relationship normalization | ✅ Per-type extraction specified for all supported types |
| Hashing strategy | ✅ Component, content, relationship, version, fingerprint |
| Persistence boundary | ✅ Clear contract defined |
| Graph boundary | ✅ Clear contract defined |
| Search boundary | ✅ Clear contract defined |
| AI boundary | ✅ Clear contract defined |
| Performance considerations | ✅ Batch, streaming, caching, large org |
| Error handling | ✅ Recoverable, fatal, logging, metrics, tracing |
| Implementation roadmap | ✅ 10 stories with dependencies and acceptance criteria |

### 20.2 Key Architectural Decisions (ADRs)

1. **ADR-NORM-1:** Normalized models are separate from canonical models. They share no base class. Rationale: prevents coupling between normalization and downstream consumer schemas.

2. **ADR-NORM-2:** Identities are SHA-256 hashes of `(org_id, platform, type, api_name, namespace)`. Rationale: deterministic, stable across syncs, globally unique within org scope.

3. **ADR-NORM-3:** Normalization is stateless. No caching, no database lookups, no external service calls. Rationale: pure function guarantees determinism and simplifies testing.

4. **ADR-NORM-4:** Relationships are flattened and stored separately from component records. Rationale: enables Graph to query edges without loading component payloads.

5. **ADR-NORM-5:** All collections are deterministically sorted before output. Rationale: guarantees idempotent fingerprints and simplifies change detection.

### 20.3 Dependencies

| Dependency | Type | Description |
|------------|------|-------------|
| Canonical metadata models | Internal | Input models from `domain.canonical` |
| PipelineContext | Internal | Stage input/output contract |
| PipelineStage | Internal | Base class for NormalizationStage |
| SHA-256 (`hashlib`) | Standard library | Hash computation |
| Pydantic | Third-party | Normalized document model validation |
| structlog | Third-party | Structured logging |

### 20.4 Open Questions

1. **Formula parsing.** Should the normalizer attempt to parse validation rule/flow formulas to extract field references? Initial scope: no. Add as enhancement story if needed.

2. **Truncation limits.** What is the maximum body length for Search indexing? Initial: 10,000 characters. Configurable via settings.

3. **Relationship types.** Are `triggers`, `validates`, `manages` needed as distinct relationship types, or are `references` and `contains` sufficient? Initial: use `references` and `contains` only. Extend vocabulary as Graph requirements mature.

### 20.5 Conclusion

The normalization architecture is ready for implementation. The design addresses all downstream consumer requirements, provides deterministic change detection via hashing, maintains backward compatibility, and defines clear boundaries between subsystems. The implementation roadmap decomposes the work into 10 independently deliverable stories with well-defined acceptance criteria.

**Recommendation:** Proceed with Story N1 (Normalization Data Models) immediately.
