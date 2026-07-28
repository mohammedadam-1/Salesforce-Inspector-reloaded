from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest

from sfir_backend.application.pipeline.pipeline_context import PipelineContext
from sfir_backend.application.pipeline.stages import GraphStage
from sfir_backend.domain.graph.models import (
    EdgeType,
    Graph,
    GraphEdge,
    GraphNode,
    NodeType,
)
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


def _normalized_doc(
    api_name: str = "TestClass",
    type_name: str = "ApexClass",
    identity: str | None = None,
    fingerprint: str = "fp123",
    relationships: list[dict] | None = None,
) -> dict[str, Any]:
    return {
        "identity": identity or uuid.uuid4().hex,
        "api_name": api_name,
        "type": type_name,
        "fingerprint": fingerprint or uuid.uuid4().hex,
        "content_hash": uuid.uuid4().hex,
        "qualified_name": api_name,
        "fully_qualified_name": api_name,
        "version": 1,
        "status": "active",
        "source_platform": "salesforce",
        "organization_id": str(uuid.uuid4()),
        "label": api_name,
        "namespace": None,
        "relationships": relationships or [],
    }


def _rel(
    rel_type: str = "references",
    target_type: str = "CustomObject",
    target_api_name: str = "Account",
    target_namespace: str | None = None,
    target_fqdn: str = "Account",
) -> dict[str, Any]:
    return {
        "type": rel_type,
        "target_identity": uuid.uuid4().hex,
        "target_component_key": {
            "type": target_type,
            "api_name": target_api_name,
            "namespace": target_namespace,
        },
        "target_fqdn": target_fqdn,
        "metadata": {},
    }


def _make_context(normalized_components: list[dict] | None = None) -> PipelineContext:
    return PipelineContext(
        organization_id=UUID("00000000-0000-0000-0000-000000000001"),
        connection_id=UUID("00000000-0000-0000-0000-000000000002"),
        sync_job_id=UUID("00000000-0000-0000-0000-000000000003"),
        normalized_components=normalized_components or [],
    )


# ===================================================================
# GraphBuilder — build_from_normalized
# ===================================================================


