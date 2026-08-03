from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class NodeType(StrEnum):
    OBJECT = "object"
    FIELD = "field"
    RELATIONSHIP = "relationship"
    FLOW = "flow"
    FLOW_VERSION = "flow_version"
    VALIDATION_RULE = "validation_rule"
    FORMULA = "formula"
    LAYOUT = "layout"
    RECORD_TYPE = "record_type"
    PERMISSION_SET = "permission_set"
    PROFILE = "profile"
    APEX_CLASS = "apex_class"
    TRIGGER = "trigger"
    REPORT = "report"
    DASHBOARD = "dashboard"
    WORKFLOW = "workflow"
    APPROVAL_PROCESS = "approval_process"
    CUSTOM_METADATA = "custom_metadata"
    CUSTOM_SETTING = "custom_setting"
    LIGHTNING_PAGE = "lightning_page"
    QUICK_ACTION = "quick_action"
    EMAIL_TEMPLATE = "email_template"
    NAMED_CREDENTIAL = "named_credential"
    CONNECTED_APP = "connected_app"
    ROLE = "role"
    QUEUE = "queue"
    PUBLIC_GROUP = "public_group"
    SHARING_RULE = "sharing_rule"
    GLOBAL_VALUE_SET = "global_value_set"


class EdgeType(StrEnum):
    # ── Canonical edge types (Phase 4) ─────────────────────────
    REFERENCES = "references"
    USES = "uses"
    CALLS = "calls"
    CONTAINS = "contains"
    EXTENDS = "extends"
    IMPLEMENTS = "implements"
    LOOKUP_TO = "lookup_to"
    MASTER_DETAIL_TO = "master_detail_to"
    USES_FIELD = "uses_field"
    USES_OBJECT = "uses_object"
    USES_FLOW = "uses_flow"
    USES_TRIGGER = "uses_trigger"
    USES_REPORT = "uses_report"
    USES_LAYOUT = "uses_layout"
    USES_DASHBOARD = "uses_dashboard"
    USES_PERMISSION = "uses_permission"
    USES_PROFILE = "uses_profile"
    IMPORTS = "imports"
    DEPENDS_ON = "depends_on"
    # ── Legacy aliases (kept for API compatibility) ────────────
    OWNS = "owns"
    INVOKES = "invokes"
    LOOKUP = "lookup"
    MASTER_DETAIL = "master_detail"
    FORMULA_REFERENCE = "formula_reference"
    FLOW_REFERENCE = "flow_reference"
    APEX_REFERENCE = "apex_reference"
    REPORT_REFERENCE = "report_reference"
    VALIDATION_REFERENCE = "validation_reference"
    PERMISSION_REFERENCE = "permission_reference"
    LAYOUT_REFERENCE = "layout_reference"
    TRIGGER_ON = "trigger_on"
    SOQL_REFERENCE = "soql_reference"
    CUSTOM = "custom"


class GraphNode(BaseModel):
    id: str = ""
    api_name: str = ""
    node_type: NodeType = NodeType.OBJECT
    label: str = ""
    namespace: str | None = None
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.node_type.value}:{self.api_name}"


class GraphEdge(BaseModel):
    id: str = ""
    source_id: str = ""
    target_id: str = ""
    edge_type: EdgeType = EdgeType.REFERENCES
    metadata: dict[str, Any] = Field(default_factory=dict)


