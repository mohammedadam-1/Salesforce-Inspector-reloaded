"""Integration tests for the canonical relationship repository.

Phase 5 Step 3 — Canonical Relationship Store: typed, directional,
versioned, tenant-scoped, idempotent relationship rows.

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

from sfir_backend.application.pipeline.normalizer.identity_service import (
    IdentityService,
)
from sfir_backend.application.pipeline.resolver.canonical_relationship_resolver import (
    CanonicalRelationshipResolver,
)
from sfir_backend.config.settings import Settings
from sfir_backend.domain.canonical.base import FieldType
from sfir_backend.domain.canonical.core import MetadataField
from sfir_backend.domain.entities.canonical_relationship import (
    CanonicalRelationship,
    CanonicalRelationshipType,
)
from sfir_backend.infrastructure.persistence.models.organization import (
    OrganizationModel,
)
from sfir_backend.infrastructure.persistence.models.user import UserModel
from sfir_backend.infrastructure.persistence.repositories.canonical_relationship_repo import (
    SQLAlchemyCanonicalRelationshipRepository,
)

pytestmark = pytest.mark.integration


def _relationship(
    org_id: uuid.UUID,
    source_api: str,
    target_api: str,
    rel_type: CanonicalRelationshipType,
    *,
    source_type: str = "object",
    target_type: str = "field",
    deleted: bool = False,
    sync_job_id: uuid.UUID | None = None,
) -> CanonicalRelationship:
    rel = CanonicalRelationship.create(
        organization_id=org_id,
        source_identity=f"src-{source_api}",
        source_api_name=source_api,
        source_type=source_type,
        target_identity=f"tgt-{target_api}",
        target_api_name=target_api,
        target_type=target_type,
        relationship_type=rel_type,
        sync_job_id=sync_job_id,
    )
    if deleted:
        rel.soft_delete(sync_job_id=sync_job_id)
    return rel


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
            email=f"relationship-{uuid.uuid4().hex[:8]}@test.local",
            password_hash="x",
            display_name="Relationship Test User",
        ))
        session.add(OrganizationModel(
            id=org_a,
            name="Relationship Store Test Org A",
            slug=f"relationship-a-{uuid.uuid4().hex[:8]}",
            description="Relationship store test org A",
            owner_id=user_id,
        ))
        session.add(OrganizationModel(
            id=org_b,
            name="Relationship Store Test Org B",
            slug=f"relationship-b-{uuid.uuid4().hex[:8]}",
            description="Relationship store test org B",
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
async def repo(db: dict[str, Any]) -> AsyncIterator[SQLAlchemyCanonicalRelationshipRepository]:
    async with db["session_factory"]() as session:
        yield SQLAlchemyCanonicalRelationshipRepository(session)


class TestIdempotentUpsert:
    async def test_create_and_duplicate_skip(
        self, db: dict[str, Any], repo: SQLAlchemyCanonicalRelationshipRepository,
    ) -> None:
        org_id = db["org_a"]
        rel = _relationship(org_id, "Account", "Account.MyField__c",
                            CanonicalRelationshipType.OBJECT_TO_FIELD)

        first = await repo.upsert_batch(org_id, [rel])
        second = await repo.upsert_batch(org_id, [rel])

        assert first.created == 1
        assert second.created == 0
        assert second.skipped == 1
        assert await repo.count_by_organization(org_id) == 1

    async def test_repeated_run_is_noop(
        self, db: dict[str, Any], repo: SQLAlchemyCanonicalRelationshipRepository,
    ) -> None:
        org_id = db["org_a"]
        rels = [
            _relationship(
                org_id, "Account", "Contact",
                CanonicalRelationshipType.FIELD_TO_LOOKUP_TARGET,
            ),
            _relationship(
                org_id, "Account", "AccountTrigger",
                CanonicalRelationshipType.TRIGGER_TO_OBJECT,
            ),
        ]
        await repo.upsert_batch(org_id, rels)

        result = await repo.upsert_batch(org_id, rels)

        assert result.created == 0
        assert result.skipped == 2

    async def test_concurrent_workers_do_not_duplicate_rows(
        self, db: dict[str, Any],
    ) -> None:
        import asyncio

        org_id = db["org_a"]
        rel = _relationship(org_id, "Concurrent", "ConcurrentField",
                            CanonicalRelationshipType.OBJECT_TO_FIELD)
        async with (
            db["session_factory"]() as session_a,
            db["session_factory"]() as session_b,
        ):
            repo_a = SQLAlchemyCanonicalRelationshipRepository(session_a)
            repo_b = SQLAlchemyCanonicalRelationshipRepository(session_b)
            result_a, result_b = await asyncio.gather(
                repo_a.upsert_batch(org_id, [rel]),
                repo_b.upsert_batch(org_id, [rel]),
            )
            count = await repo_a.count_by_organization(org_id)
        assert (result_a.created + result_b.created) == 1
        assert (result_a.skipped + result_b.skipped) == 1
        assert count == 1


class TestVersioning:
    async def test_deleted_row_reactivates_with_new_version(
        self, db: dict[str, Any], repo: SQLAlchemyCanonicalRelationshipRepository,
    ) -> None:
        org_id = db["org_a"]
        rel = _relationship(org_id, "V", "VField", CanonicalRelationshipType.OBJECT_TO_FIELD)
        await repo.upsert_batch(org_id, [rel])
        await repo.soft_delete_missing_for_source(org_id, rel.source_identity, set())

        revived = _relationship(org_id, "V", "VField", CanonicalRelationshipType.OBJECT_TO_FIELD)
        result = await repo.upsert_batch(org_id, [revived])

        assert result.created == 0
        assert result.updated == 1
        rows = await repo.list_by_source(org_id, rel.source_identity)
        assert len(rows) == 1
        assert rows[0].version == 2
        assert rows[0].previous_version == 1
        assert rows[0].deleted_at is None
        assert not rows[0].is_deleted

    async def test_deleted_edge_is_persisted_not_dropped(
        self, db: dict[str, Any], repo: SQLAlchemyCanonicalRelationshipRepository,
    ) -> None:
        org_id = db["org_a"]
        rel = _relationship(org_id, "Src", "GoneTarget", CanonicalRelationshipType.OBJECT_TO_FIELD,
                            deleted=True)

        result = await repo.upsert_batch(org_id, [rel])

        assert result.soft_deleted == 1
        assert await repo.count_by_organization(org_id) == 1
        active = await repo.list_active(org_id)
        assert active == []
        rows = await repo.list_by_source(org_id, rel.source_identity)
        assert len(rows) == 1
        assert rows[0].is_deleted

    async def test_active_row_marked_deleted_when_incoming_edge_is_deleted(
        self, db: dict[str, Any], repo: SQLAlchemyCanonicalRelationshipRepository,
    ) -> None:
        org_id = db["org_a"]
        rel = _relationship(org_id, "Src", "Tgt", CanonicalRelationshipType.OBJECT_TO_FIELD)
        await repo.upsert_batch(org_id, [rel])

        deleted_rel = _relationship(org_id, "Src", "Tgt", CanonicalRelationshipType.OBJECT_TO_FIELD,
                                    deleted=True)
        result = await repo.upsert_batch(org_id, [deleted_rel])

        assert result.created == 0
        assert result.soft_deleted == 1
        rows = await repo.list_by_source(org_id, rel.source_identity)
        assert rows[0].is_deleted
        assert rows[0].deleted_at is not None


class TestCleanup:
    async def test_soft_delete_missing_only_removes_unseen(
        self, db: dict[str, Any], repo: SQLAlchemyCanonicalRelationshipRepository,
    ) -> None:
        org_id = db["org_a"]
        kept = _relationship(org_id, "Src", "Kept", CanonicalRelationshipType.OBJECT_TO_FIELD)
        gone = _relationship(org_id, "Src", "Gone", CanonicalRelationshipType.OBJECT_TO_FIELD)
        await repo.upsert_batch(org_id, [kept, gone])

        deleted = await repo.soft_delete_missing_for_source(
            org_id, kept.source_identity,
            {(kept.target_identity, CanonicalRelationshipType.OBJECT_TO_FIELD.value)},
        )

        assert deleted == 1
        rows = await repo.list_by_source(org_id, kept.source_identity)
        by_target = {r.target_api_name: r for r in rows}
        assert not by_target["Kept"].is_deleted
        assert by_target["Gone"].is_deleted

    async def test_soft_delete_by_source_identities(
        self, db: dict[str, Any], repo: SQLAlchemyCanonicalRelationshipRepository,
    ) -> None:
        org_id = db["org_a"]
        rel_a = _relationship(org_id, "SourceA", "TgtA", CanonicalRelationshipType.OBJECT_TO_FIELD)
        rel_b = _relationship(org_id, "SourceB", "TgtB", CanonicalRelationshipType.OBJECT_TO_FIELD)
        await repo.upsert_batch(org_id, [rel_a, rel_b])

        deleted = await repo.soft_delete_by_source_identities(org_id, {rel_a.source_identity})

        assert deleted == 1
        assert await repo.count_by_organization(org_id) == 2
        active = await repo.list_active(org_id)
        assert [r.source_api_name for r in active] == ["SourceB"]


class TestIsolation:
    async def test_organizations_are_isolated(
        self, db: dict[str, Any], repo: SQLAlchemyCanonicalRelationshipRepository,
    ) -> None:
        org_a = db["org_a"]
        org_b = db["org_b"]
        rel_a = _relationship(
            org_a, "Account", "Account.F1", CanonicalRelationshipType.OBJECT_TO_FIELD,
        )
        rel_b = _relationship(
            org_b, "Account", "Account.F1", CanonicalRelationshipType.OBJECT_TO_FIELD,
        )
        await repo.upsert_batch(org_a, [rel_a])
        await repo.upsert_batch(org_b, [rel_b])

        rows_a = await repo.list_by_source(org_a, rel_a.source_identity)
        rows_b = await repo.list_by_source(org_b, rel_b.source_identity)
        assert len(rows_a) == 1
        assert len(rows_b) == 1
        assert rows_a[0].id != rows_b[0].id
        assert await repo.count_by_organization(org_a) == 1
        assert await repo.count_by_organization(org_b) == 1

    async def test_cleanup_is_tenant_scoped(
        self, db: dict[str, Any], repo: SQLAlchemyCanonicalRelationshipRepository,
    ) -> None:
        org_a = db["org_a"]
        org_b = db["org_b"]
        rel_b = _relationship(org_b, "OtherOrg", "Tgt", CanonicalRelationshipType.OBJECT_TO_FIELD)
        await repo.upsert_batch(org_b, [rel_b])

        deleted = await repo.soft_delete_missing_for_source(
            org_a, rel_b.source_identity, set(),
        )

        assert deleted == 0
        rows = await repo.list_by_source(org_b, rel_b.source_identity)
        assert not rows[0].is_deleted


class TestScale:
    async def test_large_organization_batch_and_cleanup(
        self, db: dict[str, Any], repo: SQLAlchemyCanonicalRelationshipRepository,
    ) -> None:
        org_id = db["org_a"]
        rels = [
            _relationship(org_id, "BigObj", f"BigObj.F{i:04d}",
                          CanonicalRelationshipType.OBJECT_TO_FIELD)
            for i in range(400)
        ]
        await repo.upsert_batch(org_id, rels)

        assert await repo.count_by_organization(org_id) == 400
        active = await repo.list_active(org_id, limit=500)
        assert len(active) == 400

        deleted = await repo.soft_delete_missing_for_source(org_id, "src-BigObj", set())
        assert deleted == 400
        assert await repo.list_active(org_id) == []

    async def test_list_active_pagination(
        self,
        db: dict[str, Any],
        repo: SQLAlchemyCanonicalRelationshipRepository,
    ) -> None:
        org_id = db["org_a"]
        rels = [
            _relationship(org_id, "PageObj", f"PageObj.F{i:03d}",
                          CanonicalRelationshipType.OBJECT_TO_FIELD)
            for i in range(25)
        ]
        await repo.upsert_batch(org_id, rels)

        page_one = await repo.list_active(org_id, limit=10)
        page_three = await repo.list_active(org_id, limit=10, offset=20)

        assert len(page_one) == 10
        assert len(page_three) == 5
        assert {r.id for r in page_one}.isdisjoint({r.id for r in page_three})


class TestEndToEndResolution:
    async def test_resolver_persists_typed_edges(
        self, db: dict[str, Any], repo: SQLAlchemyCanonicalRelationshipRepository,
    ) -> None:
        org_id = db["org_a"]
        org_str = str(org_id)
        identity_service = IdentityService()

        def ident(type_name: str, api_name: str) -> str:
            return identity_service.compute_component_hash(
                organization_id=org_str, source_platform="salesforce",
                type_name=type_name, api_name=api_name,
            )

        field = MetadataField(
            id=ident("field", "Account.MyField__c"),
            api_name="Account.MyField__c",
            type="field",
            organization_id=org_str,
            object_api_name="Account",
            field_type=FieldType.LOOKUP,
            reference_to="Contact",
        )
        active = {
            ident("object", "Account"),
            ident("object", "Contact"),
            ident("field", "Account.MyField__c"),
        }
        resolution = CanonicalRelationshipResolver().resolve(
            org_str, [field], active_targets=active,
        )

        assert resolution.missing_references == 0
        result = await repo.upsert_batch(org_id, resolution.relationships)

        assert result.created == 3
        rows = await repo.list_by_source(org_id, field.id)
        kinds = {r.relationship_type for r in rows}
        assert kinds == {
            CanonicalRelationshipType.FIELD_TO_OBJECT,
            CanonicalRelationshipType.OBJECT_TO_FIELD,
            CanonicalRelationshipType.FIELD_TO_LOOKUP_TARGET,
        }

    async def test_missing_references_never_persisted(
        self, db: dict[str, Any], repo: SQLAlchemyCanonicalRelationshipRepository,
    ) -> None:
        org_id = db["org_a"]
        org_str = str(org_id)
        identity_service = IdentityService()

        def ident(type_name: str, api_name: str) -> str:
            return identity_service.compute_component_hash(
                organization_id=org_str, source_platform="salesforce",
                type_name=type_name, api_name=api_name,
            )

        field = MetadataField(
            id=ident("field", "Ghost.Lookup__c"),
            api_name="Ghost.Lookup__c",
            type="field",
            organization_id=org_str,
            object_api_name="Ghost",
            field_type=FieldType.LOOKUP,
            reference_to="NeverExisted",
        )
        resolution = CanonicalRelationshipResolver().resolve(
            org_str, [field], active_targets=set(),
        )

        assert resolution.relationships == []
        assert resolution.missing_references == 3
        assert await repo.count_by_organization(org_id) == 0
