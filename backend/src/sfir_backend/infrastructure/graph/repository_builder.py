"""Repository-fed Dependency Graph builder.

Phase 4: The Metadata Repository is the ONLY source of metadata. This builder
never queries Salesforce and never touches parsers/extractors. Every node and
every edge is derived deterministically from verified canonical metadata that
already exists in the repository.

Edge derivation mirrors the deterministic reference patterns used by the
Metadata Validation & Consistency Engine (``validation_rules.py``) — the exact
same conservative rules, applied to build a graph instead of emitting findings.
The rules intentionally only create an edge when the target component is
present in the loaded set (no invented edges).
"""

from __future__ import annotations

import logging
import re
from typing import Any, ClassVar

from sfir_backend.domain.canonical.base import (
    CanonicalRelationship,
    FieldType,
    MetadataComponent,
    RelationshipType,
)
from sfir_backend.domain.graph.models import (
    EdgeType,
    Graph,
    GraphEdge,
    GraphNode,
    NodeType,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type vocabulary
# ---------------------------------------------------------------------------

# Canonical PascalCase types (repository read-path vocabulary).
_PASCAL_TYPES: frozenset[str] = frozenset({
    "ApexClass", "Trigger", "Object", "Field", "Relationship", "GlobalValueSet",
    "ValidationRule", "Formula", "Flow", "FlowVersion", "Layout", "RecordType",
    "Profile", "PermissionSet", "Role", "Queue", "PublicGroup", "SharingRule",
    "EmailTemplate", "NamedCredential", "ConnectedApp", "Report", "Dashboard",
    "LightningPage", "QuickAction", "CustomMetadata", "CustomSetting",
    "Workflow", "ApprovalProcess",
})

_SNAKE_TO_PASCAL: dict[str, str] = {
    "apex_class": "ApexClass",
    "trigger": "Trigger",
    "object": "Object",
    "field": "Field",
    "relationship": "Relationship",
    "global_value_set": "GlobalValueSet",
    "validation_rule": "ValidationRule",
    "formula": "Formula",
    "flow": "Flow",
    "flow_version": "FlowVersion",
    "layout": "Layout",
    "record_type": "RecordType",
    "profile": "Profile",
    "permission_set": "PermissionSet",
    "role": "Role",
    "queue": "Queue",
    "public_group": "PublicGroup",
    "sharing_rule": "SharingRule",
    "email_template": "EmailTemplate",
    "named_credential": "NamedCredential",
    "connected_app": "ConnectedApp",
    "report": "Report",
    "dashboard": "Dashboard",
    "lightning_page": "LightningPage",
    "quick_action": "QuickAction",
    "custom_metadata": "CustomMetadata",
    "custom_setting": "CustomSetting",
    "workflow": "Workflow",
    "approval_process": "ApprovalProcess",
}

_PASCAL_TO_SNAKE: dict[str, str] = {v: k for k, v in _SNAKE_TO_PASCAL.items()}

# Component types that MUST reference a parent object by api_name.
_OBJECT_REFERENCE_TYPES: dict[str, tuple[str, ...]] = {
    "Field": ("object_api_name",),
    "ValidationRule": ("object_api_name",),
    "Trigger": ("object_api_name",),
    "Formula": ("object_api_name",),
    "Layout": ("object_api_name",),
    "RecordType": ("object_api_name",),
    "Report": ("object_api_name",),
    "Workflow": ("object_api_name",),
    "ApprovalProcess": ("object_api_name",),
    "SharingRule": ("object_api_name",),
    "QuickAction": ("object_api_name",),
    "CustomSetting": ("object_api_name",),
}

# Map canonical PascalCase type -> graph NodeType.
_NODE_TYPE_MAP: dict[str, NodeType] = {
    "ApexClass": NodeType.APEX_CLASS,
    "Trigger": NodeType.TRIGGER,
    "Object": NodeType.OBJECT,
    "Field": NodeType.FIELD,
    "Relationship": NodeType.RELATIONSHIP,
    "GlobalValueSet": NodeType.GLOBAL_VALUE_SET,
    "ValidationRule": NodeType.VALIDATION_RULE,
    "Formula": NodeType.FORMULA,
    "Flow": NodeType.FLOW,
    "FlowVersion": NodeType.FLOW_VERSION,
    "Layout": NodeType.LAYOUT,
    "RecordType": NodeType.RECORD_TYPE,
    "Profile": NodeType.PROFILE,
    "PermissionSet": NodeType.PERMISSION_SET,
    "Role": NodeType.ROLE,
    "Queue": NodeType.QUEUE,
    "PublicGroup": NodeType.PUBLIC_GROUP,
    "SharingRule": NodeType.SHARING_RULE,
    "EmailTemplate": NodeType.EMAIL_TEMPLATE,
    "NamedCredential": NodeType.NAMED_CREDENTIAL,
    "ConnectedApp": NodeType.CONNECTED_APP,
    "Report": NodeType.REPORT,
    "Dashboard": NodeType.DASHBOARD,
    "LightningPage": NodeType.LIGHTNING_PAGE,
    "QuickAction": NodeType.QUICK_ACTION,
    "CustomMetadata": NodeType.CUSTOM_METADATA,
    "CustomSetting": NodeType.CUSTOM_SETTING,
    "Workflow": NodeType.WORKFLOW,
    "ApprovalProcess": NodeType.APPROVAL_PROCESS,
}

# Map canonical RelationshipType -> graph EdgeType.
_RELATIONSHIP_EDGE_MAP: dict[RelationshipType, EdgeType] = {
    RelationshipType.CONTAINS: EdgeType.CONTAINS,
    RelationshipType.REFERENCES: EdgeType.REFERENCES,
    RelationshipType.DEPENDS_ON: EdgeType.DEPENDS_ON,
    RelationshipType.IMPLEMENTS: EdgeType.IMPLEMENTS,
    RelationshipType.EXTENDS: EdgeType.EXTENDS,
    RelationshipType.MANAGES: EdgeType.USES,
    RelationshipType.CONTROLS_ACCESS_TO: EdgeType.USES_PERMISSION,
    RelationshipType.TRIGGERS: EdgeType.USES_TRIGGER,
    RelationshipType.VALIDATES: EdgeType.USES_FIELD,
}

# Apex source patterns (deterministic, regex-based — no AI).
_APEX_EXTENDS_RE = re.compile(
    r"\b(?:virtual\s+|abstract\s+|global\s+|public\s+)?class\s+\w+\s+extends\s+(\w+)",
    re.IGNORECASE,
)
_APEX_IMPLEMENTS_RE = re.compile(
    r"\b(?:virtual\s+|abstract\s+|global\s+|public\s+)?class\s+\w+"
    r"(?:\s+extends\s+\w+)?\s+implements\s+([\w\s,]+)",
    re.IGNORECASE,
)
_SOQL_FROM_RE = re.compile(
    r"\bFROM\s+([A-Za-z_]\w*)\b",
    re.IGNORECASE,
)


def to_pascal_type(raw: str) -> str:
    """Normalize a type name to the canonical PascalCase vocabulary."""
    return _SNAKE_TO_PASCAL.get(raw, raw)


def to_snake_type(raw: str) -> str:
    """Normalize a type name to the snake_case vocabulary."""
    return _PASCAL_TO_SNAKE.get(raw, raw)


# ---------------------------------------------------------------------------
# Property helpers (self-contained mirror of validation_rules helpers)
# ---------------------------------------------------------------------------


def _camel_case(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _snake_case(name: str) -> str:
    out: list[str] = []
    for ch in name:
        if ch.isupper():
            out.append("_")
            out.append(ch.lower())
        else:
            out.append(ch)
    return "".join(out)


def read_prop(component: MetadataComponent, *aliases: str, default: Any = None) -> Any:
    """Read a type-specific property from a component.

    Resolution order:
      1. ``metadata_properties`` exact key
      2. ``metadata_properties`` camelCase / snake_case / lowercase variant
      3. typed attribute on the component (works for direct-save test fixtures)
    """
    props = component.metadata_properties or {}
    for alias in aliases:
        if alias in props and props[alias] is not None:
            return props[alias]
    for alias in aliases:
        variants = {_camel_case(alias), _snake_case(alias), alias.lower()}
        for variant in variants:
            if variant in props and props[variant] is not None:
                return props[variant]
    for alias in aliases:
        if hasattr(component, alias):
            value = getattr(component, alias)
            if value is not None:
                return value
    return default


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _extract_reference_names(value: Any, keys: tuple[str, ...]) -> list[str]:
    """Extract object/report names from a list of dicts or plain names."""
    names: list[str] = []
    for item in _as_list(value):
        if isinstance(item, dict):
            for key in keys:
                if item.get(key):
                    names.append(str(item[key]))
                    break
        elif isinstance(item, str) and item:
            names.append(item)
    return names


def build_reference_registry(
    components: list[MetadataComponent],
) -> dict[str, set[str]]:
    """Index every component by type → set of api_names.

    Also includes a ``*`` key with every api_name across all types, and an
    ``Objects`` alias for readability.
    """
    registry: dict[str, set[str]] = {}
    all_names: set[str] = set()
    for c in components:
        if not c.type or not c.api_name:
            continue
        registry.setdefault(to_pascal_type(c.type), set()).add(c.api_name)
        all_names.add(c.api_name)
    registry["*"] = all_names
    registry["Objects"] = registry.get("Object", set())
    return registry


# ---------------------------------------------------------------------------
# RepositoryGraphBuilder
# ---------------------------------------------------------------------------


class RepositoryGraphBuilder:
    """Deterministic graph builder fed exclusively by repository metadata.

    Public API:
      - ``build(components, *, version=None) -> Graph``  (full rebuild)
      - ``incremental_update(graph, *, new_components=None,
        changed_components=None, deleted_api_names=None) -> Graph``
      - ``build_from_versioned(components_by_version) -> Graph``
        (version-aware: only the latest version of each component is used)

    Every node carries ``api_name`` + canonical ``type`` in metadata so the
    Phase 5 impact engine can resolve ``component_type``/``component_name``.
    """

    # PascalCase -> NodeType (also maps snake_case via to_pascal_type).
    NODE_TYPE_MAP: ClassVar[dict[str, NodeType]] = _NODE_TYPE_MAP

    def __init__(self) -> None:
        self._node_type_map = dict(_NODE_TYPE_MAP)

    # ── node helpers ───────────────────────────────────────────

    def resolve_node_type(self, raw_type: str) -> NodeType:
        """Resolve a component type (PascalCase or snake_case) to NodeType."""
        if not raw_type:
            return NodeType.OBJECT
        return self._node_type_map.get(to_pascal_type(raw_type), NodeType.OBJECT)

    def node_key(self, component: MetadataComponent) -> str:
        node_type = self.resolve_node_type(component.type)
        return f"{node_type.value}:{component.api_name}"

    def component_to_node(self, component: MetadataComponent) -> GraphNode:
        node_type = self.resolve_node_type(component.type)
        return GraphNode(
            id=component.id or "",
            api_name=component.api_name,
            node_type=node_type,
            label=component.label or component.api_name,
            namespace=component.namespace,
            description=component.description,
            metadata={
                "component_type": to_pascal_type(component.type),
                "component_id": component.id or "",
                "source_platform": (
                    component.source_platform.value
                    if component.source_platform
                    else "salesforce"
                ),
                "version": component.version,
                "status": component.status.value if component.status else "active",
                "organization_id": component.organization_id,
                "hash": component.hash or "",
            },
        )

    # ── build ──────────────────────────────────────────────────

    def build(
        self,
        components: list[MetadataComponent],
        *,
        version: str | None = None,
    ) -> Graph:
        """Full rebuild: create nodes for every component, then derive edges.

        Only edges whose source and target nodes exist are created.
        """
        graph = Graph(version=version or "1")
        for comp in components:
            node = self.component_to_node(comp)
            graph.add_node(node)
        self._derive_edges(graph, components)
        return graph

    def build_from_versioned(
        self,
        components_by_version: dict[str, list[MetadataComponent]],
        *,
        version: str | None = None,
    ) -> Graph:
        """Version-aware build: only the latest version of each component is used.

        ``components_by_version`` maps a version identifier to the list of
        components captured at that version. For each api_name the highest
        version entry wins (deterministic).
        """
        latest: dict[str, MetadataComponent] = {}
        for version_id, comps in components_by_version.items():
            for comp in comps:
                if not comp.api_name:
                    continue
                existing = latest.get(comp.api_name)
                if existing is None or (comp.version or 0) >= (existing.version or 0):
                    latest[comp.api_name] = comp
        return self.build(list(latest.values()), version=version)

    # ── incremental update ─────────────────────────────────────

    def incremental_update(
        self,
        graph: Graph,
        *,
        new_components: list[MetadataComponent] | None = None,
        changed_components: list[MetadataComponent] | None = None,
        deleted_api_names: list[str] | None = None,
    ) -> Graph:
        """Incrementally mutate ``graph`` in place and return it.

        - Deleted api_names have their nodes (and attached edges) removed.
        - New/changed components are added/replaced as nodes.
        - Edges are re-derived for the affected components only.
        """
        # 1. Remove deleted nodes (edges are cleaned by Graph.remove_node).
        for api_name in deleted_api_names or []:
            # Remove any node whose key ends with ``:api_name``. Because api
            # names are unique within a type but may collide across types, we
            # scan keys — this is O(N) over node count but bounded and only
            # runs for explicit deletions.
            for key in list(graph.nodes.keys()):
                if key.endswith(f":{api_name}"):
                    graph.remove_node(key)

        # 2. Add / replace nodes.
        changed: dict[str, MetadataComponent] = {}
        for comp in [*(new_components or []), *(changed_components or [])]:
            if not comp.api_name:
                continue
            changed[comp.api_name] = comp
            graph.add_node(self.component_to_node(comp))

        # 3. Re-derive edges for affected components (full re-derive for the
        #    affected set only — deterministic and cheap).
        affected = list(changed.values())
        self._derive_edges(graph, affected)
        return graph

    # ── edge derivation ────────────────────────────────────────

    def _derive_edges(self, graph: Graph, components: list[MetadataComponent]) -> None:
        """Deterministically create edges from verified component metadata.

        Mirrors the Validation & Consistency Engine reference rules. Edges are
        only created when the target node exists in ``graph``.
        """
        # Build the registry from graph nodes so incremental updates see nodes
        # that were added by previous builds.
        registry: dict[str, set[str]] = {}
        all_names: set[str] = set()
        for node in graph.nodes.values():
            api_name = node.api_name
            node_type = node.node_type.value
            registry.setdefault(node_type, set()).add(api_name)
            all_names.add(api_name)
            ctype = (node.metadata or {}).get("component_type") or _to_pascal(node_type)
            registry.setdefault(ctype, set()).add(api_name)
        registry["*"] = all_names
        registry["Objects"] = registry.get("Object", set())

        for comp in components:
            c_type = to_pascal_type(comp.type)

            # 1. Parent-object references.
            for key in _OBJECT_REFERENCE_TYPES.get(c_type, ()):
                ref = read_prop(comp, key)
                for target in _as_list(ref):
                    self._add_edge(
                        graph,
                        comp,
                        "Object",
                        str(target),
                        EdgeType.USES_OBJECT,
                        registry=registry,
                        field_name=key,
                    )

            # 2. Field lookups / master-details → target object.
            if c_type == "Field":
                field_type = str(read_prop(comp, "field_type", "fieldType") or "").lower()
                refs = read_prop(comp, "reference_to", "referenceTo")
                edge_type = (
                    EdgeType.MASTER_DETAIL_TO
                    if field_type == FieldType.MASTER_DETAIL.value
                    else EdgeType.LOOKUP_TO
                )
                for target in _as_list(refs):
                    self._add_edge(
                        graph,
                        comp,
                        "Object",
                        str(target),
                        edge_type,
                        registry=registry,
                        field_name="reference_to",
                    )

            # 3. Formula → referenced field.
            if c_type == "Formula":
                object_name = read_prop(comp, "object_api_name")
                field_name = read_prop(comp, "field_api_name", "fieldName")
                if field_name:
                    dotted = f"{object_name}.{field_name}" if object_name else str(field_name)
                    target = dotted if dotted in registry.get("Field", set()) else str(field_name)
                    self._add_edge(
                        graph,
                        comp,
                        "Field",
                        target,
                        EdgeType.USES_FIELD,
                        registry=registry,
                        field_name="field_api_name",
                    )

            # 4. Flow record operations → objects; subflows → flows.
            if c_type == "Flow":
                for key in ("record_creates", "record_updates", "record_deletes"):
                    for target in _extract_reference_names(
                        read_prop(comp, key, _camel_case(key)),
                        ("object", "object_api_name"),
                    ):
                        self._add_edge(
                            graph,
                            comp,
                            "Object",
                            target,
                            EdgeType.USES_OBJECT,
                            registry=registry,
                            field_name=key,
                        )
                for target in _extract_reference_names(
                    read_prop(comp, "subflows"),
                    ("flow", "flow_api_name"),
                ):
                    self._add_edge(
                        graph,
                        comp,
                        "Flow",
                        target,
                        EdgeType.USES_FLOW,
                        registry=registry,
                        field_name="subflows",
                    )

            # 5. Role parent reference.
            if c_type == "Role":
                parent = read_prop(comp, "parent_role", "parentRole")
                if parent:
                    self._add_edge(
                        graph,
                        comp,
                        "Role",
                        str(parent),
                        EdgeType.DEPENDS_ON,
                        registry=registry,
                        field_name="parent_role",
                    )

            # 6. Permission sets / profiles object permissions.
            if c_type in {"PermissionSet", "Profile"}:
                for target in _extract_reference_names(
                    read_prop(comp, "object_permissions", "objectPermissions"),
                    ("object", "object_api_name", "sobject"),
                ):
                    self._add_edge(
                        graph,
                        comp,
                        "Object",
                        target,
                        EdgeType.USES_OBJECT,
                        registry=registry,
                        field_name="object_permissions",
                    )
                for target in _extract_reference_names(
                    read_prop(comp, "field_permissions", "fieldPermissions"),
                    ("field", "field_api_name", "name"),
                ):
                    self._add_edge(
                        graph,
                        comp,
                        "Field",
                        target,
                        EdgeType.USES_FIELD,
                        registry=registry,
                        field_name="field_permissions",
                    )
                for target in _extract_reference_names(
                    read_prop(comp, "class_permissions", "classPermissions"),
                    ("apex_class", "class_api_name", "name"),
                ):
                    self._add_edge(
                        graph,
                        comp,
                        "ApexClass",
                        target,
                        EdgeType.USES,
                        registry=registry,
                        field_name="class_permissions",
                    )

            # 7. Dashboard components reference reports.
            if c_type == "Dashboard":
                for target in _extract_reference_names(
                    read_prop(comp, "components"),
                    ("report", "report_api_name", "name"),
                ):
                    self._add_edge(
                        graph,
                        comp,
                        "Report",
                        target,
                        EdgeType.USES_REPORT,
                        registry=registry,
                        field_name="components",
                    )

            # 8. Apex class extends / implements / SOQL FROM.
            if c_type == "ApexClass":
                body = read_prop(comp, "body") or ""
                m = _APEX_EXTENDS_RE.search(body)
                if m:
                    self._add_edge(
                        graph,
                        comp,
                        "ApexClass",
                        m.group(1),
                        EdgeType.EXTENDS,
                        registry=registry,
                        field_name="body",
                    )
                m = _APEX_IMPLEMENTS_RE.search(body)
                if m:
                    for name in re.split(r"[\s,]+", m.group(1).strip()):
                        if name:
                            self._add_edge(
                                graph,
                                comp,
                                "ApexClass",
                                name,
                                EdgeType.IMPLEMENTS,
                                registry=registry,
                                field_name="body",
                            )
                for name in _SOQL_FROM_RE.findall(body):
                    self._add_edge(
                        graph,
                        comp,
                        "Object",
                        name,
                        EdgeType.USES_OBJECT,
                        registry=registry,
                        field_name="body",
                    )

            # 9. Trigger object reference.
            if c_type == "Trigger":
                object_name = read_prop(comp, "object_api_name")
                if object_name:
                    self._add_edge(
                        graph,
                        comp,
                        "Object",
                        str(object_name),
                        EdgeType.USES_OBJECT,
                        registry=registry,
                        field_name="object_api_name",
                    )

            # 10. Email template object type.
            if c_type == "EmailTemplate":
                object_type = read_prop(comp, "object_type", "objectType")
                if object_type:
                    self._add_edge(
                        graph,
                        comp,
                        "Object",
                        str(object_type),
                        EdgeType.USES_OBJECT,
                        registry=registry,
                        field_name="object_type",
                    )

            # 11. Queue sobjects.
            if c_type == "Queue":
                for target in _extract_reference_names(
                    read_prop(comp, "queue_sobjects", "queueSobjects"),
                    ("sobject", "object", "sobject_type"),
                ):
                    self._add_edge(
                        graph,
                        comp,
                        "Object",
                        target,
                        EdgeType.USES_OBJECT,
                        registry=registry,
                        field_name="queue_sobjects",
                    )

            # 12. QuickAction target object.
            if c_type == "QuickAction":
                target_object = read_prop(comp, "target_object", "targetObject")
                if target_object:
                    self._add_edge(
                        graph,
                        comp,
                        "Object",
                        str(target_object),
                        EdgeType.USES_OBJECT,
                        registry=registry,
                        field_name="target_object",
                    )

            # 13. Declared canonical relationships.
            for rel in comp.relationships or []:
                self._relationship_to_edge(graph, comp, rel, registry=registry)

    def _relationship_to_edge(
        self,
        graph: Graph,
        comp: MetadataComponent,
        rel: CanonicalRelationship,
        *,
        registry: dict[str, set[str]],
    ) -> None:
        target = rel.target_api_name
        if not target:
            return
        target_type = to_pascal_type(rel.target_type) or "Object"
        edge_type = _RELATIONSHIP_EDGE_MAP.get(rel.type, EdgeType.REFERENCES)
        self._add_edge(
            graph,
            comp,
            target_type,
            target,
            edge_type,
            registry=registry,
            metadata=dict(rel.metadata or {}),
        )

    def _add_edge(
        self,
        graph: Graph,
        source: MetadataComponent,
        target_type: str,
        target_api_name: str,
        edge_type: EdgeType,
        *,
        registry: dict[str, set[str]],
        field_name: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Create an edge only if the target node exists (no invented edges)."""
        target_node_type = self.resolve_node_type(target_type)
        source_node_type = self.resolve_node_type(source.type)
        source_key = f"{source_node_type.value}:{source.api_name}"
        target_key = f"{target_node_type.value}:{target_api_name}"

        # Skip edges that would point back at the source node.
        if source_key == target_key:
            return

        target_node = graph.nodes.get(target_key)
        if target_node is None:
            return

        edge_metadata: dict[str, Any] = dict(metadata or {})
        if field_name:
            edge_metadata["field"] = field_name
        edge_metadata["source_api_name"] = source.api_name
        edge_metadata["target_api_name"] = target_api_name
        edge_metadata["target_component_type"] = to_pascal_type(target_type)

        edge = GraphEdge(
            source_id=source_key,
            target_id=target_key,
            edge_type=edge_type,
            metadata=edge_metadata,
        )
        graph.add_edge(edge)


def _to_pascal(node_type_value: str) -> str:
    """Convert a snake-ish NodeType value to PascalCase vocabulary."""
    return "".join(p.capitalize() for p in str(node_type_value).split("_"))
