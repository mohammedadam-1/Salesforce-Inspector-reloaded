"""Unit tests for Phase 4 Graph model ops and EdgeType additions.

Covers: EdgeType canonical values, get_neighbors, get_dependencies,
get_dependents, find_path, connected_components, get_subgraph, export.
"""

from __future__ import annotations

import pytest

from sfir_backend.domain.graph.models import (
    DependencyType,
    EdgeType,
    Graph,
    GraphEdge,
    GraphNode,
    NodeType,
)


def _node(node_type: NodeType, api_name: str) -> GraphNode:
    return GraphNode(
        api_name=api_name,
        node_type=node_type,
        label=api_name,
    )


@pytest.fixture
def sample_graph() -> Graph:
    """A tiny directed graph: A -> B -> C, A -> D, D -> C."""
    g = Graph(version="test")
    for key, nt, name in [
        ("object:A", NodeType.OBJECT, "A"),
        ("object:B", NodeType.OBJECT, "B"),
        ("object:C", NodeType.OBJECT, "C"),
        ("object:D", NodeType.OBJECT, "D"),
    ]:
        g.add_node(_node(nt, name))
    g.add_edge(GraphEdge(source_id="object:A", target_id="object:B", edge_type=EdgeType.USES))
    g.add_edge(GraphEdge(source_id="object:B", target_id="object:C", edge_type=EdgeType.USES))
    g.add_edge(GraphEdge(source_id="object:A", target_id="object:D", edge_type=EdgeType.USES))
    g.add_edge(GraphEdge(source_id="object:D", target_id="object:C", edge_type=EdgeType.USES))
    return g


class TestEdgeTypeCanonicalValues:
    def test_all_required_edge_types_present(self):
        required = {
            "REFERENCES",
            "USES",
            "CALLS",
            "CONTAINS",
            "EXTENDS",
            "IMPLEMENTS",
            "LOOKUP_TO",
            "MASTER_DETAIL_TO",
            "USES_FIELD",
            "USES_OBJECT",
            "USES_FLOW",
            "USES_TRIGGER",
            "USES_REPORT",
            "USES_LAYOUT",
            "USES_DASHBOARD",
            "USES_PERMISSION",
            "USES_PROFILE",
            "IMPORTS",
            "DEPENDS_ON",
        }
        assert required.issubset({e.name for e in EdgeType})

    def test_legacy_edge_types_preserved(self):
        legacy = {
            "OWNS",
            "INVOKES",
            "LOOKUP",
            "MASTER_DETAIL",
            "FORMULA_REFERENCE",
            "FLOW_REFERENCE",
            "APEX_REFERENCE",
            "REPORT_REFERENCE",
            "VALIDATION_REFERENCE",
            "PERMISSION_REFERENCE",
            "LAYOUT_REFERENCE",
            "TRIGGER_ON",
            "SOQL_REFERENCE",
            "CUSTOM",
        }
        assert legacy.issubset({e.name for e in EdgeType})

    def test_dependency_type_matches_canonical(self):
        assert DependencyType.USES_OBJECT.value == "uses_object"
        assert DependencyType.DEPENDS_ON.value == "depends_on"


class TestGraphNeighbors:
    def test_get_neighbors_depth_one(self, sample_graph):
        neighbors = sample_graph.get_neighbors("object:B", max_depth=1)
        names = {n.api_name for n in neighbors}
        assert names == {"A", "C"}  # both directions

    def test_get_neighbors_depth_two(self, sample_graph):
        neighbors = sample_graph.get_neighbors("object:B", max_depth=2)
        names = {n.api_name for n in neighbors}
        assert names == {"A", "C", "D"}

    def test_get_neighbors_missing_node(self, sample_graph):
        assert sample_graph.get_neighbors("object:ZZZ") == []


class TestGraphDependencies:
    def test_get_dependencies_is_upstream(self, sample_graph):
        # get_upstream follows OUTGOING edges: what the node references.
        deps = sample_graph.get_dependencies("object:A", max_depth=1)
        names = {n.api_name for n in deps}
        assert names == {"B", "D"}

    def test_get_dependents_is_downstream(self, sample_graph):
        # get_downstream follows INCOMING edges: what references the node.
        dependents = sample_graph.get_dependents("object:C", max_depth=1)
        names = {n.api_name for n in dependents}
        assert names == {"B", "D"}


class TestGraphFindPath:
    def test_find_path_direct(self, sample_graph):
        path = sample_graph.find_path("object:A", "object:B")
        assert path == ["object:A", "object:B"]

    def test_find_path_indirect(self, sample_graph):
        path = sample_graph.find_path("object:A", "object:C")
        assert path is not None
        assert path[0] == "object:A"
        assert path[-1] == "object:C"

    def test_find_path_none_when_missing(self, sample_graph):
        assert sample_graph.find_path("object:A", "object:ZZZ") is None

    def test_find_path_same_node(self, sample_graph):
        assert sample_graph.find_path("object:A", "object:A") == ["object:A"]


class TestGraphConnectedComponents:
    def test_single_component(self, sample_graph):
        components = sample_graph.connected_components()
        assert len(components) == 1
        assert set(components[0]) == {
            "object:A", "object:B", "object:C", "object:D",
        }

    def test_disconnected_components(self):
        g = Graph(version="test")
        for name in ["A", "B", "C"]:
            g.add_node(_node(NodeType.OBJECT, name))
        g.add_edge(GraphEdge(
            source_id="object:A", target_id="object:B", edge_type=EdgeType.USES
        ))
        components = g.connected_components()
        assert len(components) == 2
        sizes = sorted(len(c) for c in components)
        assert sizes == [1, 2]


class TestGraphSubgraph:
    def test_get_subgraph(self, sample_graph):
        sub = sample_graph.get_subgraph("object:A", max_depth=1)
        assert "object:A" in sub.nodes
        assert "object:B" in sub.nodes
        assert "object:D" in sub.nodes
        assert "object:C" not in sub.nodes
        assert sub.edge_count == 2


class TestGraphExport:
    def test_export_roundtrip_keys(self, sample_graph):
        exported = sample_graph.export()
        assert set(exported.keys()) == {
            "version", "created_at", "nodes", "edges", "outgoing", "incoming", "metadata",
        }
        assert len(exported["nodes"]) == 4
        assert len(exported["edges"]) == 4
        assert "object:A" in exported["outgoing"]
        assert "object:C" in exported["incoming"]

    def test_export_json_serializable(self, sample_graph):
        import json

        exported = sample_graph.export()
        json.dumps(exported)  # must not raise