class Graph(BaseModel):
    version: str = ""
    created_at: datetime | None = None
    nodes: dict[str, GraphNode] = Field(default_factory=dict)
    edges: dict[str, GraphEdge] = Field(default_factory=dict)
    outgoing: dict[str, list[str]] = Field(default_factory=dict)
    incoming: dict[str, list[str]] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def add_node(self, node: GraphNode) -> GraphNode:
        if isinstance(node, DependencyNode):
            node = node.to_graph_node()
        existing = self.nodes.get(node.key)
        if existing:
            return existing
        self.nodes[node.key] = node
        if node.key not in self.outgoing:
            self.outgoing[node.key] = []
        if node.key not in self.incoming:
            self.incoming[node.key] = []
        return node

    def add_edge(self, edge: GraphEdge) -> None:
        if isinstance(edge, DependencyEdge):
            edge = edge.to_graph_edge()
        if not edge.id:
            edge.id = f"{edge.source_id}--[{edge.edge_type.value}]-->{edge.target_id}"
        if edge.id in self.edges:
            return
        self.edges[edge.id] = edge
        self.outgoing.setdefault(edge.source_id, []).append(edge.id)
        self.incoming.setdefault(edge.target_id, []).append(edge.id)

    def get_node(self, key: str) -> GraphNode | None:
        return self.nodes.get(key)

    def get_outgoing_edges(self, node_key: str) -> list[GraphEdge]:
        edge_ids = self.outgoing.get(node_key, [])
        return [self.edges[eid] for eid in edge_ids if eid in self.edges]

    def get_incoming_edges(self, node_key: str) -> list[GraphEdge]:
        edge_ids = self.incoming.get(node_key, [])
        return [self.edges[eid] for eid in edge_ids if eid in self.edges]

    def get_upstream(self, node_key: str, max_depth: int = 1) -> list[GraphNode]:
        visited: set[str] = set()
        result: list[GraphNode] = []
        queue: list[tuple[str, int]] = [(node_key, 0)]
        while queue:
            key, depth = queue.pop(0)
            if key in visited or depth > max_depth:
                continue
            visited.add(key)
            if depth > 0:
                node = self.nodes.get(key)
                if node:
                    result.append(node)
            if depth < max_depth:
                for edge_id in self.outgoing.get(key, []):
                    edge = self.edges.get(edge_id)
                    if edge and edge.target_id not in visited:
                        queue.append((edge.target_id, depth + 1))
        return result

    def get_downstream(self, node_key: str, max_depth: int = 1) -> list[GraphNode]:
        visited: set[str] = set()
        result: list[GraphNode] = []
        queue: list[tuple[str, int]] = [(node_key, 0)]
        while queue:
            key, depth = queue.pop(0)
            if key in visited or depth > max_depth:
                continue
            visited.add(key)
            if depth > 0:
                node = self.nodes.get(key)
                if node:
                    result.append(node)
            if depth < max_depth:
                for edge_id in self.incoming.get(key, []):
                    edge = self.edges.get(edge_id)
                    if edge and edge.source_id not in visited:
                        queue.append((edge.source_id, depth + 1))
        return result

    def remove_node(self, node_key: str) -> None:
        if node_key not in self.nodes:
            return
        for edge_id in list(self.outgoing.get(node_key, [])):
            self._remove_edge(edge_id)
        for edge_id in list(self.incoming.get(node_key, [])):
            self._remove_edge(edge_id)
        self.nodes.pop(node_key, None)
        self.outgoing.pop(node_key, None)
        self.incoming.pop(node_key, None)

    # ── Phase 4 traversal ops ──────────────────────────────────

    def get_neighbors(self, node_key: str, max_depth: int = 1) -> list[GraphNode]:
        """Return nodes adjacent to ``node_key`` (undirected, up to depth)."""
        visited: set[str] = set()
        result: list[GraphNode] = []
        queue: list[tuple[str, int]] = [(node_key, 0)]
        while queue:
            key, depth = queue.pop(0)
            if key in visited or depth > max_depth:
                continue
            visited.add(key)
            if depth > 0:
                node = self.nodes.get(key)
                if node:
                    result.append(node)
            if depth < max_depth:
                for edge_id in self.outgoing.get(key, []):
                    edge = self.edges.get(edge_id)
                    if edge and edge.target_id not in visited:
                        queue.append((edge.target_id, depth + 1))
                for edge_id in self.incoming.get(key, []):
                    edge = self.edges.get(edge_id)
                    if edge and edge.source_id not in visited:
                        queue.append((edge.source_id, depth + 1))
        return result

    def get_dependencies(self, node_key: str, max_depth: int = 1) -> list[GraphNode]:
        """Return the nodes this node depends on (outgoing, upstream)."""
        return self.get_upstream(node_key, max_depth)

    def get_dependents(self, node_key: str, max_depth: int = 1) -> list[GraphNode]:
        """Return the nodes that depend on this node (incoming, downstream)."""
        return self.get_downstream(node_key, max_depth)

    def find_path(self, source_key: str, target_key: str) -> list[str] | None:
        """Return any path (list of node keys) from source to target, or None."""
        if source_key not in self.nodes or target_key not in self.nodes:
            return None
        if source_key == target_key:
            return [source_key]
        visited: set[str] = set()
        stack: list[tuple[str, list[str]]] = [(source_key, [source_key])]
        while stack:
            current, path = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            for edge_id in self.outgoing.get(current, []):
                edge = self.edges.get(edge_id)
                if edge is None or edge.target_id in visited:
                    continue
                new_path = [*path, edge.target_id]
                if edge.target_id == target_key:
                    return new_path
                stack.append((edge.target_id, new_path))
        return None

    def connected_components(self) -> list[list[str]]:
        """Return connected components as lists of node keys (undirected)."""
        visited: set[str] = set()
        components: list[list[str]] = []
        for start in self.nodes:
            if start in visited:
                continue
            component: list[str] = []
            queue: list[str] = [start]
            visited.add(start)
            while queue:
                current = queue.pop(0)
                component.append(current)
                for edge_id in self.outgoing.get(current, []):
                    edge = self.edges.get(edge_id)
                    if edge and edge.target_id not in visited:
                        visited.add(edge.target_id)
                        queue.append(edge.target_id)
                for edge_id in self.incoming.get(current, []):
                    edge = self.edges.get(edge_id)
                    if edge and edge.source_id not in visited:
                        visited.add(edge.source_id)
                        queue.append(edge.source_id)
            components.append(component)
        return components

    def get_subgraph(self, node_key: str, max_depth: int = 1) -> "Graph":
        """Return a subgraph rooted at ``node_key`` expanded to ``max_depth``."""
        sub = Graph(version=self.version, created_at=self.created_at)
        visited: set[str] = set()
        queue: list[tuple[str, int]] = [(node_key, 0)]
        while queue:
            key, depth = queue.pop(0)
            if key in visited or depth > max_depth:
                continue
            visited.add(key)
            node = self.nodes.get(key)
            if node:
                sub.add_node(node)
            if depth < max_depth:
                for edge_id in self.outgoing.get(key, []):
                    edge = self.edges.get(edge_id)
                    if edge is None:
                        continue
                    sub.add_edge(edge)
                    queue.append((edge.target_id, depth + 1))
                for edge_id in self.incoming.get(key, []):
                    edge = self.edges.get(edge_id)
                    if edge is None:
                        continue
                    sub.add_edge(edge)
                    queue.append((edge.source_id, depth + 1))
        return sub

    def export(self) -> dict[str, Any]:
        """Export the graph as a JSON-serializable dict."""
        return self.model_dump(mode="json")

    def _remove_edge(self, edge_id: str) -> None:
        edge = self.edges.pop(edge_id, None)
        if edge is None:
            return
        src_out = self.outgoing.get(edge.source_id, [])
        if edge_id in src_out:
            src_out.remove(edge_id)
        tgt_in = self.incoming.get(edge.target_id, [])
        if edge_id in tgt_in:
            tgt_in.remove(edge_id)

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    def find_cycles(self) -> list[list[str]]:
        cycles: list[list[str]] = []
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def dfs(node_key: str, path: list[str]) -> None:
            visited.add(node_key)
            rec_stack.add(node_key)
            path.append(node_key)
            for edge_id in self.outgoing.get(node_key, []):
                edge = self.edges.get(edge_id)
                if edge and edge.target_id in rec_stack:
                    cycle_start = path.index(edge.target_id)
                    cycles.append(path[cycle_start:] + [edge.target_id])
                elif edge and edge.target_id not in visited:
                    dfs(edge.target_id, path)
            path.pop()
            rec_stack.discard(node_key)

        for key in self.nodes:
            if key not in visited:
                dfs(key, [])
        return cycles

    def clear(self) -> None:
        self.nodes.clear()
        self.edges.clear()
        self.outgoing.clear()
        self.incoming.clear()


