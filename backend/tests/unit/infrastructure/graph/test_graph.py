"""Tests for graph engine: builder, traversal, resolver, cycle detection, version, cache."""

from datetime import UTC, datetime

import pytest

from sfir_backend.domain.canonical import (
    MetadataField,
    MetadataObject,
)
from sfir_backend.domain.graph.models import (
    EdgeType,
    Graph,
    GraphEdge,
    GraphNode,
    NodeType,
)
from sfir_backend.domain.graph.traversal import TraversalContext
from sfir_backend.infrastructure.graph import (
    CycleDetectionEngine,
    DependencyGraphEngine,
    DependencyResolver,
    GraphBuilder,
    GraphCacheCoordinator,
    GraphStatistics,
    GraphTraversalEngine,
    GraphValidator,
    GraphVersionManager,
)
from sfir_backend.infrastructure.parsers.base import (
    ExtractedRelationship,
)

# ─── Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def sample_graph() -> Graph:
    g = Graph(version="test-v1", created_at=datetime.now(tz=UTC))
    for name in ["Account", "Contact", "User", "Opportunity", "Case"]:
        g.add_node(GraphNode(api_name=name, node_type=NodeType.OBJECT))
    g.add_node(GraphNode(api_name="Account.Name", node_type=NodeType.FIELD))
    g.add_node(GraphNode(api_name="Account.OwnerId", node_type=NodeType.FIELD))
    g.add_node(GraphNode(api_name="MyController", node_type=NodeType.APEX_CLASS))
    g.add_node(GraphNode(api_name="MyFlow", node_type=NodeType.FLOW))
    g.add_node(GraphNode(api_name="MyValidationRule", node_type=NodeType.VALIDATION_RULE))

    g.add_edge(
        GraphEdge(
            source_id="field:Account.OwnerId",
            target_id="object:User",
            edge_type=EdgeType.LOOKUP,
        )
    )
    g.add_edge(
        GraphEdge(
            source_id="object:Account", target_id="field:Account.Name", edge_type=EdgeType.CONTAINS
        )
    )
    g.add_edge(
        GraphEdge(
            source_id="object:Account",
            target_id="field:Account.OwnerId",
            edge_type=EdgeType.CONTAINS,
        )
    )
    g.add_edge(
        GraphEdge(
            source_id="apex_class:MyController",
            target_id="object:Account",
            edge_type=EdgeType.APEX_REFERENCE,
        )
    )
    g.add_edge(
        GraphEdge(
            source_id="apex_class:MyController",
            target_id="object:Contact",
            edge_type=EdgeType.APEX_REFERENCE,
        )
    )
    g.add_edge(
        GraphEdge(
            source_id="flow:MyFlow", target_id="object:Account", edge_type=EdgeType.FLOW_REFERENCE
        )
    )
    g.add_edge(
        GraphEdge(
            source_id="flow:MyFlow",
            target_id="object:Opportunity",
            edge_type=EdgeType.FLOW_REFERENCE,
        )
    )
    g.add_edge(
        GraphEdge(
            source_id="validation_rule:MyValidationRule",
            target_id="field:Account.Name",
            edge_type=EdgeType.VALIDATION_REFERENCE,
        )
    )
    return g


# ─── GraphBuilder ──────────────────────────────────────────────

class TestGraphBuilder:
    def test_build_from_components(self) -> None:
        builder = GraphBuilder()
        components = [
            MetadataObject(api_name="Account", label="Account"),
            MetadataField(api_name="Account.Name", label="Name", object_api_name="Account"),
        ]
        relationships = [
            ExtractedRelationship(
                type="contains",
                source_api_name="Account",
                source_type="object",
                target_api_name="Account.Name",
                target_type="field",
            ),
        ]
        graph = builder.build(components, relationships)
        assert graph.node_count >= 2
        assert graph.edge_count >= 1

    def test_build_empty(self) -> None:
        builder = GraphBuilder()
        graph = builder.build([], [])
        assert graph.node_count == 0
        assert graph.edge_count == 0

    def test_incremental_update_add(self) -> None:
        builder = GraphBuilder()
        initial = builder.build(
            [MetadataObject(api_name="A", label="A")],
            [],
        )
        updated = builder.incremental_update(
            initial,
            new_components=[MetadataObject(api_name="B", label="B")],
        )
        assert updated.node_count == 2

    def test_incremental_update_delete(self) -> None:
        builder = GraphBuilder()
        initial = builder.build(
            [MetadataObject(api_name="A", label="A")],
            [],
        )
        updated = builder.incremental_update(
            initial,
            deleted_api_names=["A"],
        )
        assert updated.node_count == 0


