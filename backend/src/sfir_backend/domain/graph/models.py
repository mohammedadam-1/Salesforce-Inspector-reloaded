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
    USES = "uses"
    REFERENCES = "references"
    CONTAINS = "contains"
    OWNS = "owns"
    INVOKES = "invokes"
    EXTENDS = "extends"
    IMPLEMENTS = "implements"
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
        if edge.id and edge.id in self.edges:
            return
        if not edge.id:
            edge.id = f"{edge.source_id}--[{edge.edge_type.value}]-->{edge.target_id}"
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


_NODE_TYPE_MAP: dict[str, NodeType] = {
    "ApexClass": NodeType.APEX_CLASS,
    "ApexPage": NodeType.APEX_CLASS,
    "CustomObject": NodeType.OBJECT,
    "CustomField": NodeType.FIELD,
    "Layout": NodeType.LAYOUT,
    "ValidationRule": NodeType.VALIDATION_RULE,
    "Profile": NodeType.PROFILE,
    "PermissionSet": NodeType.PERMISSION_SET,
}

_EDGE_TYPE_MAP: dict[DependencyType, EdgeType] = {
    DependencyType.USES_OBJECT: EdgeType.USES,
    DependencyType.USES_FIELD: EdgeType.REFERENCES,
    DependencyType.USES_CLASS: EdgeType.REFERENCES,
    DependencyType.EXTENDS: EdgeType.EXTENDS,
    DependencyType.IMPLEMENTS: EdgeType.IMPLEMENTS,
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