class TestGraphBuilderFromNormalized:
    def test_build_basic_graph(self) -> None:
        builder = GraphBuilder()
        docs = [
            _normalized_doc(api_name="Account", type_name="CustomObject"),
            _normalized_doc(api_name="Contact", type_name="CustomObject"),
        ]
        graph = builder.build_from_normalized(docs)
        assert graph.node_count == 2
        assert graph.edge_count == 0
        assert graph.get_node("object:Account") is not None
        assert graph.get_node("object:Contact") is not None

    def test_build_with_relationships(self) -> None:
        builder = GraphBuilder()
        docs = [
            _normalized_doc(
                api_name="Account",
                type_name="CustomObject",
                relationships=[
                    _rel("contains", "CustomField", "Account.Name", target_fqdn="Account.Name"),
                ],
            ),
            _normalized_doc(api_name="Account.Name", type_name="CustomField"),
        ]
        graph = builder.build_from_normalized(docs)
        assert graph.node_count == 2
        assert graph.edge_count == 1

    def test_build_empty(self) -> None:
        builder = GraphBuilder()
        graph = builder.build_from_normalized([])
        assert graph.node_count == 0
        assert graph.edge_count == 0

    def test_build_with_multiple_relationship_types(self) -> None:
        builder = GraphBuilder()
        docs = [
            _normalized_doc(
                api_name="MyTrigger",
                type_name="ApexTrigger",
                relationships=[
                    _rel("triggers", "CustomObject", "Account"),
                    _rel("references", "ApexClass", "UtilClass"),
                ],
            ),
            _normalized_doc(api_name="Account", type_name="CustomObject"),
            _normalized_doc(api_name="UtilClass", type_name="ApexClass"),
        ]
        graph = builder.build_from_normalized(docs)
        assert graph.node_count == 3
        assert graph.edge_count == 2

    def test_relationship_to_unknown_target_creates_edge(self) -> None:
        builder = GraphBuilder()
        docs = [
            _normalized_doc(
                api_name="MyClass",
                type_name="ApexClass",
                relationships=[_rel("references", "CustomObject", "TargetObj")],
            ),
        ]
        graph = builder.build_from_normalized(docs)
        assert graph.node_count == 1
        assert graph.edge_count >= 1

    def test_type_mapping_from_relationship(self) -> None:
        builder = GraphBuilder()
        docs = [
            _normalized_doc(
                api_name="MyFlow",
                type_name="Flow",
                relationships=[
                    _rel("depends_on", "CustomObject", "Account"),
                    _rel("flow_create", "CustomObject", "Contact"),
                ],
            ),
            _normalized_doc(api_name="Account", type_name="CustomObject"),
            _normalized_doc(api_name="Contact", type_name="CustomObject"),
        ]
        graph = builder.build_from_normalized(docs)
        edges = list(graph.edges.values())
        edge_types = {e.edge_type for e in edges}
        assert EdgeType.USES in edge_types
        assert EdgeType.FLOW_REFERENCE in edge_types

    def test_deterministic_build(self) -> None:
        builder = GraphBuilder()
        docs = [
            _normalized_doc(api_name="A", type_name="CustomObject"),
            _normalized_doc(api_name="B", type_name="CustomObject"),
        ]
        graph1 = builder.build_from_normalized(docs)
        graph2 = builder.build_from_normalized(docs)
        assert graph1.node_count == graph2.node_count
        assert set(graph1.nodes.keys()) == set(graph2.nodes.keys())

    def test_different_fingerprint_same_graph_structure(self) -> None:
        builder = GraphBuilder()
        docs1 = [_normalized_doc(api_name="A", type_name="CustomObject", fingerprint="fp1")]
        docs2 = [_normalized_doc(api_name="A", type_name="CustomObject", fingerprint="fp2")]
        g1 = builder.build_from_normalized(docs1)
        g2 = builder.build_from_normalized(docs2)
        assert g1.node_count == g2.node_count
        assert g1.nodes["object:A"].metadata.get("fingerprint") == "fp1"
        assert g2.nodes["object:A"].metadata.get("fingerprint") == "fp2"

    def test_large_graph(self) -> None:
        builder = GraphBuilder()
        docs: list[dict] = []
        for i in range(100):
            obj_name = f"Obj{i}"
            docs.append(
                _normalized_doc(
                    api_name=obj_name,
                    type_name="CustomObject",
                    relationships=[
                        _rel("contains", "CustomField", f"{obj_name}.Name"),
                    ],
                ),
            )
            docs.append(
                _normalized_doc(api_name=f"{obj_name}.Name", type_name="CustomField"),
            )
        graph = builder.build_from_normalized(docs)
        assert graph.node_count == 200
        assert graph.edge_count == 100


# ===================================================================
# GraphBuilder — incremental_update_from_normalized
# ===================================================================