# ─── GraphTraversalEngine ──────────────────────────────────────

class TestGraphTraversal:
    def test_dfs(self, sample_graph: Graph) -> None:
        engine = GraphTraversalEngine()
        result = engine.dfs(sample_graph, "object:Account")
        assert result.total_nodes_visited > 0
        assert len(result.paths) > 0

    def test_dfs_with_depth_limit(self, sample_graph: Graph) -> None:
        engine = GraphTraversalEngine()
        ctx = TraversalContext(max_depth=1)
        result = engine.dfs(sample_graph, "object:Account", ctx)
        assert result.total_nodes_visited <= 3  # Account + 2 fields

    def test_bfs(self, sample_graph: Graph) -> None:
        engine = GraphTraversalEngine()
        result = engine.bfs(sample_graph, "apex_class:MyController")
        assert result.total_nodes_visited > 0

    def test_shortest_path_found(self, sample_graph: Graph) -> None:
        engine = GraphTraversalEngine()
        result = engine.shortest_path(
            sample_graph,
            "apex_class:MyController",
            "object:User",
        )
        assert len(result.paths) > 0

    def test_shortest_path_not_found(self, sample_graph: Graph) -> None:
        engine = GraphTraversalEngine()
        result = engine.shortest_path(
            sample_graph,
            "object:Account",
            "object:NonExistent",
        )
        assert len(result.paths) == 0

    def test_find_descendants(self, sample_graph: Graph) -> None:
        engine = GraphTraversalEngine()
        descendants = engine.find_descendants(sample_graph, "apex_class:MyController")
        assert len(descendants) >= 2  # Account, Contact

    def test_find_ancestors(self, sample_graph: Graph) -> None:
        engine = GraphTraversalEngine()
        ancestors = engine.find_ancestors(sample_graph, "field:Account.Name")
        assert len(ancestors) >= 2  # Account, MyValidationRule

    def test_subgraph(self, sample_graph: Graph) -> None:
        engine = GraphTraversalEngine()
        sub = engine.subgraph(sample_graph, {"object:Account"}, depth=2)
        assert sub.node_count >= 3  # Account + 2 fields + User via lookup


# ─── DependencyResolver ────────────────────────────────────────

class TestDependencyResolver:
    def test_where_used(self, sample_graph: Graph) -> None:
        resolver = DependencyResolver()
        # Where is User used?
        users = resolver.where_used(sample_graph, "User")
        assert len(users) > 0
        # Account.OwnerId references User, Account contains Account.OwnerId

    def test_what_depends_on(self, sample_graph: Graph) -> None:
        resolver = DependencyResolver()
        # What does Account depend on?
        deps = resolver.what_depends_on(sample_graph, "Account")
        assert len(deps) >= 2  # Account.Name, Account.OwnerId

    def test_find_orphaned(self) -> None:
        g = Graph()
        g.add_node(GraphNode(api_name="Alone", node_type=NodeType.OBJECT))
        resolver = DependencyResolver()
        orphaned = resolver.find_orphaned(g)
        assert len(orphaned) == 1
        assert orphaned[0].api_name == "Alone"

    def test_find_unreachable(self, sample_graph: Graph) -> None:
        g = sample_graph
        g.add_node(GraphNode(api_name="Island", node_type=NodeType.OBJECT))
        resolver = DependencyResolver()
        unreachable = resolver.find_unreachable(g)
        assert len(unreachable) >= 1
        names = [n.api_name for n in unreachable]
        assert "Island" in names

    def test_dependency_depth(self, sample_graph: Graph) -> None:
        resolver = DependencyResolver()
        depth = resolver.dependency_depth(sample_graph, "object:Account")
        assert depth >= 0


# ─── CycleDetectionEngine ──────────────────────────────────────

