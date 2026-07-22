"""Tests for domain graph models: GraphNode, GraphEdge, Graph, GraphVersion, GraphSnapshot."""

from datetime import UTC, datetime

from sfir_backend.domain.graph.models import (
    EdgeType,
    Graph,
    GraphEdge,
    GraphNode,
    GraphSnapshot,
    GraphVersion,
    NodeType,
)


class TestNodeType:
    def test_values(self) -> None:
        assert NodeType.OBJECT.value == "object"
        assert NodeType.FIELD.value == "field"
        assert NodeType.APEX_CLASS.value == "apex_class"
        assert NodeType.FLOW.value == "flow"


class TestEdgeType:
    def test_values(self) -> None:
        assert EdgeType.USES.value == "uses"
        assert EdgeType.REFERENCES.value == "references"
        assert EdgeType.CONTAINS.value == "contains"
        assert EdgeType.OWNS.value == "owns"
        assert EdgeType.LOOKUP.value == "lookup"


class TestGraphNode:
    def test_construction(self) -> None:
        node = GraphNode(
            id="n1",
            api_name="Account",
            node_type=NodeType.OBJECT,
            label="Account",
        )
        assert node.id == "n1"
        assert node.api_name == "Account"
        assert node.key == "object:Account"

    def test_key_property(self) -> None:
        node = GraphNode(api_name="Account.Name", node_type=NodeType.FIELD)
        assert node.key == "field:Account.Name"


class TestGraphEdge:
    def test_construction(self) -> None:
        edge = GraphEdge(
            id="e1",
            source_id="object:Account",
            target_id="object:User",
            edge_type=EdgeType.LOOKUP,
        )
        assert edge.source_id == "object:Account"
        assert edge.target_id == "object:User"
        assert edge.edge_type == EdgeType.LOOKUP


class TestGraph:
    def test_empty_graph(self) -> None:
        g = Graph()
        assert g.node_count == 0
        assert g.edge_count == 0

    def test_add_node(self) -> None:
        g = Graph()
        node = GraphNode(api_name="Account", node_type=NodeType.OBJECT)
        g.add_node(node)
        assert g.node_count == 1
        assert g.get_node("object:Account") is not None

    def test_add_duplicate_node(self) -> None:
        g = Graph()
        n1 = GraphNode(api_name="Account", node_type=NodeType.OBJECT)
        n2 = GraphNode(api_name="Account", node_type=NodeType.OBJECT)
        g.add_node(n1)
        g.add_node(n2)
        assert g.node_count == 1

    def test_add_edge(self) -> None:
        g = Graph()
        n1 = GraphNode(api_name="Account", node_type=NodeType.OBJECT)
        n2 = GraphNode(api_name="User", node_type=NodeType.OBJECT)
        g.add_node(n1)
        g.add_node(n2)
        edge = GraphEdge(
            source_id="object:Account",
            target_id="object:User",
            edge_type=EdgeType.LOOKUP,
        )
        g.add_edge(edge)
        assert g.edge_count == 1

    def test_outgoing_and_incoming(self) -> None:
        g = Graph()
        nodes = [
            GraphNode(api_name="A", node_type=NodeType.OBJECT),
            GraphNode(api_name="B", node_type=NodeType.OBJECT),
            GraphNode(api_name="C", node_type=NodeType.OBJECT),
        ]
        for n in nodes:
            g.add_node(n)
        g.add_edge(GraphEdge(source_id="object:A", target_id="object:B"))
        g.add_edge(GraphEdge(source_id="object:A", target_id="object:C"))

        outgoing = g.get_outgoing_edges("object:A")
        assert len(outgoing) == 2
        incoming_b = g.get_incoming_edges("object:B")
        assert len(incoming_b) == 1

    def test_remove_node(self) -> None:
        g = Graph()
        n = GraphNode(api_name="Orphan", node_type=NodeType.OBJECT)
        g.add_node(n)
        g.remove_node("object:Orphan")
        assert g.node_count == 0

    def test_remove_node_with_edges(self) -> None:
        g = Graph()
        for name in ["A", "B", "C"]:
            g.add_node(GraphNode(api_name=name, node_type=NodeType.OBJECT))
        g.add_edge(GraphEdge(source_id="object:A", target_id="object:B"))
        g.add_edge(GraphEdge(source_id="object:B", target_id="object:C"))
        g.remove_node("object:B")
        assert "object:B" not in g.nodes
        assert g.edge_count == 0

    def test_clear(self) -> None:
        g = Graph()
        g.add_node(GraphNode(api_name="A", node_type=NodeType.OBJECT))
        g.add_edge(
            GraphEdge(source_id="object:A", target_id="object:A"),
        )
        g.clear()
        assert g.node_count == 0
        assert g.edge_count == 0

    def test_serialization(self) -> None:
        g = Graph(version="v1")
        g.add_node(GraphNode(api_name="A", node_type=NodeType.OBJECT))
        data = g.model_dump()
        restored = Graph.model_validate(data)
        assert restored.version == "v1"
        assert restored.node_count == 1


class TestGraphVersion:
    def test_construction(self) -> None:
        v = GraphVersion(
            version="v1",
            parent_version="v0",
            node_count=100,
            edge_count=50,
            change_summary="initial build",
        )
        assert v.version == "v1"
        assert v.parent_version == "v0"


class TestGraphSnapshot:
    def test_construction(self) -> None:
        g = Graph(version="v1")
        g.add_node(GraphNode(api_name="A", node_type=NodeType.OBJECT))
        snap = GraphSnapshot(
            version="v1",
            snapshot_id="s1",
            created_at=datetime.now(tz=UTC),
            graph=g,
            version_info=GraphVersion(version="v1"),
        )
        assert snap.snapshot_id == "s1"
        assert snap.graph.node_count == 1
