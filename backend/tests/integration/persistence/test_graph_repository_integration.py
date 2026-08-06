"""Integration tests for the dependency graph store.

Phase 6 — Dependency Graph: persisted graph nodes (one per canonical
document identity) and graph edges (one per canonical relationship),
tenant-scoped, versioned, idempotent, soft-delete aware, and safe under
concurrent workers.

These tests run against a real PostgreSQL test database. If the test
database is unreachable (e.g. local dev without Postgres running), the
tests skip gracefully with a clear message.

Marked with the ``integration`` marker (see pyproject.toml).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from sfir_backend.application.pipeline.graph.dependency_graph_builder import (
    DependencyGraphBuilder,
)
from sfir_backend.config.settings import Settings
from sfir_backend.domain.entities.canonical_document import CanonicalDocument
from sfir_backend.domain.entities.canonical_relationship import (
    CanonicalRelationship,
    CanonicalRelationshipType,
)
from sfir_backend.domain.entities.graph_edge import GraphEdge
from sfir_backend.domain.entities.graph_node import GraphNode
from sfir_backend.infrastructure.persistence.models.organization import (
    OrganizationModel,
)
from sfir_backend.infrastructure.persistence.models.user import UserModel
from sfir_backend.infrastructure.persistence.repositories.canonical_relationship_repo import (
    SQLAlchemyCanonicalRelationshipRepository,
)
from sfir_backend.infrastructure.persistence.repositories.canonical_repo import (
    SQLAlchemyCanonicalDocumentRepository,
)
from sfir_backend.infrastructure.persistence.repositories.graph_repo import (
    SQLAlchemyGraphRepository,
)

pytestmark = pytest.mark.integration


def _document(
    org_id: uuid.UUID,
    identity: str,
    type_name: str,
    api_name: str,
    *,
    version: int = 1,
    fingerprint: str = "fp",
) -> CanonicalDocument:
    return CanonicalDocument.create(
        organization_id=org_id,
        identity=identity,
        type=type_name,
        api_name=api_name,
        developer_name=api_name,
        namespace=None,
        version=version,
        previous_version=version - 1,
        fingerprint=fingerprint,
    )


def _relationship(
    org_id: uuid.UUID,
    source_identity: str,
    source_api_name: str,
    source_type: str,
    target_identity: str,
    target_api_name: str,
    target_type: str,
    rel_type: CanonicalRelationshipType,
) -> CanonicalRelationship:
    return CanonicalRelationship.create(
        organization_id=org_id,
        source_identity=source_identity,
        source_api_name=source_api_name,
        source_type=source_type,
        target_identity=target_identity,
        target_api_name=target_api_name,
        target_type=target_type,
        relationship_type=rel_type,
    )


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """Create the test engine, skipping if the test DB is unreachable.

    Function-scoped so every test runs on its own event loop with fresh
    connections (module-scoped async engines reuse pooled asyncpg
    connections across test loops, which raises "attached to a different
    loop").
    """
    settings = Settings(
        environment="testing",
        database_url="postgresql+asyncpg://sfir:sfir@localhost:5432/sfir_test",
    )
    engine = create_async_engine(
        settings.database_url.get_secret_value(),
        echo=False,
        pool_pre_ping=True,
    )
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - depends on environment
        await engine.dispose()
        pytest.skip(f"Test database unavailable: {exc}")
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db(engine: AsyncEngine, session_factory: Any) -> AsyncIterator[dict[str, Any]]:
    """Create tables, seed two organizations, and clean up."""
    from sfir_backend.infrastructure.database.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    user_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(UserModel(
            id=user_id,
            email=f"graph-{uuid.uuid4().hex[:8]}@test.local",
            password_hash="x",
            display_name="Graph Test User",
        ))
        session.add(OrganizationModel(
            id=org_a,
            name="Graph Store Test Org A",
            slug=f"graph-a-{uuid.uuid4().hex[:8]}",
            description="Graph store test org A",
            owner_id=user_id,
        ))
        session.add(OrganizationModel(
            id=org_b,
            name="Graph Store Test Org B",
            slug=f"graph-b-{uuid.uuid4().hex[:8]}",
            description="Graph store test org B",
            owner_id=user_id,
        ))
        await session.commit()

    yield {
        "org_a": org_a,
        "org_b": org_b,
        "session_factory": session_factory,
    }

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def repo(db: dict[str, Any]) -> AsyncIterator[SQLAlchemyGraphRepository]:
    async with db["session_factory"]() as session:
        yield SQLAlchemyGraphRepository(session)


class TestNodeUpsert:
    async def test_create_and_idempotent_skip(
        self, db: dict[str, Any], repo: SQLAlchemyGraphRepository,
    ) -> None:
        org_id = db["org_a"]
        node = GraphNode.from_document(_document(org_id, "obj-Account", "object", "Account"))

        first = await repo.upsert_nodes(org_id, [node])
        second = await repo.upsert_nodes(org_id, [node])

        assert first.created == 1
        assert second.created == 0
        assert second.skipped == 1
        assert await repo.count_nodes(org_id) == 1

    async def test_updated_document_updates_node_without_version_bump(
        self, db: dict[str, Any], repo: SQLAlchemyGraphRepository,
    ) -> None:
        org_id = db["org_a"]
        node = GraphNode.from_document(_document(org_id, "obj-Account", "object", "Account"))
        await repo.upsert_nodes(org_id, [node])

        updated = GraphNode.from_document(
            _document(org_id, "obj-Account", "object", "Account", version=2, fingerprint="fp-2"),
        )
        result = await repo.upsert_nodes(org_id, [updated])

        assert result.created == 0
        assert result.updated == 1
        stored = await repo.get_node(org_id, "obj-Account")
        assert stored is not None
        assert stored.document_version == 2
        assert stored.document_fingerprint == "fp-2"
        assert stored.version == 1

    async def test_deleted_document_soft_deletes_node_and_reactivation_bumps_version(
        self, db: dict[str, Any], repo: SQLAlchemyGraphRepository,
    ) -> None:
        org_id = db["org_a"]
        doc = _document(org_id, "obj-Account", "object", "Account")
        node = GraphNode.from_document(doc)
        await repo.upsert_nodes(org_id, [node])

        doc.soft_delete()
        deleted_node = GraphNode.from_document(doc)
        result = await repo.upsert_nodes(org_id, [deleted_node])
        assert result.soft_deleted == 1
        stored = await repo.get_node(org_id, "obj-Account")
        assert stored is not None and stored.is_deleted

        reactivated = GraphNode.from_document(
            _document(org_id, "obj-Account", "object", "Account"),
        )
        result = await repo.upsert_nodes(org_id, [reactivated])
        assert result.updated == 1
        stored = await repo.get_node(org_id, "obj-Account")
        assert stored is not None
        assert not stored.is_deleted
        assert stored.version == 2
        assert stored.previous_version == 1

    async def test_tenant_isolation(
        self, db: dict[str, Any], repo: SQLAlchemyGraphRepository,
    ) -> None:
        node_a = GraphNode.from_document(_document(db["org_a"], "obj-Account", "object", "Account"))
        node_b = GraphNode.from_document(_document(db["org_b"], "obj-Contact", "object", "Contact"))
        await repo.upsert_nodes(db["org_a"], [node_a])
        await repo.upsert_nodes(db["org_b"], [node_b])

        assert await repo.count_nodes(db["org_a"]) == 1
        assert await repo.count_nodes(db["org_b"]) == 1
        stored_b = await repo.get_node(db["org_b"], "obj-Account")
        assert stored_b is None


class TestEdgeUpsert:
    async def test_create_and_idempotent_skip(
        self, db: dict[str, Any], repo: SQLAlchemyGraphRepository,
    ) -> None:
        org_id = db["org_a"]
        rel = _relationship(
            org_id, "obj-Account", "Account", "object",
            "fld-Account.Name", "Account.Name", "field",
            CanonicalRelationshipType.OBJECT_TO_FIELD,
        )
        edge = GraphEdge.from_relationship(rel)

        first = await repo.upsert_edges(org_id, [edge])
        second = await repo.upsert_edges(org_id, [edge])

        assert first.created == 1
        assert second.created == 0
        assert second.skipped == 1
        assert await repo.count_edges(org_id) == 1

    async def test_deleted_relationship_soft_deletes_edge_and_reactivation_bumps_version(
        self, db: dict[str, Any], repo: SQLAlchemyGraphRepository,
    ) -> None:
        org_id = db["org_a"]
        rel = _relationship(
            org_id, "obj-Account", "Account", "object",
            "fld-Account.Name", "Account.Name", "field",
            CanonicalRelationshipType.OBJECT_TO_FIELD,
        )
        await repo.upsert_edges(org_id, [GraphEdge.from_relationship(rel)])

        rel.soft_delete()
        result = await repo.upsert_edges(org_id, [GraphEdge.from_relationship(rel)])
        assert result.soft_deleted == 1
        assert await repo.list_active_edges(org_id) == []

        reactivated = _relationship(
            org_id, "obj-Account", "Account", "object",
            "fld-Account.Name", "Account.Name", "field",
            CanonicalRelationshipType.OBJECT_TO_FIELD,
        )
        result = await repo.upsert_edges(org_id, [GraphEdge.from_relationship(reactivated)])
        edges = await repo.list_active_edges(org_id)
        assert len(edges) == 1
        assert edges[0].version == 2
        assert edges[0].previous_version == 1

    async def test_duplicate_edge_keys_are_never_duplicated(
        self, db: dict[str, Any], repo: SQLAlchemyGraphRepository,
    ) -> None:
        org_id = db["org_a"]
        rel = _relationship(
            org_id, "obj-Account", "Account", "object",
            "fld-Account.Name", "Account.Name", "field",
            CanonicalRelationshipType.OBJECT_TO_FIELD,
        )
        await repo.upsert_edges(org_id, [GraphEdge.from_relationship(rel)])
        await repo.upsert_edges(org_id, [GraphEdge.from_relationship(rel)])
        assert await repo.count_edges(org_id) == 1

    async def test_get_edges_by_keys_filters_precisely(
        self, db: dict[str, Any], repo: SQLAlchemyGraphRepository,
    ) -> None:
        org_id = db["org_a"]
        edge = GraphEdge.from_relationship(_relationship(
            org_id, "obj-Account", "Account", "object",
            "fld-Account.Name", "Account.Name", "field",
            CanonicalRelationshipType.OBJECT_TO_FIELD,
        ))
        await repo.upsert_edges(org_id, [edge])

        found = await repo.get_edges_by_keys(
            org_id,
            {("obj-Account", "fld-Account.Name", "object_to_field")},
        )
        assert len(found) == 1
        missing = await repo.get_edges_by_keys(
            org_id,
            {("obj-Account", "fld-Account.Name", "field_to_object")},
        )
        assert missing == []


class TestCleanup:
    async def test_soft_delete_missing_edges_for_source(
        self, db: dict[str, Any], repo: SQLAlchemyGraphRepository,
    ) -> None:
        org_id = db["org_a"]
        edges = [
            GraphEdge.from_relationship(_relationship(
                org_id, "obj-Account", "Account", "object",
                "fld-Account.Name", "Account.Name", "field",
                CanonicalRelationshipType.OBJECT_TO_FIELD,
            )),
            GraphEdge.from_relationship(_relationship(
                org_id, "obj-Account", "Account", "object",
                "fld-Account.OwnerId", "Account.OwnerId", "field",
                CanonicalRelationshipType.OBJECT_TO_FIELD,
            )),
        ]
        await repo.upsert_edges(org_id, edges)

        deleted = await repo.soft_delete_missing_edges_for_source(
            org_id,
            "obj-Account",
            {("fld-Account.Name", "object_to_field")},
        )
        assert deleted == 1
        active = await repo.list_active_edges(org_id)
        assert len(active) == 1
        assert active[0].target_identity == "fld-Account.Name"

    async def test_soft_delete_edges_for_node_removes_both_directions(
        self, db: dict[str, Any], repo: SQLAlchemyGraphRepository,
    ) -> None:
        org_id = db["org_a"]
        outgoing = GraphEdge.from_relationship(_relationship(
            org_id, "obj-Account", "Account", "object",
            "fld-Account.Name", "Account.Name", "field",
            CanonicalRelationshipType.OBJECT_TO_FIELD,
        ))
        incoming = GraphEdge.from_relationship(_relationship(
            org_id, "flw-Process", "Process", "flow",
            "obj-Account", "Account", "object",
            CanonicalRelationshipType.FLOW_TO_OBJECT,
        ))
        await repo.upsert_edges(org_id, [outgoing, incoming])

        deleted = await repo.soft_delete_edges_for_node(org_id, "obj-Account")
        assert deleted == 2
        assert await repo.list_active_edges(org_id) == []


class TestConcurrency:
    async def test_concurrent_upserts_never_duplicate(
        self, db: dict[str, Any], repo: SQLAlchemyGraphRepository,
    ) -> None:
        org_id = db["org_a"]

        async def worker(index: int) -> None:
            async with db["session_factory"]() as session:
                worker_repo = SQLAlchemyGraphRepository(session)
                nodes = [
                    GraphNode.from_document(
                        _document(org_id, f"obj-C{index}-{i}", "object", f"C{index}{i}"),
                    )
                    for i in range(5)
                ]
                await worker_repo.upsert_nodes(org_id, nodes)
                rel = _relationship(
                    org_id, f"obj-C{index}-0", f"C{index}0", "object",
                    f"obj-C{index}-1", f"C{index}1", "object",
                    CanonicalRelationshipType.FIELD_TO_LOOKUP_TARGET,
                )
                await worker_repo.upsert_edges(org_id, [GraphEdge.from_relationship(rel)])

        await asyncio.gather(*(worker(i) for i in range(4)))

        assert await repo.count_nodes(org_id) == 20
        assert await repo.count_edges(org_id) == 4

    async def test_concurrent_identical_upserts_skip(
        self, db: dict[str, Any], repo: SQLAlchemyGraphRepository,
    ) -> None:
        org_id = db["org_a"]
        node = GraphNode.from_document(_document(org_id, "obj-Account", "object", "Account"))

        async def worker() -> None:
            async with db["session_factory"]() as session:
                worker_repo = SQLAlchemyGraphRepository(session)
                await worker_repo.upsert_nodes(org_id, [node])

        await asyncio.gather(*(worker() for _ in range(3)))

        assert await repo.count_nodes(org_id) == 1


class TestLargeGraph:
    async def test_bulk_upsert_handles_large_graphs(
        self, db: dict[str, Any], repo: SQLAlchemyGraphRepository,
    ) -> None:
        org_id = db["org_a"]
        nodes = [
            GraphNode.from_document(_document(org_id, f"obj-O{i}", "object", f"O{i}"))
            for i in range(200)
        ]
        edges = [
            GraphEdge.from_relationship(_relationship(
                org_id, f"obj-O{i}", f"O{i}", "object",
                f"obj-O{(i + 1) % 200}", f"O{(i + 1) % 200}", "object",
                CanonicalRelationshipType.FIELD_TO_LOOKUP_TARGET,
            ))
            for i in range(200)
        ]
        first = await repo.upsert_nodes(org_id, nodes)
        second = await repo.upsert_nodes(org_id, nodes)
        edge_result = await repo.upsert_edges(org_id, edges)

        assert first.created == 200
        assert second.skipped == 200
        assert edge_result.created == 200
        assert await repo.count_nodes(org_id) == 200
        assert await repo.count_edges(org_id) == 200

        active = await repo.list_active_nodes(org_id, limit=50, offset=0, metadata_type="object")
        assert len(active) == 50
        assert all(node.type == "object" and not node.is_deleted for node in active)


class TestBuilderEndToEnd:
    async def _seed_canonical(
        self,
        db: dict[str, Any],
        org_id: uuid.UUID,
        docs: list[CanonicalDocument],
        rels: list[CanonicalRelationship],
    ) -> tuple[SQLAlchemyCanonicalDocumentRepository, SQLAlchemyCanonicalRelationshipRepository]:
        async with db["session_factory"]() as session:
            canonical = SQLAlchemyCanonicalDocumentRepository(session)
            relationship = SQLAlchemyCanonicalRelationshipRepository(session)
            await canonical.upsert_batch(org_id, docs)
            await relationship.upsert_batch(org_id, rels)
            return canonical, relationship

    async def test_full_build_then_incremental_rebuild(
        self, db: dict[str, Any], repo: SQLAlchemyGraphRepository,
    ) -> None:
        org_id = db["org_a"]
        builder = DependencyGraphBuilder()
        docs = [
            _document(org_id, "obj-Account", "object", "Account"),
            _document(org_id, "fld-Account.Name", "field", "Account.Name"),
            _document(org_id, "fld-Account.OwnerId", "field", "Account.OwnerId"),
            _document(org_id, "trg-AccountTrigger", "trigger", "AccountTrigger"),
        ]
        rels = [
            _relationship(
                org_id, "obj-Account", "Account", "object",
                "fld-Account.Name", "Account.Name", "field",
                CanonicalRelationshipType.OBJECT_TO_FIELD,
            ),
            _relationship(
                org_id, "obj-Account", "Account", "object",
                "fld-Account.OwnerId", "Account.OwnerId", "field",
                CanonicalRelationshipType.OBJECT_TO_FIELD,
            ),
            _relationship(
                org_id, "trg-AccountTrigger", "AccountTrigger", "trigger",
                "obj-Account", "Account", "object",
                CanonicalRelationshipType.TRIGGER_TO_OBJECT,
            ),
        ]
        await self._seed_canonical(db, org_id, docs, rels)

        first = await builder.build(org_id, docs, rels, repo)
        assert first.nodes.created == 4
        assert first.edges.created == 3
        assert await repo.count_nodes(org_id) == 4
        assert await repo.count_edges(org_id) == 3

        second = await builder.build(org_id, docs, rels, repo)
        assert second.nodes.skipped == 4
        assert second.edges.skipped == 3
        assert second.stale_edges_deleted == 0
        assert second.node_edge_deletions == 0

        stored = await repo.get_node(org_id, "obj-Account")
        assert stored is not None and not stored.is_deleted
        assert stored.document_version == 1

    async def test_document_deletion_propagates_to_nodes_and_edges(
        self, db: dict[str, Any], repo: SQLAlchemyGraphRepository,
    ) -> None:
        org_id = db["org_a"]
        builder = DependencyGraphBuilder()
        docs = [
            _document(org_id, "obj-Account", "object", "Account"),
            _document(org_id, "fld-Account.Name", "field", "Account.Name"),
        ]
        rels = [
            _relationship(
                org_id, "obj-Account", "Account", "object",
                "fld-Account.Name", "Account.Name", "field",
                CanonicalRelationshipType.OBJECT_TO_FIELD,
            ),
        ]
        await self._seed_canonical(db, org_id, docs, rels)
        await builder.build(org_id, docs, rels, repo)

        deleted = _document(org_id, "obj-Account", "object", "Account")
        deleted.soft_delete()
        result = await builder.build(org_id, [deleted, docs[1]], [], repo)

        assert result.nodes.soft_deleted == 1
        assert result.node_edge_deletions == 1
        node = await repo.get_node(org_id, "obj-Account")
        assert node is not None and node.is_deleted
        assert await repo.list_active_edges(org_id) == []

    async def test_endpoint_nodes_cover_relationship_endpoints_without_documents(
        self, db: dict[str, Any], repo: SQLAlchemyGraphRepository,
    ) -> None:
        org_id = db["org_a"]
        builder = DependencyGraphBuilder()
        docs = [_document(org_id, "flw-Process", "flow", "Process")]
        rels = [
            _relationship(
                org_id, "flw-Process", "Process", "flow",
                "invac-Invoke", "Invoke", "invocable_action",
                CanonicalRelationshipType.FLOW_TO_INVOCABLE_ACTION,
            ),
        ]
        await self._seed_canonical(db, org_id, docs, rels)

        result = await builder.build(org_id, docs, rels, repo)

        assert result.nodes.created == 2
        assert result.endpoint_nodes_created == 1
        endpoint = await repo.get_node(org_id, "invac-Invoke")
        assert endpoint is not None
        assert endpoint.type == "invocable_action"
        assert endpoint.document_version == 0
        assert await repo.count_edges(org_id) == 1

    async def test_tenant_isolation_across_full_builds(
        self, db: dict[str, Any], repo: SQLAlchemyGraphRepository,
    ) -> None:
        builder = DependencyGraphBuilder()
        docs_a = [_document(db["org_a"], "obj-Account", "object", "Account")]
        docs_b = [_document(db["org_b"], "obj-Contact", "object", "Contact")]
        await self._seed_canonical(db, db["org_a"], docs_a, [])
        await self._seed_canonical(db, db["org_b"], docs_b, [])

        await builder.build(db["org_a"], docs_a, [], repo)
        await builder.build(db["org_b"], docs_b, [], repo)

        assert await repo.count_nodes(db["org_a"]) == 1
        assert await repo.count_nodes(db["org_b"]) == 1
        assert await repo.get_node(db["org_a"], "obj-Contact") is None

    async def test_reactivation_of_deleted_node_bumps_graph_version(
        self, db: dict[str, Any], repo: SQLAlchemyGraphRepository,
    ) -> None:
        org_id = db["org_a"]
        builder = DependencyGraphBuilder()
        doc = _document(org_id, "obj-Account", "object", "Account")
        await self._seed_canonical(db, org_id, [doc], [])
        await builder.build(org_id, [doc], [], repo)

        deleted = _document(org_id, "obj-Account", "object", "Account")
        deleted.soft_delete()
        await self._seed_canonical(db, org_id, [deleted], [])
        await builder.build(org_id, [deleted], [], repo)
        assert (await repo.get_node(org_id, "obj-Account")).is_deleted

        reactivated = _document(org_id, "obj-Account", "object", "Account")
        await self._seed_canonical(db, org_id, [reactivated], [])
        result = await builder.build(org_id, [reactivated], [], repo)

        assert result.nodes.updated == 1
        node = await repo.get_node(org_id, "obj-Account")
        assert node is not None
        assert not node.is_deleted
        assert node.version == 2
        assert node.previous_version == 1

    async def test_version_update_marks_node_updated_without_new_graph_version(
        self, db: dict[str, Any], repo: SQLAlchemyGraphRepository,
    ) -> None:
        org_id = db["org_a"]
        builder = DependencyGraphBuilder()
        doc = _document(org_id, "obj-Account", "object", "Account")
        await self._seed_canonical(db, org_id, [doc], [])
        await builder.build(org_id, [doc], [], repo)

        updated = _document(
            org_id, "obj-Account", "object", "Account", version=2, fingerprint="fp-2",
        )
        await self._seed_canonical(db, org_id, [updated], [])
        result = await builder.build(org_id, [updated], [], repo)

        assert result.nodes.updated == 1
        node = await repo.get_node(org_id, "obj-Account")
        assert node is not None
        assert node.document_version == 2
        assert node.version == 1

    async def test_deleted_node_has_no_duplicate_rows_after_repeated_runs(
        self, db: dict[str, Any], repo: SQLAlchemyGraphRepository,
    ) -> None:
        org_id = db["org_a"]
        builder = DependencyGraphBuilder()
        doc = _document(org_id, "obj-Account", "object", "Account")
        await self._seed_canonical(db, org_id, [doc], [])
        await builder.build(org_id, [doc], [], repo)

        deleted = _document(org_id, "obj-Account", "object", "Account")
        deleted.soft_delete()
        await self._seed_canonical(db, org_id, [deleted], [])
        await builder.build(org_id, [deleted], [], repo)
        await builder.build(org_id, [deleted], [], repo)

        assert await repo.count_nodes(org_id) == 1
        node = await repo.get_node(org_id, "obj-Account")
        assert node is not None and node.is_deleted
        assert node.version == 1
