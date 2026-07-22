from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sfir_backend.domain.graph.models import GraphEdge, GraphNode, NodeType


class TraversalContext(BaseModel):
    max_depth: int = 10
    max_nodes: int = 1000
    node_types: list[NodeType] = Field(default_factory=list)
    edge_types: list[str] = Field(default_factory=list)
    include_self: bool = False
    stop_on_cycle: bool = True


class DependencyPath(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    total_depth: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class TraversalResult(BaseModel):
    paths: list[DependencyPath] = Field(default_factory=list)
    nodes: dict[str, GraphNode] = Field(default_factory=dict)
    edges: dict[str, GraphEdge] = Field(default_factory=dict)
    total_nodes_visited: int = 0
    total_edges_traversed: int = 0
    cycles_detected: list[list[str]] = Field(default_factory=list)
    truncated: bool = False
