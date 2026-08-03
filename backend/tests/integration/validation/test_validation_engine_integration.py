"""Integration tests for the Metadata Validation & Consistency Engine.

These tests run against a real PostgreSQL test database.  If the test
database is unreachable (e.g. local dev without Postgres running), the
tests skip gracefully with a clear message.

Marked with the ``integration`` marker (see pyproject.toml).

Phase 3.6 repaired the repository write path: previously ``save`` crashed
with a TypeError for 9 of the 27 named types (Field, ValidationRule,
RecordType, Layout, Profile, PermissionSet, Report, Dashboard, Workflow)
because ``_component_to_orm`` blindly emitted ``namespace`` / ``description``
column values those ORM models do not define.  The write path is now
schema-aware, so those types persist and round-trip exactly (see
``TestWritePathRoundTrip``).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from sfir_backend.application.use_cases.metadata.validation_engine import (
    MetadataValidationEngine,
)
from sfir_backend.config.settings import Settings
from sfir_backend.domain.canonical.base import (
    MetadataComponent,
    MetadataStatus,
    SourcePlatform,
)
from sfir_backend.domain.request_context import RequestContext
from sfir_backend.infrastructure.persistence.models import metadata_components  # noqa: F401
from sfir_backend.infrastructure.persistence.models import metadata_sync  # noqa: F401
from sfir_backend.infrastructure.persistence.models.organization import (
    OrganizationModel,
)
from sfir_backend.infrastructure.persistence.repositories.metadata_repo import (
    SQLAlchemyMetadataRepository,
)

pytestmark = pytest.mark.integration

TEST_ORG_NAME = "Validation Engine Integration Org"


def _make_component(
    type: str,
    api_name: str,
    label: str,
    properties: dict | None = None,
) -> MetadataComponent:
    return MetadataComponent(
        id=str(uuid.uuid4()),
        organization_id=str(uuid.uuid4()),
        type=type,
        api_name=api_name,
        label=label,
        hash=f"hash-{api_name}",
        status=MetadataStatus.ACTIVE,
        source_platform=SourcePlatform.SALESFORCE,
        metadata_properties=properties or {},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest_asyncio.fixture(scope="module")
async def engine() -> AsyncIterator[AsyncEngine]:
    """Create the test engine, skipping if the test DB is unreachable."""
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


@pytest_asyncio.fixture(scope="module")
async def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(scope="module")
async def db(engine: AsyncEngine, session_factory: Any) -> AsyncIterator[dict[str, Any]]:
    """Create tables, seed an organization, and clean up."""
    from sfir_backend.infrastructure.database.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(OrganizationModel(
            id=org_id,
            name=TEST_ORG_NAME,
            slug=f"validation-{uuid.uuid4().hex[:8]}",
            description="Validation engine integration org",
            owner_id=user_id,
        ))
        await session.commit()

    yield {
        "org_id": org_id,
        "session_factory": session_factory,
    }

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def repo(db: dict[str, Any]) -> AsyncIterator[SQLAlchemyMetadataRepository]:
    async with db["session_factory"]() as session:
        yield SQLAlchemyMetadataRepository(session)


def _ctx(org_id: uuid.UUID) -> RequestContext:
    return RequestContext.authenticated(
        user_id=uuid.uuid4(),
        organization_id=org_id,
    )


class TestWritePathRoundTrip:
    """Phase 3.6: the write path is schema-aware; previously-crashing types
    now persist and round-trip exactly."""

    @pytest.mark.asyncio
    async def test_field_saves_and_round_trips_without_namespace_column(
        self, db: dict[str, Any], repo: SQLAlchemyMetadataRepository,
    ) -> None:
        org_id = db["org_id"]
        ctx = _ctx(org_id)
        field = _make_component(
            "Field", "Account.Name", "Name",
            properties={"object_api_name": "Account", "field_type": "text"},
        )
        # This used to raise TypeError (missing namespace/description columns).
        saved = await repo.save(org_id, field, request_context=ctx)
        assert saved.api_name == "Account.Name"

        loaded = await repo.get_by_api_name(org_id, "Account.Name", request_context=ctx)
        assert loaded is not None
        assert loaded.type == "Field"
        assert loaded.metadata_properties["object_api_name"] == "Account"
        assert loaded.metadata_properties["field_type"] == "text"

    @pytest.mark.asyncio
    async def test_all_previously_crashing_types_persist(
        self, db: dict[str, Any], repo: SQLAlchemyMetadataRepository,
    ) -> None:
        org_id = db["org_id"]
        ctx = _ctx(org_id)
        for metadata_type in [
            "Field", "ValidationRule", "RecordType", "Layout", "Profile",
            "PermissionSet", "Report", "Dashboard", "Workflow",
        ]:
            component = _make_component(
                metadata_type, f"RT_{metadata_type}", metadata_type,
            )
            saved = await repo.save(org_id, component, request_context=ctx)
            assert saved.type == metadata_type
            loaded = await repo.get_by_api_name(
                org_id, f"RT_{metadata_type}", request_context=ctx,
            )
            assert loaded is not None
            assert loaded.type == metadata_type
            assert loaded.label == metadata_type


class TestEngineAgainstRealRepository:
    @pytest.mark.asyncio
    async def test_engine_validates_healthy_org(
        self, db: dict[str, Any], repo: SQLAlchemyMetadataRepository,
    ) -> None:
        org_id = db["org_id"]
        ctx = _ctx(org_id)

        # Seed types whose write path works (Object, ApexClass, Flow).
        await repo.save(org_id, _make_component("Object", "Account", "Account"), request_context=ctx)
        await repo.save(org_id, _make_component("Object", "Contact", "Contact"), request_context=ctx)
        await repo.save(org_id, _make_component("ApexClass", "MyController", "MyController"), request_context=ctx)

        engine = MetadataValidationEngine(metadata_repo=repo)
        report = await engine.validate(org_id, request_context=ctx)

        assert report.passed is True
        assert report.metadata_counts["Object"] == 2
        assert report.metadata_counts["ApexClass"] == 1
        assert not report.consistency_failures
        assert not report.integrity_failures

    @pytest.mark.asyncio
    async def test_engine_detects_broken_flow_reference(
        self, db: dict[str, Any], repo: SQLAlchemyMetadataRepository,
    ) -> None:
        org_id = db["org_id"]
        ctx = _ctx(org_id)

        await repo.save(org_id, _make_component("Object", "Account", "Account"), request_context=ctx)
        # Flow with a record_creates target that does not exist. metadata_properties
        # survives the round-trip, so the engine can validate it.
        await repo.save(
            org_id,
            _make_component(
                "Flow", "BrokenFlow", "Broken Flow",
                properties={"record_creates": [{"object": "GhostObject"}]},
            ),
            request_context=ctx,
        )

        engine = MetadataValidationEngine(metadata_repo=repo)
        report = await engine.validate(org_id, request_context=ctx)

        assert report.passed is False
        assert any(
            f.error_code == "BROKEN_REFERENCE"
            and f.reference_api_name == "GhostObject"
            for f in report.consistency_failures
        )

    @pytest.mark.asyncio
    async def test_engine_completeness_mismatch(
        self, db: dict[str, Any], repo: SQLAlchemyMetadataRepository,
    ) -> None:
        org_id = db["org_id"]
        ctx = _ctx(org_id)
        await repo.save(org_id, _make_component("Object", "Account", "Account"), request_context=ctx)

        engine = MetadataValidationEngine(metadata_repo=repo)
        report = await engine.validate(
            org_id, request_context=ctx,
            downloaded_counts={"Object": 7},
        )

        assert report.passed is False
        assert report.missing_metadata
        assert report.missing_metadata[0].error_code == "COUNT_MISMATCH"
        assert report.missing_metadata[0].metadata == {
            "downloaded": 7, "persisted": 1,
        }

    @pytest.mark.asyncio
    async def test_repository_unchanged_after_validation(
        self, db: dict[str, Any], repo: SQLAlchemyMetadataRepository,
    ) -> None:
        org_id = db["org_id"]
        ctx = _ctx(org_id)
        await repo.save(org_id, _make_component("Object", "Account", "Account"), request_context=ctx)

        before = await repo.count_by_organization(org_id, request_context=ctx)

        engine = MetadataValidationEngine(metadata_repo=repo)
        await engine.validate(org_id, request_context=ctx)

        after = await repo.count_by_organization(org_id, request_context=ctx)
        assert before == after == 1

    @pytest.mark.asyncio
    async def test_read_path_note_reported(
        self, db: dict[str, Any], repo: SQLAlchemyMetadataRepository,
    ) -> None:
        org_id = db["org_id"]
        ctx = _ctx(org_id)
        await repo.save(org_id, _make_component("Object", "Account", "Account"), request_context=ctx)

        engine = MetadataValidationEngine(metadata_repo=repo)
        report = await engine.validate(org_id, request_context=ctx)
        assert any(f.error_code == "READ_PATH_NOTE" for f in report.findings)