class TestGraphBuilderIncrementalFromNormalized:
    def test_incremental_add(self) -> None:
        builder = GraphBuilder()
        initial = builder.build_from_normalized(
            [_normalized_doc(api_name="A", type_name="CustomObject")],
        )
        updated = builder.incremental_update_from_normalized(
            initial,
            normalized_components=[_normalized_doc(api_name="B", type_name="CustomObject")],
        )
        assert updated.node_count == 2

    def test_incremental_delete(self) -> None:
        builder = GraphBuilder()
        initial = builder.build_from_normalized(
            [_normalized_doc(api_name="A", type_name="CustomObject")],
        )
        updated = builder.incremental_update_from_normalized(
            initial,
            deleted_api_names=["A"],
        )
        assert updated.node_count == 0

    def test_incremental_add_with_relationships(self) -> None:
        builder = GraphBuilder()
        initial = builder.build_from_normalized(
            [_normalized_doc(api_name="A", type_name="CustomObject")],
        )
        updated = builder.incremental_update_from_normalized(
            initial,
            normalized_components=[
                _normalized_doc(
                    api_name="B",
                    type_name="CustomObject",
                    relationships=[_rel("references", "CustomObject", "A")],
                ),
            ],
        )
        assert updated.node_count == 2
        assert updated.edge_count >= 1

    def test_incremental_update_replaces_node(self) -> None:
        builder = GraphBuilder()
        initial = builder.build_from_normalized(
            [_normalized_doc(api_name="A", type_name="CustomObject", fingerprint="old")],
        )
        assert initial.nodes["object:A"].metadata.get("fingerprint") == "old"
        updated = builder.incremental_update_from_normalized(
            initial,
            normalized_components=[
                _normalized_doc(api_name="A", type_name="CustomObject", fingerprint="new"),
            ],
        )
        assert updated.nodes["object:A"].metadata.get("fingerprint") == "new"

    def test_incremental_idempotent(self) -> None:
        builder = GraphBuilder()
        doc = _normalized_doc(api_name="A", type_name="CustomObject")
        initial = builder.build_from_normalized([doc])
        updated = builder.incremental_update_from_normalized(initial, normalized_components=[doc])
        assert updated.node_count == 1

    def test_incremental_delete_nonexistent(self) -> None:
        builder = GraphBuilder()
        initial = builder.build_from_normalized(
            [_normalized_doc(api_name="A", type_name="CustomObject")],
        )
        updated = builder.incremental_update_from_normalized(initial, deleted_api_names=["NONEXISTENT"])
        assert updated.node_count == 1  # unchanged


# ===================================================================
# DependencyGraphEngine — build_from_normalized
# ===================================================================


class TestDependencyGraphEngineFromNormalized:
    def test_build_from_normalized(self) -> None:
        engine = DependencyGraphEngine()
        docs = [
            _normalized_doc(api_name="Account", type_name="CustomObject"),
            _normalized_doc(api_name="Contact", type_name="CustomObject"),
        ]
        engine.build_from_normalized(docs)
        assert engine.graph.node_count == 2
        assert engine.version != ""

    def test_build_from_normalized_with_relationships(self) -> None:
        engine = DependencyGraphEngine()
        docs = [
            _normalized_doc(
                api_name="MyController",
                type_name="ApexClass",
                relationships=[_rel("references", "CustomObject", "Account")],
            ),
            _normalized_doc(api_name="Account", type_name="CustomObject"),
        ]
        engine.build_from_normalized(docs)
        assert engine.graph.node_count == 2
        assert engine.graph.edge_count >= 1

    def test_build_with_cache(self) -> None:
        engine = DependencyGraphEngine()
        docs = [_normalized_doc(api_name="A", type_name="CustomObject")]
        engine.build_from_normalized(docs, cache_key="test")
        cached = engine._cache.get("test")
        assert cached is not None
        assert cached.node_count == 1

    def test_incremental_update_from_normalized(self) -> None:
        engine = DependencyGraphEngine()
        engine.build_from_normalized([_normalized_doc(api_name="A", type_name="CustomObject")])
        engine.incremental_update_from_normalized(
            normalized_components=[_normalized_doc(api_name="B", type_name="CustomObject")],
        )
        assert engine.graph.node_count == 2

    def test_snapshot_after_build(self) -> None:
        engine = DependencyGraphEngine()
        engine.build_from_normalized([_normalized_doc(api_name="A", type_name="CustomObject")])
        snapshots = engine.list_snapshots()
        assert len(snapshots) >= 1

    def test_statistics_after_build(self) -> None:
        engine = DependencyGraphEngine()
        docs = [
            _normalized_doc(api_name="Account", type_name="CustomObject"),
            _normalized_doc(
                api_name="MyClass",
                type_name="ApexClass",
                relationships=[_rel("references", "CustomObject", "Account")],
            ),
        ]
        engine.build_from_normalized(docs)
        stats = engine.statistics()
        assert stats["node_count"] == 2
        assert stats["edge_count"] >= 1

    def test_traversal_after_build(self) -> None:
        engine = DependencyGraphEngine()
        docs = [
            _normalized_doc(
                api_name="MyClass",
                type_name="apex_class",
                relationships=[_rel("references", "CustomObject", "Account")],
            ),
            _normalized_doc(api_name="Account", type_name="CustomObject"),
        ]
        engine.build_from_normalized(docs)
        result = engine.dfs("apex_class:MyClass")
        assert result.total_nodes_visited > 0

    def test_cycle_detection_after_build(self) -> None:
        engine = DependencyGraphEngine()
        engine._graph = Graph()
        engine._graph.add_node(GraphNode(api_name="A", node_type=NodeType.OBJECT))
        engine._graph.add_node(GraphNode(api_name="B", node_type=NodeType.OBJECT))
        engine._graph.add_edge(GraphEdge(source_id="object:A", target_id="object:B"))
        engine._graph.add_edge(GraphEdge(source_id="object:B", target_id="object:A"))
        assert engine.has_cycles() is True

    def test_rollback(self) -> None:
        engine = DependencyGraphEngine()
        engine.build_from_normalized([_normalized_doc(api_name="A", type_name="CustomObject")])
        snapshots = engine.list_snapshots()
        engine.build_from_normalized([_normalized_doc(api_name="B", type_name="CustomObject")])
        engine.rollback(snapshots[0].version)
        assert engine.graph.node_count >= 1


