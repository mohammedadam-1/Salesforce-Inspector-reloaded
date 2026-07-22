from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GraphBuildRequest:
    organization_id: str
    metadata_types: list[str] | None = None


@dataclass
class GraphNodeResponse:
    component_type: str
    component_name: str
    component_id: str | None = None


@dataclass
class GraphEdgeResponse:
    source: str
    target: str
    dependency_type: str
    source_field: str | None = None
    target_field: str | None = None


@dataclass
class GraphResponse:
    nodes: list[GraphNodeResponse] = field(default_factory=list)
    edges: list[GraphEdgeResponse] = field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0


@dataclass
class DependencyQueryResponse:
    node: dict[str, Any] | None = None
    upstream: list[dict[str, Any]] = field(default_factory=list)
    downstream: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ImpactResponse:
    impacted_components: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class GraphSummaryResponse:
    node_count: int = 0
    edge_count: int = 0
    cycles: int = 0
    component_types: dict[str, int] = field(default_factory=dict)