class TestCycleDetection:
    def test_no_cycles(self, sample_graph: Graph) -> None:
        detector = CycleDetectionEngine()
        cycles = detector.detect_cycles(sample_graph)
        assert len(cycles) == 0

    def test_detects_cycle(self) -> None:
        g = Graph()
        for name in ["A", "B", "C"]:
            g.add_node(GraphNode(api_name=name, node_type=NodeType.OBJECT))
        g.add_edge(GraphEdge(source_id="object:A", target_id="object:B"))
        g.add_edge(GraphEdge(source_id="object:B", target_id="object:C"))
        g.add_edge(GraphEdge(source_id="object:C", target_id="object:A"))
        detector = CycleDetectionEngine()
        cycles = detector.detect_cycles(g)
        assert len(cycles) >= 1

    def test_has_cycles(self) -> None:
        g = Graph()
        for name in ["A", "B"]:
            g.add_node(GraphNode(api_name=name, node_type=NodeType.OBJECT))
        g.add_edge(GraphEdge(source_id="object:A", target_id="object:B"))
        g.add_edge(GraphEdge(source_id="object:B", target_id="object:A"))
        detector = CycleDetectionEngine()
        assert detector.has_cycles(g) is True

    def test_self_references(self) -> None:
        g = Graph()
        g.add_node(GraphNode(api_name="Self", node_type=NodeType.OBJECT))
        g.add_edge(GraphEdge(source_id="object:Self", target_id="object:Self"))
        detector = CycleDetectionEngine()
        self_refs = detector.find_self_references(g)
        assert len(self_refs) == 1


# ─── GraphValidator ────────────────────────────────────────────

class TestGraphValidator:
    def test_valid_graph(self, sample_graph: Graph) -> None:
        validator = GraphValidator()
        result = validator.integrity_check(sample_graph)
        assert result["is_valid"] is True

    def test_broken_edge(self) -> None:
        g = Graph()
        g.add_node(GraphNode(api_name="A", node_type=NodeType.OBJECT))
        g.add_edge(GraphEdge(source_id="object:A", target_id="object:MISSING"))
        validator = GraphValidator()
        issues = validator.validate(g)
        assert len(issues["broken_edges"]) > 0

    def test_duplicate_edge(self) -> None:
        g = Graph()
        g.add_node(GraphNode(api_name="A", node_type=NodeType.OBJECT))
        g.add_node(GraphNode(api_name="B", node_type=NodeType.OBJECT))
        g.add_edge(GraphEdge(id="e1", source_id="object:A", target_id="object:B"))
        g.add_edge(GraphEdge(id="e2", source_id="object:A", target_id="object:B"))
        validator = GraphValidator()
        issues = validator.validate(g)
        assert len(issues["duplicate_edges"]) > 0

    def test_consistency_check(self, sample_graph: Graph) -> None:
        validator = GraphValidator()
        result = validator.consistency_check(sample_graph)
        assert result["consistent"] is True


# ─── GraphVersionManager ───────────────────────────────────────

class TestGraphVersionManager:
    def test_create_version(self, sample_graph: Graph) -> None:
        mgr = GraphVersionManager()
        version = mgr.create_version(sample_graph, change_summary="test")
        assert version.version
        assert version.node_count > 0
        assert mgr.current_version == version.version

    def test_create_snapshot(self, sample_graph: Graph) -> None:
        mgr = GraphVersionManager()
        snap = mgr.create_snapshot(sample_graph, "initial")
        assert snap.snapshot_id
        assert snap.graph.node_count == sample_graph.node_count

    def test_list_versions(self, sample_graph: Graph) -> None:
        mgr = GraphVersionManager()
        mgr.create_version(sample_graph, change_summary="v1")
        mgr.create_version(sample_graph, change_summary="v2")
        assert len(mgr.list_versions()) == 2

    def test_rollback(self, sample_graph: Graph) -> None:
        mgr = GraphVersionManager()
        snap1 = mgr.create_snapshot(sample_graph, "first")
        mgr.create_snapshot(sample_graph, "second")
        rolled = mgr.rollback_to_version(snap1.version)
        assert rolled is not None
        assert rolled.version == snap1.version


# ─── GraphCacheCoordinator ─────────────────────────────────────

class TestGraphCache:
    def test_set_and_get(self, sample_graph: Graph) -> None:
        cache = GraphCacheCoordinator()
        cache.set("test", sample_graph)
        retrieved = cache.get("test")
        assert retrieved is not None
        assert retrieved.node_count == sample_graph.node_count

    def test_invalidate(self, sample_graph: Graph) -> None:
        cache = GraphCacheCoordinator()
        cache.set("test", sample_graph)
        cache.invalidate("test")
        assert cache.get("test") is None

    def test_cache_eviction(self) -> None:
        cache = GraphCacheCoordinator()
        for i in range(20):
            g = Graph(version=str(i))
            cache.set(f"key{i}", g)
        assert cache.cache_size <= 10