# ===================================================================
# GraphStage Integration
# ===================================================================


class TestGraphStage:
    @pytest.mark.asyncio
    async def test_stage_builds_graph_from_normalized(self) -> None:
        engine = DependencyGraphEngine()
        stage = GraphStage(graph_engine=engine)
        ctx = _make_context(
            normalized_components=[
                _normalized_doc(api_name="Account", type_name="CustomObject"),
                _normalized_doc(api_name="Contact", type_name="CustomObject"),
            ],
        )
        result = await stage.execute(ctx)
        assert result.graph_result["node_count"] == 2
        assert result.graph_result["edge_count"] == 0
        assert result.graph_version != ""
        assert "node_count" in result.graph_statistics

    @pytest.mark.asyncio
    async def test_stage_builds_with_relationships(self) -> None:
        engine = DependencyGraphEngine()
        stage = GraphStage(graph_engine=engine)
        ctx = _make_context(
            normalized_components=[
                _normalized_doc(
                    api_name="MyClass",
                    type_name="ApexClass",
                    relationships=[_rel("references", "CustomObject", "Account")],
                ),
                _normalized_doc(api_name="Account", type_name="CustomObject"),
            ],
        )
        result = await stage.execute(ctx)
        assert result.graph_result["node_count"] == 2
        assert result.graph_result["edge_count"] >= 1

    @pytest.mark.asyncio
    async def test_stage_empty_components_skips(self) -> None:
        engine = DependencyGraphEngine()
        stage = GraphStage(graph_engine=engine)
        ctx = _make_context(normalized_components=[])
        result = await stage.execute(ctx)
        assert result.graph_result == {}
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_stage_sets_graph_statistics(self) -> None:
        engine = DependencyGraphEngine()
        stage = GraphStage(graph_engine=engine)
        ctx = _make_context(
            normalized_components=[
                _normalized_doc(api_name="A", type_name="CustomObject"),
                _normalized_doc(api_name="B", type_name="CustomObject"),
            ],
        )
        result = await stage.execute(ctx)
        assert "node_count" in result.graph_statistics
        assert "edge_count" in result.graph_statistics
        assert "node_types" in result.graph_statistics

    @pytest.mark.asyncio
    async def test_stage_sets_graph_version(self) -> None:
        engine = DependencyGraphEngine()
        stage = GraphStage(graph_engine=engine)
        ctx = _make_context(
            normalized_components=[_normalized_doc(api_name="A", type_name="CustomObject")],
        )
        result = await stage.execute(ctx)
        assert result.graph_version != ""
        assert result.graph_version == result.graph_result["version"]

    @pytest.mark.asyncio
    async def test_stage_error_handling(self) -> None:
        class ExplodingEngine:
            @property
            def graph(self) -> Graph:
                return Graph()

            @property
            def version(self) -> str:
                return ""

            def build_from_normalized(self, normalized_components: list[dict], cache_key: str | None = None) -> Graph:
                raise RuntimeError("Engine exploded")

            def statistics(self) -> dict:
                return {}

        stage = GraphStage(graph_engine=ExplodingEngine())  # type: ignore[arg-type]
        ctx = _make_context(
            normalized_components=[_normalized_doc(api_name="A", type_name="CustomObject")],
        )
        result = await stage.execute(ctx)
        assert len(result.errors) >= 1
        assert any("Engine exploded" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_stage_name(self) -> None:
        engine = DependencyGraphEngine()
        stage = GraphStage(graph_engine=engine)
        assert stage.name == "graph"

    @pytest.mark.asyncio
    async def test_stage_pipeline_contract(self) -> None:
        engine = DependencyGraphEngine()
        stage = GraphStage(graph_engine=engine)
        ctx = _make_context(
            normalized_components=[
                _normalized_doc(api_name="A", type_name="CustomObject"),
            ],
        )
        result = await stage.execute(ctx)
        assert isinstance(result, PipelineContext)
        assert result is ctx  # same object returned


# ===================================================================
# Edge cases and error handling
# ===================================================================


class TestGraphEdgeCases:
    def test_duplicate_edges(self) -> None:
        builder = GraphBuilder()
        docs = [
            _normalized_doc(
                api_name="A",
                type_name="CustomObject",
                relationships=[_rel("references", "CustomObject", "B")],
            ),
            _normalized_doc(api_name="B", type_name="CustomObject"),
        ]
        graph = builder.build_from_normalized(docs)
        validator = GraphValidator()
        issues = validator.validate(graph)
        assert len(issues.get("duplicate_edges", [])) == 0

    def test_self_referencing_relationship(self) -> None:
        builder = GraphBuilder()
        docs = [
            _normalized_doc(
                api_name="Self",
                type_name="CustomObject",
                relationships=[_rel("references", "CustomObject", "Self")],
            ),
        ]
        graph = builder.build_from_normalized(docs)
        detector = CycleDetectionEngine()
        self_refs = detector.find_self_references(graph)
        assert len(self_refs) >= 1

    def test_missing_target_type_defaults_to_object_in_edge(self) -> None:
        builder = GraphBuilder()
        rel = {
            "type": "references",
            "target_identity": uuid.uuid4().hex,
            "target_component_key": {"type": "", "api_name": "Target"},
            "target_fqdn": "Target",
            "metadata": {},
        }
        docs = [
            _normalized_doc(
                api_name="Source",
                type_name="ApexClass",
                relationships=[rel],
            ),
        ]
        graph = builder.build_from_normalized(docs)
        edges = list(graph.edges.values())
        assert len(edges) == 1
        assert edges[0].target_id == "object:Target"

    def test_all_edge_types_mapped(self) -> None:
        builder = GraphBuilder()
        edge_type_strings = {
            "contains", "references", "depends_on", "lookup",
            "master_detail", "trigger_on", "soql_ref",
            "flow_create", "flow_update", "flow_delete", "flow_subflow",
            "string_ref", "list_ref", "dict_ref",
        }
        rels = [_rel(rel_type, "CustomObject", "Target") for rel_type in edge_type_strings]
        docs = [
            _normalized_doc(api_name="Source", type_name="ApexClass", relationships=rels),
            _normalized_doc(api_name="Target", type_name="CustomObject"),
        ]
        graph = builder.build_from_normalized(docs)
        edge_types_in_graph = {e.edge_type for e in graph.edges.values()}
        for rel_type_str in edge_type_strings:
            mapped = builder.EDGE_TYPE_MAP.get(rel_type_str)
            assert mapped is not None, f"{rel_type_str} not mapped"
            assert mapped in edge_types_in_graph, f"{rel_type_str} -> {mapped} not in graph"

    def test_node_with_missing_api_name_skipped(self) -> None:
        builder = GraphBuilder()
        doc = _normalized_doc(api_name="", type_name="CustomObject")
        graph = builder.build_from_normalized([doc])
        assert graph.node_count == 0

    def test_node_with_missing_type_skipped(self) -> None:
        builder = GraphBuilder()
        doc = _normalized_doc(api_name="NoType", type_name="")
        graph = builder.build_from_normalized([doc])
        assert graph.node_count == 0


# ===================================================================
# Fingerprint-aware updates
# ===================================================================


class TestFingerprintAwareUpdates:
    def test_fingerprint_stored_in_node_metadata(self) -> None:
        builder = GraphBuilder()
        doc = _normalized_doc(api_name="A", type_name="CustomObject", fingerprint="my_fp")
        graph = builder.build_from_normalized([doc])
        node = graph.get_node("object:A")
        assert node is not None
        assert node.metadata.get("fingerprint") == "my_fp"

    def test_incremental_update_changes_fingerprint(self) -> None:
        builder = GraphBuilder()
        initial = builder.build_from_normalized(
            [_normalized_doc(api_name="A", type_name="CustomObject", fingerprint="old")],
        )
        updated = builder.incremental_update_from_normalized(
            initial,
            normalized_components=[
                _normalized_doc(api_name="A", type_name="CustomObject", fingerprint="new"),
            ],
        )
        assert updated.nodes["object:A"].metadata.get("fingerprint") == "new"


# ===================================================================
# Pipeline contract: normalized_relationships field
# ===================================================================


class TestPipelineContextContracts:
    def test_normalized_relationships_field_exists(self) -> None:
        ctx = _make_context()
        assert hasattr(ctx, "normalized_relationships")
        assert ctx.normalized_relationships == []

    def test_graph_statistics_field_exists(self) -> None:
        ctx = _make_context()
        assert hasattr(ctx, "graph_statistics")
        assert ctx.graph_statistics == {}

    def test_graph_version_field_exists(self) -> None:
        ctx = _make_context()
        assert hasattr(ctx, "graph_version")
        assert ctx.graph_version == ""


# ===================================================================
# Legacy backward compatibility
# ===================================================================


class TestLegacyBackwardCompatibility:
    def test_old_build_method_still_works(self) -> None:
        from sfir_backend.domain.canonical import MetadataObject
        from sfir_backend.infrastructure.parsers.base import ExtractedRelationship

        builder = GraphBuilder()
        components = [MetadataObject(api_name="Account", label="Account")]
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
        assert graph.node_count >= 1
        assert graph.node_count >= 1

    def test_old_incremental_update_still_works(self) -> None:
        from sfir_backend.domain.canonical import MetadataObject

        builder = GraphBuilder()
        initial = builder.build([MetadataObject(api_name="A", label="A")])
        updated = builder.incremental_update(
            initial,
            new_components=[MetadataObject(api_name="B", label="B")],
        )
        assert updated.node_count == 2

    def test_old_engine_build_still_works(self) -> None:
        from sfir_backend.domain.canonical import MetadataObject

        engine = DependencyGraphEngine()
        engine.build([MetadataObject(api_name="A", label="A")])
        assert engine.graph.node_count == 1

    def test_old_engine_incremental_update_still_works(self) -> None:
        from sfir_backend.domain.canonical import MetadataObject

        engine = DependencyGraphEngine()
        engine.build([MetadataObject(api_name="A", label="A")])
        engine.incremental_update(new_components=[MetadataObject(api_name="B", label="B")])
        assert engine.graph.node_count == 2
