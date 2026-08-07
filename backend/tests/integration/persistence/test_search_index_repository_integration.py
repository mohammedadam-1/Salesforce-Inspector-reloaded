"""Integration tests for the search index store.

Phase 7 — Search Index: persisted searchable documents (one per graph
node identity per tenant), derived from canonical documents and the
dependency graph, tenant-scoped, versioned, idempotent, soft-delete
aware, ranked, and safe under concurrent workers.

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

from sfir_backend.application.pipeline.search.search_index_builder import (
    SearchIndexBuilder,
)
from sfir_backend.config.settings import Settings
from sfir_backend.domain.entities.canonical_document import CanonicalDocument
from sfir_backend.domain.entities.canonical_relationship import (
    CanonicalRelationshipType,
)
from sfir_backend.domain.entities.graph_edge import GraphEdge
from sfir_backend.domain.entities.graph_node import GraphNode
from sfir_backend.domain.entities.search_document import SearchDocument
from sfir_backend.infrastructure.persistence.models.organization import (
    OrganizationModel,
)
from sfir_backend.infrastructure.persistence.models.user import UserModel
from sfir_backend.infrastructure.persistence.repositories.search_index_repo import (
    SQLAlchemySearchIndexRepository,
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
    label: str | None = None,
    description: str | None = None,
    namespace: str | None = None,
) -> CanonicalDocument:
    doc = CanonicalDocument.create(
        organization_id=org_id,
        identity=identity,
        type=type_name,
        api_name=api_name,
        developer_name=api_name,
        namespace=namespace,
        version=version,
        previous_version=version - 1,
        fingerprint=fingerprint,
    )
    payload = {}
    if label:
        payload["label"] = label
    if description:
        payload["description"] = description
    if payload:
        doc.payload = payload
    return doc


def _node(
    org_id: uuid.UUID,
    identity: str,
    type_name: str,
    api_name: str,
    *,
    document_version: int = 1,
    namespace: str | None = None,
) -> GraphNode:
    from datetime import UTC, datetime

    return GraphNode(
        id=uuid.uuid4(),
        organization_id=org_id,
        identity=identity,
        type=type_name,
        api_name=api_name,
        namespace=namespace,
        document_version=document_version,
        document_fingerprint="fp",
        version=1,
        previous_version=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _edge(
    org_id: uuid.UUID,
    source_identity: str,
    source_api_name: str,
    source_type: str,
    target_identity: str,
    target_api_name: str,
    target_type: str,
    rel_type: CanonicalRelationshipType,
) -> GraphEdge:
    from datetime import UTC, datetime

    return GraphEdge(
        id=uuid.uuid4(),
        organization_id=org_id,
        source_identity=source_identity,
        source_api_name=source_api_name,
        source_type=source_type,
        target_identity=target_identity,
        target_api_name=target_api_name,
        target_type=target_type,
        relationship_type=rel_type,
        version=1,
        previous_version=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
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
            email=f"search-{uuid.uuid4().hex[:8]}@test.local",
            password_hash="x",
            display_name="Search Test User",
        ))
        session.add(OrganizationModel(
            id=org_a,
            name="Search Store Test Org A",
            slug=f"search-a-{uuid.uuid4().hex[:8]}",
            description="Search store test org A",
            owner_id=user_id,
        ))
        session.add(OrganizationModel(
            id=org_b,
            name="Search Store Test Org B",
            slug=f"search-b-{uuid.uuid4().hex[:8]}",
            description="Search store test org B",
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
async def repo(db: dict[str, Any]) -> AsyncIterator[SQLAlchemySearchIndexRepository]:
    async with db["session_factory"]() as session:
        yield SQLAlchemySearchIndexRepository(session)


class TestUpsert:
    async def test_create_and_idempotent_skip(
        self, db: dict[str, Any], repo: SQLAlchemySearchIndexRepository,
    ) -> None:
        org_id = db["org_a"]
        doc = SearchDocument.from_graph_node(
            _node(org_id, "obj-Account", "object", "Account"),
        )

        first = await repo.upsert_batch(org_id, [doc])
        second = await repo.upsert_batch(org_id, [doc])

        assert first.created == 1
        assert second.created == 0
        assert second.skipped == 1
        assert await repo.count_by_organization(org_id) == 1

    async def test_content_update_updates_in_place_without_version_bump(
        self, db: dict[str, Any], repo: SQLAlchemySearchIndexRepository,
    ) -> None:
        org_id = db["org_a"]
        node = _node(org_id, "obj-Account", "object", "Account")
        doc = SearchDocument.from_graph_node(node)
        doc.enrich_from_document(
            _document(org_id, "obj-Account", "object", "Account", label="Accounts"),
        )
        await repo.upsert_batch(org_id, [doc])

        updated = SearchDocument.from_graph_node(
            _node(org_id, "obj-Account", "object", "Account", document_version=2),
        )
        updated.enrich_from_document(
            _document(
                org_id, "obj-Account", "object", "Account",
                version=2, fingerprint="fp-2", label="Account Objects",
            ),
        )
        result = await repo.upsert_batch(org_id, [updated])

        assert result.updated == 1
        stored = await repo.get_by_identity(org_id, "obj-Account")
        assert stored is not None
        assert stored.display_name == "Account Objects"
        assert stored.version == 1

    async def test_deleted_document_soft_deletes_and_reactivation_bumps_version(
        self, db: dict[str, Any], repo: SQLAlchemySearchIndexRepository,
    ) -> None:
        org_id = db["org_a"]
        doc = SearchDocument.from_graph_node(
            _node(org_id, "obj-Account", "object", "Account"),
        )
        await repo.upsert_batch(org_id, [doc])

        doc.soft_delete()
        result = await repo.upsert_batch(org_id, [doc])
        assert result.soft_deleted == 1
        stored = await repo.get_by_identity(org_id, "obj-Account")
        assert stored is not None and stored.is_deleted

        reactivated = SearchDocument.from_graph_node(
            _node(org_id, "obj-Account", "object", "Account"),
        )
        result = await repo.upsert_batch(org_id, [reactivated])
        assert result.updated == 1
        stored = await repo.get_by_identity(org_id, "obj-Account")
        assert stored is not None
        assert not stored.is_deleted
        assert stored.version == 2
        assert stored.previous_version == 1

    async def test_duplicate_identities_never_create_duplicate_rows(
        self, db: dict[str, Any], repo: SQLAlchemySearchIndexRepository,
    ) -> None:
        org_id = db["org_a"]
        doc = SearchDocument.from_graph_node(
            _node(org_id, "obj-Account", "object", "Account"),
        )
        await repo.upsert_batch(org_id, [doc])
        await repo.upsert_batch(org_id, [doc])
        assert await repo.count_by_organization(org_id) == 1

    async def test_tenant_isolation(
        self, db: dict[str, Any], repo: SQLAlchemySearchIndexRepository,
    ) -> None:
        doc_a = SearchDocument.from_graph_node(
            _node(db["org_a"], "obj-Account", "object", "Account"),
        )
        doc_b = SearchDocument.from_graph_node(
            _node(db["org_b"], "obj-Contact", "object", "Contact"),
        )
        await repo.upsert_batch(db["org_a"], [doc_a])
        await repo.upsert_batch(db["org_b"], [doc_b])

        assert await repo.count_by_organization(db["org_a"]) == 1
        assert await repo.count_by_organization(db["org_b"]) == 1
        assert await repo.get_by_identity(db["org_b"], "obj-Account") is None


class TestSearch:
    async def _seed(self, repo: SQLAlchemySearchIndexRepository, org_id: uuid.UUID) -> None:
        docs = [
            SearchDocument.from_graph_node(
                _node(org_id, "obj-Account", "object", "Account"),
            ),
            SearchDocument.from_graph_node(
                _node(org_id, "obj-Accounting", "object", "Accounting"),
            ),
            SearchDocument.from_graph_node(
                _node(org_id, "fld-Account.Name", "field", "Account.Name"),
            ),
            SearchDocument.from_graph_node(
                _node(org_id, "flw-Process", "flow", "Process", namespace="ns1"),
            ),
        ]
        docs[0].enrich_from_document(
            _document(
                org_id, "obj-Account", "object", "Account",
                label="Accounts", description="Customer accounts",
            ),
        )
        await repo.upsert_batch(org_id, docs)

    async def test_exact_search_ranks_api_name_first(
        self, db: dict[str, Any], repo: SQLAlchemySearchIndexRepository,
    ) -> None:
        org_id = db["org_a"]
        await self._seed(repo, org_id)
        results = await repo.search(org_id, "Account", mode="exact")
        assert results[0].identity == "obj-Account"
        assert results[0].display_name == "Accounts"
        assert all(
            r.metadata_type == "object"
            for r in results
            if r.identity != "fld-Account.Name"
        )
    async def test_prefix_search(
        self,
        db: dict[str, Any],
        repo: SQLAlchemySearchIndexRepository,
    ) -> None:
        org_id = db["org_a"]
        await self._seed(repo, org_id)
        results = await repo.search(org_id, "acc", mode="prefix")
        assert {r.identity for r in results} == {
            "obj-Account",
            "obj-Accounting",
            "fld-Account.Name",
        }
    async def test_fuzzy_substring_search(
        self,
        db: dict[str, Any],
        repo: SQLAlchemySearchIndexRepository,
    ) -> None:
        org_id = db["org_a"]
        await self._seed(repo, org_id)
        results = await repo.search(org_id, "ount", mode="fuzzy")
        assert {r.identity for r in results} == {
            "obj-Account",
            "obj-Accounting",
            "fld-Account.Name",
        }

    async def test_case_insensitive_matching(
        self, db: dict[str, Any], repo: SQLAlchemySearchIndexRepository,
    ) -> None:
        org_id = db["org_a"]
        await self._seed(repo, org_id)
        assert await repo.search(org_id, "aCcOuNt", mode="exact")
        assert await repo.search(org_id, "ACCOUNT", mode="exact")
    async def test_namespace_filter(
        self,
        db: dict[str, Any],
        repo: SQLAlchemySearchIndexRepository,
    ) -> None:
        org_id = db["org_a"]
        await self._seed(repo, org_id)
        results = await repo.search(org_id, "Process", namespace="ns1")
        assert {r.identity for r in results} == {"flw-Process"}
        assert await repo.search(org_id, "Account", namespace="ns1") == []

    async def test_metadata_type_filter(
        self, db: dict[str, Any], repo: SQLAlchemySearchIndexRepository,
    ) -> None:
        org_id = db["org_a"]
        await self._seed(repo, org_id)
        results = await repo.search(org_id, "Account", metadata_type="field")
        assert {r.identity for r in results} == {"fld-Account.Name"}

    async def test_relationship_type_filter(
        self, db: dict[str, Any], repo: SQLAlchemySearchIndexRepository,
    ) -> None:
        org_id = db["org_a"]
        docs = [
            SearchDocument.from_graph_node(
                _node(org_id, "obj-Account", "object", "Account"),
            ),
            SearchDocument.from_graph_node(
                _node(org_id, "obj-Contact", "object", "Contact"),
            ),
        ]
        docs[0].relationship_types = ["field_to_lookup_target"]
        await repo.upsert_batch(org_id, docs)
        results = await repo.search(
            org_id, "Account", relationship_type="field_to_lookup_target",
        )
        assert {r.identity for r in results} == {"obj-Account"}
        assert await repo.search(
            org_id, "Account", relationship_type="flow_to_object",
        ) == []
    async def test_field_scoping(
        self,
        db: dict[str, Any],
        repo: SQLAlchemySearchIndexRepository,
    ) -> None:
        org_id = db["org_a"]
        await self._seed(repo, org_id)
        by_api = await repo.search(org_id, "Process", fields={"api_name"})
        assert {r.identity for r in by_api} == {"flw-Process"}
        by_display = await repo.search(org_id, "Accounts", fields={"display_name"})
        assert {r.identity for r in by_display} == {"obj-Account"}
        by_content = await repo.search(org_id, "Customer accounts", fields={"content"})
        assert {r.identity for r in by_content} == {"obj-Account"}

    async def test_reference_count_breaks_rank_ties(
        self, db: dict[str, Any], repo: SQLAlchemySearchIndexRepository,
    ) -> None:
        org_id = db["org_a"]
        account = SearchDocument.from_graph_node(
            _node(org_id, "obj-Account", "object", "Account"),
        )
        accounting = SearchDocument.from_graph_node(
            _node(org_id, "obj-Accounting", "object", "Accounting"),
        )
        account.reference_count = 5
        accounting.reference_count = 1
        await repo.upsert_batch(org_id, [account, accounting])
        results = await repo.search(org_id, "account", mode="fuzzy")
        assert [r.identity for r in results] == ["obj-Account", "obj-Accounting"]
    async def test_deleted_rows_are_excluded(
        self,
        db: dict[str, Any],
        repo: SQLAlchemySearchIndexRepository,
    ) -> None:
        org_id = db["org_a"]
        doc = SearchDocument.from_graph_node(
            _node(org_id, "obj-Account", "object", "Account"),
        )
        await repo.upsert_batch(org_id, [doc])
        await repo.upsert_batch(org_id, [doc.soft_delete() or doc])
        assert await repo.search(org_id, "Account") == []
    async def test_limit_and_offset(
        self,
        db: dict[str, Any],
        repo: SQLAlchemySearchIndexRepository,
    ) -> None:
        org_id = db["org_a"]
        docs = [
            SearchDocument.from_graph_node(
                _node(org_id, f"obj-O{i}", "object", f"O{i}"),
            )
            for i in range(10)
        ]
        await repo.upsert_batch(org_id, docs)
        first_page = await repo.search(org_id, "o", limit=4, offset=0)
        second_page = await repo.search(org_id, "o", limit=4, offset=4)
        assert len(first_page) == 4
        assert len(second_page) == 4
        assert first_page[0].identity != second_page[0].identity
    async def test_empty_query_returns_nothing(
        self,
        db: dict[str, Any],
        repo: SQLAlchemySearchIndexRepository,
    ) -> None:
        org_id = db["org_a"]
        await self._seed(repo, org_id)
        assert await repo.search(org_id, "   ") == []


class TestCleanup:
    async def test_soft_delete_by_identities(
        self,
        db: dict[str, Any],
        repo: SQLAlchemySearchIndexRepository,
    ) -> None:
        org_id = db["org_a"]
        docs = [
            SearchDocument.from_graph_node(
                _node(org_id, f"obj-O{i}", "object", f"O{i}"),
            )
            for i in range(3)
        ]
        await repo.upsert_batch(org_id, docs)
        deleted = await repo.soft_delete_by_identities(org_id, {"obj-O0", "obj-O2"})
        assert deleted == 2
        assert {d.identity for d in await repo.list_active(org_id)} == {"obj-O1"}
        assert await repo.count_by_organization(org_id) == 3


class TestConcurrency:
    async def test_concurrent_upserts_never_duplicate(
        self, db: dict[str, Any], repo: SQLAlchemySearchIndexRepository,
    ) -> None:
        org_id = db["org_a"]

        async def worker(index: int) -> None:
            async with db["session_factory"]() as session:
                worker_repo = SQLAlchemySearchIndexRepository(session)
                docs = [
                    SearchDocument.from_graph_node(
                        _node(org_id, f"obj-C{index}-{i}", "object", f"C{index}{i}"),
                    )
                    for i in range(5)
                ]
                await worker_repo.upsert_batch(org_id, docs)

        await asyncio.gather(*(worker(i) for i in range(4)))

        assert await repo.count_by_organization(org_id) == 20

    async def test_concurrent_identical_upserts_skip(
        self, db: dict[str, Any], repo: SQLAlchemySearchIndexRepository,
    ) -> None:
        org_id = db["org_a"]
        doc = SearchDocument.from_graph_node(
            _node(org_id, "obj-Account", "object", "Account"),
        )

        async def worker() -> None:
            async with db["session_factory"]() as session:
                worker_repo = SQLAlchemySearchIndexRepository(session)
                await worker_repo.upsert_batch(org_id, [doc])

        await asyncio.gather(*(worker() for _ in range(3)))

        assert await repo.count_by_organization(org_id) == 1


class TestLargeIndex:
    async def test_bulk_upsert_and_paginated_listing(
        self, db: dict[str, Any], repo: SQLAlchemySearchIndexRepository,
    ) -> None:
        org_id = db["org_a"]
        docs = [
            SearchDocument.from_graph_node(
                _node(org_id, f"obj-O{i}", "object", f"O{i}"),
            )
            for i in range(200)
        ]
        first = await repo.upsert_batch(org_id, docs)
        second = await repo.upsert_batch(org_id, docs)
        assert first.created == 200
        assert second.skipped == 200

        page = await repo.list_active(org_id, limit=50, offset=0)
        assert len(page) == 50
        assert all(not d.is_deleted for d in page)
        assert len(await repo.list_active(org_id, limit=50, offset=150)) == 50


class TestBuilderEndToEnd:
    async def test_full_build_then_incremental_rebuild(
        self, db: dict[str, Any], repo: SQLAlchemySearchIndexRepository,
    ) -> None:
        org_id = db["org_a"]
        builder = SearchIndexBuilder()
        docs = [
            _document(org_id, "obj-Account", "object", "Account", label="Accounts"),
            _document(org_id, "fld-Account.Name", "field", "Account.Name"),
            _document(org_id, "trg-AccountTrigger", "trigger", "AccountTrigger"),
        ]
        nodes = [
            _node(org_id, "obj-Account", "object", "Account"),
            _node(org_id, "fld-Account.Name", "field", "Account.Name"),
            _node(org_id, "trg-AccountTrigger", "trigger", "AccountTrigger"),
        ]
        edges = [
            _edge(
                org_id, "obj-Account", "Account", "object",
                "fld-Account.Name", "Account.Name", "field",
                CanonicalRelationshipType.OBJECT_TO_FIELD,
            ),
            _edge(
                org_id, "trg-AccountTrigger", "AccountTrigger", "trigger",
                "obj-Account", "Account", "object",
                CanonicalRelationshipType.TRIGGER_TO_OBJECT,
            ),
        ]

        first = await builder.build(org_id, docs, nodes, edges, repo)
        assert first.upsert.created == 3
        account = await repo.get_by_identity(org_id, "obj-Account")
        assert account is not None
        assert account.display_name == "Accounts"
        assert account.reference_count == 1
        assert account.child_identities == ["fld-Account.Name"]
        assert "trigger_to_object" in account.relationship_types
        field = await repo.get_by_identity(org_id, "fld-Account.Name")
        assert field is not None
        assert field.parent_identities == ["obj-Account"]
        assert field.object_api_name == "Account"

        second = await builder.build(org_id, docs, nodes, edges, repo)
        assert second.upsert.created == 0
        assert second.upsert.skipped == 3
        assert second.stale_deleted == 0

    async def test_removed_node_is_soft_deleted_as_stale(
        self, db: dict[str, Any], repo: SQLAlchemySearchIndexRepository,
    ) -> None:
        org_id = db["org_a"]
        builder = SearchIndexBuilder()
        docs = [
            _document(org_id, "obj-Account", "object", "Account"),
            _document(org_id, "obj-Contact", "object", "Contact"),
        ]
        nodes = [
            _node(org_id, "obj-Account", "object", "Account"),
            _node(org_id, "obj-Contact", "object", "Contact"),
        ]
        await builder.build(org_id, docs, nodes, [], repo)

        result = await builder.build(
            org_id,
            [_document(org_id, "obj-Account", "object", "Account")],
            [_node(org_id, "obj-Account", "object", "Account")],
            [],
            repo,
        )

        assert result.stale_deleted == 1
        assert {d.identity for d in await repo.list_active(org_id)} == {"obj-Account"}
        stale = await repo.get_by_identity(org_id, "obj-Contact")
        assert stale is not None and stale.is_deleted

    async def test_deleted_document_mirrors_into_search_index(
        self, db: dict[str, Any], repo: SQLAlchemySearchIndexRepository,
    ) -> None:
        org_id = db["org_a"]
        builder = SearchIndexBuilder()
        doc = _document(org_id, "obj-Account", "object", "Account")
        await builder.build(
            org_id,
            [doc],
            [_node(org_id, "obj-Account", "object", "Account")],
            [],
            repo,
        )

        deleted = _document(org_id, "obj-Account", "object", "Account")
        deleted.soft_delete()
        deleted_node = _node(org_id, "obj-Account", "object", "Account")
        deleted_node.deleted_at = deleted.deleted_at
        result = await builder.build(org_id, [deleted], [deleted_node], [], repo)

        assert result.upsert.soft_deleted == 1
        stored = await repo.get_by_identity(org_id, "obj-Account")
        assert stored is not None and stored.is_deleted
    async def test_reactivation_bumps_version(
        self,
        db: dict[str, Any],
        repo: SQLAlchemySearchIndexRepository,
    ) -> None:
        org_id = db["org_a"]
        builder = SearchIndexBuilder()
        doc = _document(org_id, "obj-Account", "object", "Account")
        await builder.build(
            org_id,
            [doc],
            [_node(org_id, "obj-Account", "object", "Account")],
            [],
            repo,
        )

        deleted = _document(org_id, "obj-Account", "object", "Account")
        deleted.soft_delete()
        deleted_node = _node(org_id, "obj-Account", "object", "Account")
        deleted_node.deleted_at = deleted.deleted_at
        await builder.build(org_id, [deleted], [deleted_node], [], repo)

        reactivated = _document(
            org_id, "obj-Account", "object", "Account", version=3, fingerprint="fp-3",
        )
        result = await builder.build(
            org_id,
            [reactivated],
            [_node(org_id, "obj-Account", "object", "Account", document_version=3)],
            [],
            repo,
        )

        assert result.upsert.updated == 1
        stored = await repo.get_by_identity(org_id, "obj-Account")
        assert stored is not None
        assert not stored.is_deleted
        assert stored.version == 2
        assert stored.previous_version == 1

    async def test_tenant_isolation_across_full_builds(
        self, db: dict[str, Any], repo: SQLAlchemySearchIndexRepository,
    ) -> None:
        builder = SearchIndexBuilder()
        docs_a = [_document(db["org_a"], "obj-Account", "object", "Account")]
        nodes_a = [_node(db["org_a"], "obj-Account", "object", "Account")]
        docs_b = [_document(db["org_b"], "obj-Contact", "object", "Contact")]
        nodes_b = [_node(db["org_b"], "obj-Contact", "object", "Contact")]

        await builder.build(db["org_a"], docs_a, nodes_a, [], repo)
        await builder.build(db["org_b"], docs_b, nodes_b, [], repo)

        assert await repo.count_by_organization(db["org_a"]) == 1
        assert await repo.count_by_organization(db["org_b"]) == 1
        assert await repo.get_by_identity(db["org_a"], "obj-Contact") is None
        assert (await repo.search(db["org_a"], "Contact")) == []
        assert (await repo.search(db["org_b"], "Contact")) != []
    async def test_large_org_index_build(
        self,
        db: dict[str, Any],
        repo: SQLAlchemySearchIndexRepository,
    ) -> None:
        org_id = db["org_a"]
        builder = SearchIndexBuilder()
        docs = [
            _document(org_id, f"obj-O{i}", "object", f"O{i}")
            for i in range(300)
        ]
        nodes = [_node(org_id, f"obj-O{i}", "object", f"O{i}") for i in range(300)]
        edges = [
            _edge(
                org_id, f"obj-O{i}", f"O{i}", "object",
                f"obj-O{(i + 1) % 300}", f"O{(i + 1) % 300}", "object",
                CanonicalRelationshipType.FIELD_TO_LOOKUP_TARGET,
            )
            for i in range(300)
        ]

        first = await builder.build(org_id, docs, nodes, edges, repo)
        assert first.upsert.created == 300
        second = await builder.build(org_id, docs, nodes, edges, repo)
        assert second.upsert.skipped == 300

        results = await repo.search(org_id, "O7", mode="prefix")
        assert any(r.api_name == "O7" for r in results)
