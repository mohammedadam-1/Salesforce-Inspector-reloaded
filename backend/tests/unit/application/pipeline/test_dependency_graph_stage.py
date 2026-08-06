"""DependencyGraphStage unit tests."""

from __future__ import annotations

import uuid

from sfir_backend.application.pipeline.pipeline_context import PipelineContext
from sfir_backend.application.pipeline.stages.dependency_graph_stage import (
    DependencyGraphStage,
)
from sfir_backend.domain.entities.canonical_document import CanonicalDocument
from sfir_backend.domain.entities.canonical_relationship import (
    CanonicalRelationship,
    CanonicalRelationshipType,
)

ORG_ID = uuid.uuid4()
CONN_ID = uuid.uuid4()
JOB_ID = uuid.uuid4()


def _document(identity: str, type_name: str, api_name: str) -> CanonicalDocument:
    return CanonicalDocument.create(
        organization_id=ORG_ID,
        identity=identity,
        type=type_name,
        api_name=api_name,
        developer_name=api_name,
        namespace=None,
        version=1,
        previous_version=0,
        fingerprint="fp",
    )


def _relationship() -> CanonicalRelationship:
    return CanonicalRelationship.create(
        organization_id=ORG_ID,
        source_identity="obj-Account",
        source_api_name="Account",
        source_type="object",
        target_identity="fld-Account.Name",
        target_api_name="Account.Name",
        target_type="field",
        relationship_type=CanonicalRelationshipType.OBJECT_TO_FIELD,
    )


class FakeCanonicalRepo:
    def __init__(self, documents: list[CanonicalDocument]) -> None:
        self.documents = documents
        self.list_latest_calls: list[tuple[int, int]] = []

    async def list_latest(self, organization_id, *, limit=1000, offset=0):
        self.list_latest_calls.append((limit, offset))
        return self.documents


class FakeRelationshipRepo:
    def __init__(self, relationships: list[CanonicalRelationship]) -> None:
        self.relationships = relationships
        self.list_active_calls: list[tuple[int, int]] = []

    async def list_active(self, organization_id, *, limit=1000, offset=0):
        self.list_active_calls.append((limit, offset))
        return self.relationships


class FakeGraphRepo:
    def __init__(self) -> None:
        self.upsert_nodes_calls: list[tuple[uuid.UUID, list]] = []
        self.upsert_edges_calls: list[tuple[uuid.UUID, list]] = []
        self.deleted_for_node: dict[str, int] = {}
        self.missing_for_source: dict[str, int] = {}

    async def upsert_nodes(self, organization_id, nodes):
        self.upsert_nodes_calls.append((organization_id, nodes))
        from sfir_backend.domain.entities.graph_node import GraphUpsertResult

        return GraphUpsertResult(created=len(nodes))

    async def upsert_edges(self, organization_id, edges):
        self.upsert_edges_calls.append((organization_id, edges))
        from sfir_backend.domain.entities.graph_node import GraphUpsertResult

        return GraphUpsertResult(created=len(edges))

    async def soft_delete_nodes(self, organization_id, identities, *, sync_job_id=None):
        return 0

    async def soft_delete_edges_for_node(self, organization_id, identity, *, sync_job_id=None):
        self.deleted_for_node[identity] = self.deleted_for_node.get(identity, 0) + 1
        return 1

    async def soft_delete_missing_edges_for_source(
        self, organization_id, source_identity, seen_edges, *, sync_job_id=None,
    ):
        key = source_identity
        self.missing_for_source[key] = self.missing_for_source.get(key, 0) + 1
        return 0

    async def soft_delete_edges_for_sources(
        self, organization_id, source_identities, *, sync_job_id=None,
    ):
        return 0

    async def list_active_edges(self, organization_id, *, limit=1000, offset=0):
        return []


def _context() -> PipelineContext:
    return PipelineContext(
        organization_id=ORG_ID,
        connection_id=CONN_ID,
        sync_job_id=JOB_ID,
    )