class GraphVersion(BaseModel):
    version: str = ""
    parent_version: str | None = None
    created_at: datetime | None = None
    node_count: int = 0
    edge_count: int = 0
    change_summary: str = ""


class GraphSnapshot(BaseModel):
    version: str = ""
    snapshot_id: str = ""
    created_at: datetime | None = None
    graph: Graph = Field(default_factory=Graph)
    version_info: GraphVersion = Field(default_factory=GraphVersion)


# ─── Backward-compatibility aliases ─────────────────────────


class DependencyType(StrEnum):
    USES_OBJECT = "uses_object"
    USES_FIELD = "uses_field"
    USES_CLASS = "uses_class"
    EXTENDS = "extends"
    IMPLEMENTS = "implements"
    REFERENCES = "references"
    CALLS = "calls"
    CONTAINS = "contains"
    LOOKUP_TO = "lookup_to"
    MASTER_DETAIL_TO = "master_detail_to"
    USES_FLOW = "uses_flow"
    USES_TRIGGER = "uses_trigger"
    USES_REPORT = "uses_report"
    USES_LAYOUT = "uses_layout"
    USES_DASHBOARD = "uses_dashboard"
    USES_PERMISSION = "uses_permission"
    USES_PROFILE = "uses_profile"
    IMPORTS = "imports"
    DEPENDS_ON = "depends_on"