# ─── GraphStatistics ───────────────────────────────────────────

class TestGraphStatistics:
    def test_node_count_by_type(self, sample_graph: Graph) -> None:
        stats = GraphStatistics()
        counts = stats.node_count_by_type(sample_graph)
        assert counts.get("object", 0) == 5
        assert counts.get("field", 0) == 2

    def test_edge_count_by_type(self, sample_graph: Graph) -> None:
        stats = GraphStatistics()
        counts = stats.edge_count_by_type(sample_graph)
        assert counts.get("contains", 0) == 2

    def test_avg_degree(self, sample_graph: Graph) -> None:
        stats = GraphStatistics()
        degree = stats.avg_degree(sample_graph)
        assert degree > 0

    def test_snapshot(self, sample_graph: Graph) -> None:
        stats = GraphStatistics()
        snap = stats.snapshot(sample_graph)
        assert snap["node_count"] > 0
        assert snap["edge_count"] > 0


# ─── DependencyGraphEngine ─────────────────────────────────────

class TestDependencyGraphEngine:
    def test_build_from_components(self) -> None:
        engine = DependencyGraphEngine()
        components = [
            MetadataObject(api_name="Account", label="Account"),
            MetadataField(api_name="Account.Name", label="Name"),
        ]
        relationships = [
            ExtractedRelationship(
                type="contains",
                source_api_name="Account",
                source_type="object",
                target_api_name="Account.Name",
                target_type="field",
            ),
        ]
        engine.build(components, relationships)
        assert engine.graph.node_count >= 2
        assert engine.version != ""

    def test_dfs_via_engine(self, sample_graph: Graph) -> None:
        engine = DependencyGraphEngine()
        engine._graph = sample_graph
        result = engine.dfs("object:Account", max_depth=5)
        assert result.total_nodes_visited > 0

    def test_where_used_via_engine(self, sample_graph: Graph) -> None:
        engine = DependencyGraphEngine()
        engine._graph = sample_graph
        users = engine.where_used("User")
        assert len(users) > 0

    def test_detect_cycles_via_engine(self) -> None:
        engine = DependencyGraphEngine()
        g = Graph()
        for name in ["A", "B"]:
            g.add_node(GraphNode(api_name=name, node_type=NodeType.OBJECT))
        g.add_edge(GraphEdge(source_id="object:A", target_id="object:B"))
        g.add_edge(GraphEdge(source_id="object:B", target_id="object:A"))
        engine._graph = g
        assert engine.has_cycles() is True
        assert len(engine.cycle_diagnostics()["cycles"]) >= 1

    def test_validate_via_engine(self, sample_graph: Graph) -> None:
        engine = DependencyGraphEngine()
        engine._graph = sample_graph
        result = engine.validate()
        assert result["is_valid"] is True

    def test_statistics_via_engine(self, sample_graph: Graph) -> None:
        engine = DependencyGraphEngine()
        engine._graph = sample_graph
        stats = engine.statistics()
        assert stats["node_count"] > 0
        assert stats["edge_count"] > 0

    def test_snapshots(self) -> None:
        engine = DependencyGraphEngine()
        components = [MetadataObject(api_name="A", label="A")]
        engine.build(components)
        assert len(engine.list_snapshots()) >= 1

    def test_rollback(self) -> None:
        engine = DependencyGraphEngine()
        engine.build([MetadataObject(api_name="A", label="A")])
        snapshots = engine.list_snapshots()
        assert len(snapshots) >= 1
        snapshot_id = snapshots[0].snapshot_id
        engine.rollback(snapshot_id)
        assert engine.graph.node_count >= 1

    def test_incremental_update(self) -> None:
        engine = DependencyGraphEngine()
        engine.build([MetadataObject(api_name="A", label="A")])
        engine.incremental_update(
            new_components=[MetadataObject(api_name="B", label="B")],
        )
        assert engine.graph.node_count == 2

    def test_find_orphaned_via_engine(self) -> None:
        engine = DependencyGraphEngine()
        engine.build([MetadataObject(api_name="Alone", label="Alone")])
        orphaned = engine.find_orphaned()
        assert len(orphaned) == 1
