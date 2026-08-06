"""Integration tests for the canonical document repository.

Phase 5 Step 2 — Canonical Metadata Store: current-state rows per stable
identity, upsert-correct under concurrency, versioned, only soft-deleted.

These tests run against a real PostgreSQL test database.  If the test
database is unreachable (e.g. local dev without Postgres running), the
tests skip gracefully with a clear message.

Marked with the ``integration`` marker (see pyproject.toml).
"""

from __future__ import annotations

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

from sfir_backend.config.settings import Settings
from sfir_backend.domain.canonical.base import MetadataStatus
from sfir_backend.domain.entities.canonical_document import CanonicalDocument
from sfir_backend.infrastructure.persistence.models.organization import (
    OrganizationModel,
)
from sfir_backend.infrastructure.persistence.models.user import UserModel
from sfir_backend.infrastructure.persistence.repositories.canonical_repo import (
    SQLAlchemyCanonicalDocumentRepository,
)

pytestmark = pytest.mark.integration

TEST_ORG_NAME = "Canonical Store Test Org"


def _document(
    org_id: uuid.UUID,
    api_name: str,
    *,
    type_name: str = "ApexClass",
    fingerprint: str = "fp1",
    version: int = 1,
    previous_version: int = 0,
    payload: dict | None = None,
) -> CanonicalDocument:
    return CanonicalDocument.create(
        organization_id=org_id,
        identity=f"hash-{type_name}-{api_name}",
        type=type_name,
        api_name=api_name,
        developer_name=api_name,
        namespace=None,
        version=version,
        previous_version=previous_version,
        fingerprint=fingerprint,
        sync_job_id=uuid.uuid4(),
        payload=payload or {"api_name": api_name, "type": type_name},
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
            email=f"canonical-{uuid.uuid4().hex[:8]}@test.local",
            password_hash="x",
            display_name="Canonical Test User",
        ))
        session.add(OrganizationModel(
            id=org_a,
            name=TEST_ORG_NAME,
            slug=f"canonical-a-{uuid.uuid4().hex[:8]}",
            description="Canonical store test org A",
            owner_id=user_id,
        ))
        session.add(OrganizationModel(
            id=org_b,
            name="Canonical Store Test Org B",
            slug=f"canonical-b-{uuid.uuid4().hex[:8]}",
            description="Canonical store test org B",
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
async def repo(db: dict[str, Any]) -> AsyncIterator[SQLAlchemyCanonicalDocumentRepository]:
    async with db["session_factory"]() as session:
        yield SQLAlchemyCanonicalDocumentRepository(session)


class TestUpsertAndRead:
    async def test_create_and_get_by_identity(
        self, db: dict[str, Any], repo: SQLAlchemyCanonicalDocumentRepository,
    ) -> None:
        org_id = db["org_a"]
        doc = _document(org_id, "MyClass")

        result = await repo.upsert_batch(org_id, [doc])

        assert result.created == 1
        assert result.updated == 0
        found = await repo.get_by_identity(org_id, doc.identity)
        assert found is not None
        assert found.api_name == "MyClass"
        assert found.version == 1
        assert found.previous_version == 0
        assert found.fingerprint == "fp1"
        assert found.status == MetadataStatus.ACTIVE
        assert found.payload["api_name"] == "MyClass"

    async def test_duplicate_fingerprint_is_skipped(
        self, db: dict[str, Any], repo: SQLAlchemyCanonicalDocumentRepository,
    ) -> None:
        org_id = db["org_a"]
        doc = _document(org_id, "StableClass")
        await repo.upsert_batch(org_id, [doc])

        result = await repo.upsert_batch(org_id, [doc])

        assert result.created == 0
        assert result.skipped == 1
        found = await repo.get_by_identity(org_id, doc.identity)
        assert found is not None
        assert found.version == 1

    async def test_changed_fingerprint_creates_new_version(
        self, db: dict[str, Any], repo: SQLAlchemyCanonicalDocumentRepository,
    ) -> None:
        org_id = db["org_a"]
        doc = _document(org_id, "ChangingClass", fingerprint="fp-v1")
        await repo.upsert_batch(org_id, [doc])

        updated = _document(
            org_id, "ChangingClass", fingerprint="fp-v2",
            version=2, previous_version=1,
        )
        result = await repo.upsert_batch(org_id, [updated])

        assert result.updated == 1
        found = await repo.get_by_identity(org_id, doc.identity)
        assert found is not None
        assert found.fingerprint == "fp-v2"
        assert found.version == 2
        assert found.previous_version == 1

    async def test_repeated_idempotent_run_is_noop(
        self, db: dict[str, Any], repo: SQLAlchemyCanonicalDocumentRepository,
    ) -> None:
        org_id = db["org_a"]
        docs = [_document(org_id, "IdemA"), _document(org_id, "IdemB", type_name="Flow")]
        await repo.upsert_batch(org_id, docs)

        result = await repo.upsert_batch(org_id, docs)

        assert result.created == 0
        assert result.updated == 0
        assert result.skipped == 2
        assert await repo.count_by_organization(org_id) == 2

    async def test_concurrent_upserts_do_not_duplicate_rows(
        self, db: dict[str, Any],
    ) -> None:
        import asyncio

        org_id = db["org_a"]
        doc = _document(org_id, "ConcurrentClass")
        async with (
            db["session_factory"]() as session_a,
            db["session_factory"]() as session_b,
        ):
            repo_a = SQLAlchemyCanonicalDocumentRepository(session_a)
            repo_b = SQLAlchemyCanonicalDocumentRepository(session_b)
            result_a, result_b = await asyncio.gather(
                repo_a.upsert_batch(org_id, [doc]),
                repo_b.upsert_batch(org_id, [doc]),
            )
            count = await repo_a.count_by_organization(org_id)
        assert (result_a.created + result_b.created) == 1
        assert (result_a.skipped + result_b.skipped) == 1
        assert count == 1


class TestSoftDelete:
    async def test_soft_delete_missing_only_removes_unseen(
        self, db: dict[str, Any], repo: SQLAlchemyCanonicalDocumentRepository,
    ) -> None:
        org_id = db["org_a"]
        kept = _document(org_id, "KeptClass")
        gone = _document(org_id, "GoneClass")
        await repo.upsert_batch(org_id, [kept, gone])

        deleted = await repo.soft_delete_missing(
            org_id, "ApexClass", seen_api_names={"KeptClass"},
        )

        assert deleted == 1
        kept_row = await repo.get_by_identity(org_id, kept.identity)
        gone_row = await repo.get_by_identity(org_id, gone.identity)
        assert kept_row is not None and kept_row.status == MetadataStatus.ACTIVE
        assert gone_row is not None and gone_row.status == MetadataStatus.DELETED
        assert gone_row.deleted_at is not None

    async def test_soft_delete_missing_respects_type_boundary(
        self, db: dict[str, Any], repo: SQLAlchemyCanonicalDocumentRepository,
    ) -> None:
        org_id = db["org_a"]
        flow = _document(org_id, "FlowA", type_name="Flow")
        await repo.upsert_batch(org_id, [flow])

        deleted = await repo.soft_delete_missing(org_id, "ApexClass", seen_api_names=set())

        assert deleted == 0
        row = await repo.get_by_identity(org_id, flow.identity)
        assert row is not None and row.status == MetadataStatus.ACTIVE

    async def test_soft_delete_by_identity_marks_deleted(
        self, db: dict[str, Any], repo: SQLAlchemyCanonicalDocumentRepository,
    ) -> None:
        org_id = db["org_a"]
        doc = _document(org_id, "ByeClass")
        await repo.upsert_batch(org_id, [doc])

        deleted = await repo.soft_delete_by_identity(org_id, doc.identity)

        assert deleted is True
        row = await repo.get_by_identity(org_id, doc.identity)
        assert row is not None and row.status == MetadataStatus.DELETED
        assert row.is_deleted

    async def test_reactivation_preserves_first_seen_timestamps(
        self, db: dict[str, Any], repo: SQLAlchemyCanonicalDocumentRepository,
    ) -> None:
        org_id = db["org_a"]
        doc = _document(org_id, "RisingClass")
        await repo.upsert_batch(org_id, [doc])
        row = await repo.get_by_identity(org_id, doc.identity)
        assert row is not None
        first_seen = row.first_seen_at
        await repo.soft_delete_by_identity(org_id, doc.identity)

        revived = _document(
            org_id, "RisingClass", fingerprint="fp-revived", version=2, previous_version=1,
        )
        result = await repo.upsert_batch(org_id, [revived])

        assert result.updated == 1
        row = await repo.get_by_identity(org_id, doc.identity)
        assert row is not None
        assert row.status == MetadataStatus.ACTIVE
        assert row.deleted_at is None
        assert row.first_seen_at == first_seen
        assert row.version == 2


class TestListingAndIsolation:
    async def test_list_latest_and_by_type(
        self, db: dict[str, Any], repo: SQLAlchemyCanonicalDocumentRepository,
    ) -> None:
        org_id = db["org_a"]
        await repo.upsert_batch(org_id, [
            _document(org_id, "ListA"),
            _document(org_id, "ListB", type_name="Flow"),
            _document(org_id, "ListC", type_name="Flow"),
        ])

        all_docs = await repo.list_latest(org_id, limit=100)
        flows = await repo.list_latest_by_type(org_id, "Flow")

        assert len(all_docs) == 3
        assert [d.api_name for d in flows] == ["ListB", "ListC"]
        assert await repo.count_by_organization(org_id) == 3

    async def test_organizations_are_isolated(
        self, db: dict[str, Any], repo: SQLAlchemyCanonicalDocumentRepository,
    ) -> None:
        org_a = db["org_a"]
        org_b = db["org_b"]
        doc_b = _document(org_b, "PrivateClass")
        await repo.upsert_batch(org_a, [_document(org_a, "PublicClass")])
        await repo.upsert_batch(org_b, [doc_b])

        found_b = await repo.get_by_identity(org_b, doc_b.identity)
        assert found_b is not None
        in_a = await repo.get_by_identity(org_a, doc_b.identity)
        assert in_a is None
        assert len(await repo.list_latest(org_b, limit=100)) == 1
        assert await repo.count_by_organization(org_b) == 1

    async def test_soft_delete_missing_is_tenant_scoped(
        self, db: dict[str, Any], repo: SQLAlchemyCanonicalDocumentRepository,
    ) -> None:
        org_a = db["org_a"]
        org_b = db["org_b"]
        doc_b = _document(org_b, "OtherOrgClass")
        await repo.upsert_batch(org_b, [doc_b])

        deleted = await repo.soft_delete_missing(org_a, "ApexClass", seen_api_names=set())

        assert deleted == 0
        row = await repo.get_by_identity(org_b, doc_b.identity)
        assert row is not None and row.status == MetadataStatus.ACTIVE