_NODE_TYPE_MAP: dict[str, NodeType] = {
    "ApexClass": NodeType.APEX_CLASS,
    "ApexPage": NodeType.APEX_CLASS,
    "CustomObject": NodeType.OBJECT,
    "CustomField": NodeType.FIELD,
    "Layout": NodeType.LAYOUT,
    "ValidationRule": NodeType.VALIDATION_RULE,
    "Profile": NodeType.PROFILE,
    "PermissionSet": NodeType.PERMISSION_SET,
    "Object": NodeType.OBJECT,
    "Field": NodeType.FIELD,
    "Trigger": NodeType.TRIGGER,
    "Flow": NodeType.FLOW,
    "Report": NodeType.REPORT,
    "Dashboard": NodeType.DASHBOARD,
    "Workflow": NodeType.WORKFLOW,
    "Role": NodeType.ROLE,
    "Queue": NodeType.QUEUE,
    "PublicGroup": NodeType.PUBLIC_GROUP,
    "SharingRule": NodeType.SHARING_RULE,
    "GlobalValueSet": NodeType.GLOBAL_VALUE_SET,
    "RecordType": NodeType.RECORD_TYPE,
    "Formula": NodeType.FORMULA,
    "CustomMetadata": NodeType.CUSTOM_METADATA,
    "CustomSetting": NodeType.CUSTOM_SETTING,
    "LightningPage": NodeType.LIGHTNING_PAGE,
    "QuickAction": NodeType.QUICK_ACTION,
    "EmailTemplate": NodeType.EMAIL_TEMPLATE,
    "NamedCredential": NodeType.NAMED_CREDENTIAL,
    "ConnectedApp": NodeType.CONNECTED_APP,
    "ApprovalProcess": NodeType.APPROVAL_PROCESS,
    "Relationship": NodeType.RELATIONSHIP,
}

_EDGE_TYPE_MAP: dict[DependencyType, EdgeType] = {
    DependencyType.USES_OBJECT: EdgeType.USES_OBJECT,
    DependencyType.USES_FIELD: EdgeType.USES_FIELD,
    DependencyType.USES_CLASS: EdgeType.REFERENCES,
    DependencyType.EXTENDS: EdgeType.EXTENDS,
    DependencyType.IMPLEMENTS: EdgeType.IMPLEMENTS,
    DependencyType.REFERENCES: EdgeType.REFERENCES,
    DependencyType.CALLS: EdgeType.CALLS,
    DependencyType.CONTAINS: EdgeType.CONTAINS,
    DependencyType.LOOKUP_TO: EdgeType.LOOKUP_TO,
    DependencyType.MASTER_DETAIL_TO: EdgeType.MASTER_DETAIL_TO,
    DependencyType.USES_FLOW: EdgeType.USES_FLOW,
    DependencyType.USES_TRIGGER: EdgeType.USES_TRIGGER,
    DependencyType.USES_REPORT: EdgeType.USES_REPORT,
    DependencyType.USES_LAYOUT: EdgeType.USES_LAYOUT,
    DependencyType.USES_DASHBOARD: EdgeType.USES_DASHBOARD,
    DependencyType.USES_PERMISSION: EdgeType.USES_PERMISSION,
    DependencyType.USES_PROFILE: EdgeType.USES_PROFILE,
    DependencyType.IMPORTS: EdgeType.IMPORTS,
    DependencyType.DEPENDS_ON: EdgeType.DEPENDS_ON,
}


class DependencyNode(BaseModel):
    component_type: str = ""
    component_name: str = ""
    component_id: str | None = None

    model_config = {"extra": "allow"}

    @property
    def key(self) -> str:
        return f"{self.component_type}:{self.component_name}"

    def to_graph_node(self) -> GraphNode:
        return GraphNode(
            api_name=self.component_name,
            node_type=_NODE_TYPE_MAP.get(self.component_type, NodeType.OBJECT),
        )


class DependencyEdge(BaseModel):
    source: DependencyNode | GraphNode = Field(default_factory=DependencyNode)
    target: DependencyNode | GraphNode = Field(default_factory=DependencyNode)
    dependency_type: DependencyType = DependencyType.USES_OBJECT
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_field: str | None = None

    def to_graph_edge(self) -> GraphEdge:
        src_key = getattr(self.source, "key", "")
        tgt_key = getattr(self.target, "key", "")
        return GraphEdge(
            source_id=src_key,
            target_id=tgt_key,
            edge_type=_EDGE_TYPE_MAP.get(self.dependency_type, EdgeType.REFERENCES),
        )


DependencyGraph = Graph