class TestDependencyGraphStage:
    async def test_builds_graph_from_canonical_state(self) -> None:
        docs = [
            _document("obj-Account", "object", "Account"),
            _document("fld-Account.Name", "field", "Account.Name"),
        ]
        rels = [_relationship()]
        canonical = FakeCanonicalRepo(docs)
        relationship = FakeRelationshipRepo(rels)
        graph = FakeGraphRepo()
        stage = DependencyGraphStage(graph, canonical, relationship)

        context = await stage.execute(_context())

        assert graph.upsert_nodes_calls[0][0] == ORG_ID
        assert len(graph.upsert_nodes_calls[0][1]) == 2
        assert len(graph.upsert_edges_calls[0][1]) == 1
        assert context.dependency_graph_result["nodes"]["created"] == 2
        assert context.dependency_graph_result["edges"]["created"] == 1

    async def test_endpoint_nodes_are_built_from_relationship_endpoints(self) -> None:
        docs = [_document("ps-Admin", "permission_set", "Admin")]
        rels = [
            CanonicalRelationship.create(
                organization_id=ORG_ID,
                source_identity="prf-Standard",
                source_api_name="Standard",
                source_type="profile",
                target_identity="ps-Admin",
                target_api_name="Admin",
                target_type="permission_set",
                relationship_type=CanonicalRelationshipType.PROFILE_TO_PERMISSION_SET,
            ),
        ]
        graph = FakeGraphRepo()
        stage = DependencyGraphStage(graph, FakeCanonicalRepo(docs), FakeRelationshipRepo(rels))

        context = await stage.execute(_context())

        identities = {node.identity for node in graph.upsert_nodes_calls[0][1]}
        assert identities == {"ps-Admin", "prf-Standard"}
        assert context.dependency_graph_result["nodes"]["endpoint_nodes_created"] == 1

    async def test_deleted_document_produces_deleted_node(self) -> None:
        doc = _document("obj-Account", "object", "Account")
        doc.soft_delete()
        graph = FakeGraphRepo()
        stage = DependencyGraphStage(graph, FakeCanonicalRepo([doc]), FakeRelationshipRepo([]))

        await stage.execute(_context())

        nodes = graph.upsert_nodes_calls[0][1]
        assert nodes[0].is_deleted
        assert graph.deleted_for_node.get("obj-Account") == 1

    async def test_empty_canonical_state_skips_builder(self) -> None:
        graph = FakeGraphRepo()
        stage = DependencyGraphStage(graph, FakeCanonicalRepo([]), FakeRelationshipRepo([]))

        context = await stage.execute(_context())

        assert graph.upsert_nodes_calls == []
        assert context.dependency_graph_result["nodes"]["created"] == 0
        assert context.dependency_graph_result["edges"]["created"] == 0

    async def test_passes_sync_job_id_through(self) -> None:
        docs = [_document("obj-Account", "object", "Account")]
        graph = FakeGraphRepo()
        stage = DependencyGraphStage(graph, FakeCanonicalRepo(docs), FakeRelationshipRepo([]))

        await stage.execute(_context())

        node = graph.upsert_nodes_calls[0][1][0]
        assert node.last_sync_job_id == JOB_ID

    async def test_result_defaults_in_context(self) -> None:
        context = _context()
        assert context.dependency_graph_result["nodes"]["created"] == 0
        assert context.dependency_graph_result["errors"] == []

    async     def test_created_at_fallbacks_never_break_summary(self) -> None:
        docs = [_document("obj-Account", "object", "Account")]
        graph = FakeGraphRepo()
        stage = DependencyGraphStage(graph, FakeCanonicalRepo(docs), FakeRelationshipRepo([]))

        context = await stage.execute(_context())

        assert context.dependency_graph_result["nodes"]["deleted"] == 0
        assert context.dependency_graph_result["edges"]["skipped"] == 0
        assert context.dependency_graph_result["stale_edges_deleted"] == 0
        assert context.dependency_graph_result["node_edge_deletions"] == 0
