"""DependencyGraphBuilder unit tests (in-memory fake graph repository)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sfir_backend.application.pipeline.graph.dependency_graph_builder import (
    DependencyGraphBuilder,
)
from sfir_backend.domain.canonical.base import MetadataStatus
from sfir_backend.domain.entities.canonical_document import CanonicalDocument
from sfir_backend.domain.entities.canonical_relationship import (
    CanonicalRelationship,
    CanonicalRelationshipType,
)
from sfir_backend.domain.entities.graph_edge import GraphEdge
from sfir_backend.domain.entities.graph_node import GraphNode, GraphUpsertResult
from sfir_backend.domain.repositories.graph_repo import IGraphRepository

ORG_ID = uuid.uuid4()
OTHER_ORG_ID = uuid.uuid4()
JOB_ID = uuid.uuid4()


def _document(
    identity: str,
    type_name: str,
    api_name: str,
    *,
    version: int = 1,
    fingerprint: str = "fp",
    deleted: bool = False,
) -> CanonicalDocument:
    doc = CanonicalDocument.create(
        organization_id=ORG_ID,
        identity=identity,
        type=type_name,
        api_name=api_name,
        developer_name=api_name,
        namespace=None,
        version=version,
        previous_version=version - 1,
        fingerprint=fingerprint,
    )
    if deleted:
        doc.soft_delete()
    return doc


def _relationship(
    source_identity: str,
    source_api_name: str,
    source_type: str,
    target_identity: str,
    target_api_name: str,
    target_type: str,
    relationship_type: CanonicalRelationshipType,
) -> CanonicalRelationship:
    return CanonicalRelationship.create(
        organization_id=ORG_ID,
        source_identity=source_identity,
        source_api_name=source_api_name,
        source_type=source_type,
        target_identity=target_identity,
        target_api_name=target_api_name,
        target_type=target_type,
        relationship_type=relationship_type,
    )


@dataclass
class _StoredNode:
    entity: GraphNode


@dataclass
class _StoredEdge:
    entity: GraphEdge


class FakeGraphRepository(IGraphRepository):
    """In-memory graph repository mirroring the SQLAlchemy semantics."""

    def __init__(self) -> None:
        self.nodes: dict[uuid.UUID, dict[str, GraphNode]] = {}
        self.edges: dict[uuid.UUID, dict[tuple[str, str, str], GraphEdge]] = {}

    async def upsert_nodes(self, org: uuid.UUID, nodes: list[GraphNode]) -> GraphUpsertResult:
        store = self.nodes.setdefault(org, {})
        result = GraphUpsertResult()
        for node in nodes:
            existing = store.get(node.identity)
            if existing is None:
                if node.is_deleted:
                    result.soft_deleted += 1
                else:
                    result.created += 1
                store[node.identity] = node
            elif node.is_deleted:
                if existing.is_deleted:
                    result.skipped += 1
                else:
                    result.soft_deleted += 1
                    existing.as_deleted()
            elif existing.unchanged(_doc_from_node(node)):
                result.skipped += 1
            else:
                result.updated += 1
                if existing.is_deleted:
                    existing.reactivate(_doc_from_node(node))
                else:
                    existing.apply_document(_doc_from_node(node))
        return result

    async def upsert_edges(self, org: uuid.UUID, edges: list[GraphEdge]) -> GraphUpsertResult:
        store = self.edges.setdefault(org, {})
        result = GraphUpsertResult()
        for edge in edges:
            key = (edge.source_identity, edge.target_identity, edge.relationship_type.value)
            existing = store.get(key)
            if existing is None:
                if edge.is_deleted:
                    result.soft_deleted += 1
                else:
                    result.created += 1
                store[key] = edge
            elif edge.is_deleted:
                if existing.is_deleted:
                    result.skipped += 1
                else:
                    result.soft_deleted += 1
                    existing.as_deleted()
            elif existing.unchanged(_rel_from_edge(edge)):
                result.skipped += 1
            else:
                result.updated += 1
                if existing.is_deleted:
                    existing.reactivate(_rel_from_edge(edge))
                else:
                    existing.apply_relationship(_rel_from_edge(edge))
        return result

    async def soft_delete_nodes(
        self, org: uuid.UUID, identities: set[str], *, sync_job_id: uuid.UUID | None = None,
    ) -> int:
        store = self.nodes.setdefault(org, {})
        count = 0
        for identity in identities:
            node = store.get(identity)
            if node is not None and not node.is_deleted:
                node.as_deleted()
                count += 1
        return count

    async def soft_delete_edges_for_node(
        self, org: uuid.UUID, identity: str, *, sync_job_id: uuid.UUID | None = None,
    ) -> int:
        store = self.edges.setdefault(org, {})
        count = 0
        for edge in list(store.values()):
            if (
                edge.source_identity == identity or edge.target_identity == identity
            ) and not edge.is_deleted:
                edge.as_deleted()
                count += 1
        return count

    async def soft_delete_missing_edges_for_source(
        self,
        org: uuid.UUID,
        source_identity: str,
        seen_edges: set[tuple[str, str]],
        *,
        sync_job_id: uuid.UUID | None = None,
    ) -> int:
        store = self.edges.setdefault(org, {})
        count = 0
        for edge in list(store.values()):
            if (
                edge.source_identity == source_identity
                and not edge.is_deleted
                and (edge.target_identity, edge.relationship_type.value) not in seen_edges
            ):
                edge.as_deleted()
                count += 1
        return count

    async def soft_delete_edges_for_sources(
        self, org: uuid.UUID, source_identities: set[str], *, sync_job_id: uuid.UUID | None = None,
    ) -> int:
        store = self.edges.setdefault(org, {})
        count = 0
        for edge in list(store.values()):
            if edge.source_identity in source_identities and not edge.is_deleted:
                edge.as_deleted()
                count += 1
        return count

    async def get_node(self, org: uuid.UUID, identity: str) -> GraphNode | None:
        return self.nodes.setdefault(org, {}).get(identity)

    async def get_nodes_by_identities(
        self, org: uuid.UUID, identities: set[str],
    ) -> list[GraphNode]:
        store = self.nodes.setdefault(org, {})
        return [store[i] for i in identities if i in store]

    async def get_edges_by_keys(
        self, org: uuid.UUID, keys: set[tuple[str, str, str]],
    ) -> list[GraphEdge]:
        store = self.edges.setdefault(org, {})
        return [store[k] for k in keys if k in store]

    async def list_active_nodes(
        self,
        org: uuid.UUID,
        *,
        limit: int = 1000,
        offset: int = 0,
        metadata_type: str | None = None,
    ) -> list[GraphNode]:
        nodes = [
            n
            for n in self.nodes.setdefault(org, {}).values()
            if not n.is_deleted and (metadata_type is None or n.type == metadata_type)
        ]
        return nodes[offset : offset + limit]

    async def list_active_edges(
        self, org: uuid.UUID, *, limit: int = 1000, offset: int = 0,
    ) -> list[GraphEdge]:
        edges = [e for e in self.edges.setdefault(org, {}).values() if not e.is_deleted]
        return edges[offset : offset + limit]

    async def count_nodes(self, org: uuid.UUID) -> int:
        return len(self.nodes.setdefault(org, {}))

    async def count_edges(self, org: uuid.UUID) -> int:
        return len(self.edges.setdefault(org, {}))


def _doc_from_node(node: GraphNode) -> CanonicalDocument:
    return CanonicalDocument(
        id=uuid.uuid4(),
        organization_id=node.organization_id,
        identity=node.identity,
        type=node.type,
        api_name=node.api_name,
        developer_name="",
        namespace=node.namespace,
        version=node.document_version,
        previous_version=max(node.document_version - 1, 0),
        fingerprint=node.document_fingerprint,
        status=MetadataStatus.DELETED if node.is_deleted else MetadataStatus.ACTIVE,
        created_at=node.created_at,
        updated_at=node.updated_at,
        first_seen_at=node.created_at,
        last_seen_at=node.updated_at,
        deleted_at=node.deleted_at,
    )


def _rel_from_edge(edge: GraphEdge) -> CanonicalRelationship:
    rel = CanonicalRelationship.create(
        organization_id=edge.organization_id,
        source_identity=edge.source_identity,
        source_api_name=edge.source_api_name,
        source_type=edge.source_type,
        target_identity=edge.target_identity,
        target_api_name=edge.target_api_name,
        target_type=edge.target_type,
        relationship_type=edge.relationship_type,
    )
    if edge.is_deleted:
        rel.soft_delete()
    return rel


class TestBuildGraph:
    async def test_creates_nodes_edges_and_endpoint_nodes(self) -> None:
        repo = FakeGraphRepository()
        builder = DependencyGraphBuilder()
        docs = [
            _document("obj-Account", "object", "Account"),
            _document("fld-Account.Name", "field", "Account.Name"),
            _document("flw-Process", "flow", "Process"),
            _document("ps-Admin", "permission_set", "Admin"),
        ]
        rels = [
            _relationship(
                "obj-Account",
                "Account",
                "object",
                "fld-Account.Name",
                "Account.Name",
                "field",
                CanonicalRelationshipType.OBJECT_TO_FIELD,
            ),
            _relationship(
                "flw-Process",
                "Process",
                "flow",
                "invac-Invoke",
                "Invoke",
                "invocable_action",
                CanonicalRelationshipType.FLOW_TO_INVOCABLE_ACTION,
            ),
            _relationship(
                "prf-Standard",
                "Standard",
                "profile",
                "ps-Admin",
                "Admin",
                "permission_set",
                CanonicalRelationshipType.PROFILE_TO_PERMISSION_SET,
            ),
        ]
        result = await builder.build(ORG_ID, docs, rels, repo, sync_job_id=JOB_ID)
        assert result.nodes.created == 4 + 2
        assert result.endpoint_nodes_created == 2
        assert result.edges.created == 3
        profile = await repo.get_node(ORG_ID, "prf-Standard")
        assert profile is not None
        assert profile.type == "profile"
        assert profile.document_version == 0
        invac = await repo.get_node(ORG_ID, "invac-Invoke")
        assert invac is not None
        assert invac.type == "invocable_action"
        assert result.stale_edges_deleted == 0

    async def test_second_build_is_idempotent(self) -> None:
        repo = FakeGraphRepository()
        builder = DependencyGraphBuilder()
        docs = [_document("obj-Account", "object", "Account")]
        rels = [
            _relationship(
                "obj-Account",
                "Account",
                "object",
                "fld-Account.Name",
                "Account.Name",
                "field",
                CanonicalRelationshipType.OBJECT_TO_FIELD,
            ),
        ]
        first = await builder.build(ORG_ID, docs, rels, repo)
        assert first.nodes.created == 2
        assert first.edges.created == 1
        second = await builder.build(ORG_ID, docs, rels, repo)
        assert second.nodes.created == 0
        assert second.nodes.skipped == 2
        assert second.edges.created == 0
        assert second.edges.skipped == 1
        assert second.stale_edges_deleted == 0

    async def test_duplicate_inputs_are_deduplicated(self) -> None:
        repo = FakeGraphRepository()
        builder = DependencyGraphBuilder()
        docs = [
            _document("obj-Account", "object", "Account"),
            _document("obj-Account", "object", "Account"),
        ]
        rels = [
            _relationship(
                "obj-Account",
                "Account",
                "object",
                "fld-Account.Name",
                "Account.Name",
                "field",
                CanonicalRelationshipType.OBJECT_TO_FIELD,
            ),
            _relationship(
                "obj-Account",
                "Account",
                "object",
                "fld-Account.Name",
                "Account.Name",
                "field",
                CanonicalRelationshipType.OBJECT_TO_FIELD,
            ),
        ]
        result = await builder.build(ORG_ID, docs, rels, repo)
        assert result.nodes.created == 2
        assert result.edges.created == 1
        assert await repo.count_nodes(ORG_ID) == 2
        assert await repo.count_edges(ORG_ID) == 1

    async def test_document_update_updates_node_in_place(self) -> None:
        repo = FakeGraphRepository()
        builder = DependencyGraphBuilder()
        first = await builder.build(
            ORG_ID,
            [_document("obj-Account", "object", "Account")],
            [],
            repo,
        )
        assert first.nodes.created == 1
        second = await builder.build(
            ORG_ID,
            [_document("obj-Account", "object", "Account", version=2, fingerprint="fp-2")],
            [],
            repo,
        )
        assert second.nodes.created == 0
        assert second.nodes.updated == 1
        node = await repo.get_node(ORG_ID, "obj-Account")
        assert node.document_version == 2
        assert node.document_fingerprint == "fp-2"
        assert node.version == 1

    async def test_deleted_document_deletes_node_and_both_directions(self) -> None:
        repo = FakeGraphRepository()
        builder = DependencyGraphBuilder()
        docs = [
            _document("obj-Account", "object", "Account"),
            _document("fld-Account.Name", "field", "Account.Name"),
        ]
        rels = [
            _relationship(
                "obj-Account",
                "Account",
                "object",
                "fld-Account.Name",
                "Account.Name",
                "field",
                CanonicalRelationshipType.OBJECT_TO_FIELD,
            ),
        ]
        await builder.build(ORG_ID, docs, rels, repo)
        deleted_docs = [
            _document("obj-Account", "object", "Account", deleted=True),
            _document("fld-Account.Name", "field", "Account.Name"),
        ]
        result = await builder.build(ORG_ID, deleted_docs, [], repo)
        assert result.nodes.soft_deleted == 1
        assert result.node_edge_deletions == 1
        node = await repo.get_node(ORG_ID, "obj-Account")
        assert node.is_deleted
        edges = await repo.list_active_edges(ORG_ID)
        assert edges == []

    async def test_removed_relationship_soft_deletes_stale_edge(self) -> None:
        repo = FakeGraphRepository()
        builder = DependencyGraphBuilder()
        docs = [
            _document("obj-Account", "object", "Account"),
            _document("fld-Account.Name", "field", "Account.Name"),
            _document("fld-Account.OwnerId", "field", "Account.OwnerId"),
        ]
        rels = [
            _relationship(
                "obj-Account",
                "Account",
                "object",
                "fld-Account.Name",
                "Account.Name",
                "field",
                CanonicalRelationshipType.OBJECT_TO_FIELD,
            ),
            _relationship(
                "obj-Account",
                "Account",
                "object",
                "fld-Account.OwnerId",
                "Account.OwnerId",
                "field",
                CanonicalRelationshipType.OBJECT_TO_FIELD,
            ),
        ]
        await builder.build(ORG_ID, docs, rels, repo)
        remaining = [
            _relationship(
                "obj-Account",
                "Account",
                "object",
                "fld-Account.Name",
                "Account.Name",
                "field",
                CanonicalRelationshipType.OBJECT_TO_FIELD,
            ),
        ]
        result = await builder.build(ORG_ID, docs, remaining, repo)
        assert result.stale_edges_deleted == 1
        edges = await repo.list_active_edges(ORG_ID)
        assert len(edges) == 1
        assert edges[0].target_identity == "fld-Account.Name"

    async def test_source_with_all_edges_removed_is_cleaned_up(self) -> None:
        repo = FakeGraphRepository()
        builder = DependencyGraphBuilder()
        docs = [
            _document("obj-Account", "object", "Account"),
            _document("fld-Account.Name", "field", "Account.Name"),
        ]
        rels = [
            _relationship(
                "obj-Account",
                "Account",
                "object",
                "fld-Account.Name",
                "Account.Name",
                "field",
                CanonicalRelationshipType.OBJECT_TO_FIELD,
            ),
        ]
        await builder.build(ORG_ID, docs, rels, repo)
        result = await builder.build(ORG_ID, docs, [], repo)
        assert result.stale_edges_deleted == 1
        assert await repo.list_active_edges(ORG_ID) == []

    async def test_deleted_relationship_reactivation_bumps_edge_version(self) -> None:
        repo = FakeGraphRepository()
        builder = DependencyGraphBuilder()
        docs = [_document("obj-Account", "object", "Account")]
        rel = _relationship(
            "obj-Account",
            "Account",
            "object",
            "fld-Account.Name",
            "Account.Name",
            "field",
            CanonicalRelationshipType.OBJECT_TO_FIELD,
        )
        await builder.build(ORG_ID, docs, [rel], repo)
        edges = await repo.list_active_edges(ORG_ID)
        assert edges[0].version == 1
        await builder.build(ORG_ID, docs, [], repo)
        assert await repo.list_active_edges(ORG_ID) == []
        result = await builder.build(ORG_ID, docs, [rel], repo)
        assert result.edges.updated == 1
        edges = await repo.list_active_edges(ORG_ID)
        assert edges[0].version == 2
        assert edges[0].previous_version == 1

    async def test_tenant_isolation(self) -> None:
        repo = FakeGraphRepository()
        builder = DependencyGraphBuilder()
        docs = [_document("obj-Account", "object", "Account")]
        rels = [
            _relationship(
                "obj-Account",
                "Account",
                "object",
                "fld-Account.Name",
                "Account.Name",
                "field",
                CanonicalRelationshipType.OBJECT_TO_FIELD,
            ),
        ]
        await builder.build(ORG_ID, docs, rels, repo)
        other_docs = [
            CanonicalDocument.create(
                organization_id=OTHER_ORG_ID,
                identity="obj-Contact",
                type="object",
                api_name="Contact",
                developer_name="Contact",
                namespace=None,
                version=1,
                previous_version=0,
                fingerprint="other",
            ),
        ]
        await builder.build(OTHER_ORG_ID, other_docs, [], repo)
        assert await repo.count_nodes(ORG_ID) == 2
        assert await repo.count_edges(ORG_ID) == 1
        assert await repo.count_nodes(OTHER_ORG_ID) == 1
        assert await repo.count_edges(OTHER_ORG_ID) == 0

    async def test_unknown_relationship_type_is_never_duplicated(self) -> None:
        repo = FakeGraphRepository()
        builder = DependencyGraphBuilder()
        docs = [
            _document("obj-Account", "object", "Account"),
            _document("obj-Contact", "object", "Contact"),
        ]
        rels = [
            _relationship(
                "obj-Account",
                "Account",
                "object",
                "obj-Contact",
                "Contact",
                "object",
                CanonicalRelationshipType.FIELD_TO_LOOKUP_TARGET,
            ),
            _relationship(
                "obj-Account",
                "Account",
                "object",
                "obj-Contact",
                "Contact",
                "object",
                CanonicalRelationshipType.FIELD_TO_LOOKUP_TARGET,
            ),
        ]
        result = await builder.build(ORG_ID, docs, rels, repo)
        assert result.edges.created == 1
