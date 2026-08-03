"""Integration tests for the SQLAlchemy Metadata Repository.

These tests run against a real PostgreSQL test database.  If the test
database is unreachable (e.g. local dev without Postgres running), the
tests skip gracefully with a clear message.

Marked with the ``integration`` marker (see pyproject.toml).
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

from sfir_backend.config.settings import Settings
from sfir_backend.domain.canonical.base import (
    CanonicalRelationship,
    MetadataComponent,
    MetadataStatus,
    RelationshipType,
    SourcePlatform,
)
from sfir_backend.domain.canonical.code import MetadataApexClass, MetadataTrigger
from sfir_backend.domain.canonical.core import (
    MetadataField,
    MetadataGlobalValueSet,
    MetadataObject,
)
from sfir_backend.domain.canonical.custom import (
    MetadataCustomMetadata,
    MetadataCustomSetting,
)
from sfir_backend.domain.canonical.flows import MetadataFlow, MetadataFlowVersion
from sfir_backend.domain.canonical.integration import (
    MetadataConnectedApp,
    MetadataEmailTemplate,
    MetadataNamedCredential,
)
from sfir_backend.domain.canonical.layouts import MetadataLayout, MetadataRecordType
from sfir_backend.domain.canonical.permissions import (
    MetadataPermissionSet,
    MetadataProfile,
)
from sfir_backend.domain.canonical.reporting import MetadataDashboard, MetadataReport
from sfir_backend.domain.canonical.ui import MetadataLightningPage, MetadataQuickAction
from sfir_backend.domain.canonical.validation import (
    MetadataFormula,
    MetadataValidationRule,
)
from sfir_backend.domain.canonical.workflows import (
    MetadataApprovalProcess,
    MetadataWorkflow,
)
from sfir_backend.domain.repositories.metadata_repo import (
    MetadataFilter,
    Pagination,
    SortOrder,
)
from sfir_backend.domain.request_context import RequestContext
from sfir_backend.infrastructure.persistence.models import metadata_components  # noqa: F401
from sfir_backend.infrastructure.persistence.models import metadata_sync  # noqa: F401
from sfir_backend.infrastructure.persistence.models.metadata_components import (
    MetadataDependencyModel,
    MetadataRelationshipModel,
)
from sfir_backend.infrastructure.persistence.models.metadata_sync import (
    MetadataVersionModel,
    SyncJobModel,
)
from sfir_backend.infrastructure.persistence.models.organization import (
    OrganizationModel,
)
from sfir_backend.infrastructure.persistence.repositories.metadata_repo import (
    SQLAlchemyMetadataRepository,
    _TYPE_TO_CANONICAL_CLASS,
)

pytestmark = pytest.mark.integration

TEST_ORG_NAME = "Integration Test Org"


def _make_component(
    type: str,
    api_name: str,
    label: str,
    namespace: str | None = None,
    description: str | None = None,
) -> MetadataComponent:
    return MetadataComponent(
        id=str(uuid.uuid4()),
        organization_id=str(uuid.uuid4()),
        type=type,
        api_name=api_name,
        label=label,
        namespace=namespace,
        description=description or f"Description for {api_name}",
        hash=f"hash-{api_name}",
        status=MetadataStatus.ACTIVE,
        source_platform=SourcePlatform.SALESFORCE,
        metadata_properties={},
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
    """Create tables, seed an organization + sync job, and clean up."""
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
            slug=f"integration-{uuid.uuid4().hex[:8]}",
            description="Integration test org",
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


class TestCrudRoundTrip:
    """Full CRUD round-trip against a real database."""

    async def test_save_and_get_by_api_name(
        self, db: dict[str, Any], repo: SQLAlchemyMetadataRepository,
    ) -> None:
        org_id = db["org_id"]
        component = _make_component("ApexClass", "IntegrationClass", "Integration Class")
        ctx = _ctx(org_id)

        saved = await repo.save(org_id, component, request_context=ctx)
        assert saved.api_name == "IntegrationClass"

        found = await repo.get_by_api_name(org_id, "IntegrationClass", request_context=ctx)
        assert found is not None
        assert found.type == "ApexClass"
        assert found.label == "Integration Class"

    async def test_update_existing(
        self, db: dict[str, Any], repo: SQLAlchemyMetadataRepository,
    ) -> None:
        org_id = db["org_id"]
        component = _make_component("Flow", "Integration_Flow", "Integration Flow")
        ctx = _ctx(org_id)
        await repo.save(org_id, component, request_context=ctx)

        updated = _make_component("Flow", "Integration_Flow", "Updated Flow Label")
        result = await repo.update(org_id, updated, request_context=ctx)
        assert result.label == "Updated Flow Label"

        found = await repo.get_by_api_name(org_id, "Integration_Flow", request_context=ctx)
        assert found is not None
        assert found.label == "Updated Flow Label"

    async def test_delete_removes_component(
        self, db: dict[str, Any], repo: SQLAlchemyMetadataRepository,
    ) -> None:
        org_id = db["org_id"]
        component = _make_component("Layout", "IntegrationLayout", "Integration Layout")
        ctx = _ctx(org_id)
        await repo.save(org_id, component, request_context=ctx)

        deleted = await repo.delete(org_id, "IntegrationLayout", request_context=ctx)
        assert deleted is True

        found = await repo.get_by_api_name(org_id, "IntegrationLayout", request_context=ctx)
        assert found is None

    async def test_delete_nonexistent_returns_false(
        self, db: dict[str, Any], repo: SQLAlchemyMetadataRepository,
    ) -> None:
        org_id = db["org_id"]
        ctx = _ctx(org_id)
        deleted = await repo.delete(org_id, "DoesNotExist", request_context=ctx)
        assert deleted is False


class TestPaginationAndFiltering:
    """Pagination, sorting, and filtering against a real database."""

    async def test_get_by_type_with_pagination(
        self, db: dict[str, Any], repo: SQLAlchemyMetadataRepository,
    ) -> None:
        org_id = db["org_id"]
        ctx = _ctx(org_id)
        components = [
            _make_component("ApexClass", f"PagingClass{i}", f"Paging Class {i}")
            for i in range(5)
        ]
        await repo.save_batch(org_id, components, request_context=ctx)

        page1 = await repo.get_by_type(
            org_id, "ApexClass",
            pagination=Pagination(limit=2, offset=0),
            sort=SortOrder(field="api_name"),
            request_context=ctx,
        )
        assert len(page1) == 2

        page2 = await repo.get_by_type(
            org_id, "ApexClass",
            pagination=Pagination(limit=2, offset=2),
            sort=SortOrder(field="api_name"),
            request_context=ctx,
        )
        assert len(page2) == 2
        names = {c.api_name for c in page1 + page2}
        assert len(names) == 4

    async def test_filter_by_namespace(
        self, db: dict[str, Any], repo: SQLAlchemyMetadataRepository,
    ) -> None:
        org_id = db["org_id"]
        ctx = _ctx(org_id)
        await repo.save(
            org_id, _make_component("ApexClass", "NsClass", "Ns Class", namespace="ns1"),
            request_context=ctx,
        )
        await repo.save(
            org_id, _make_component("ApexClass", "OtherClass", "Other Class", namespace="ns2"),
            request_context=ctx,
        )

        results = await repo.get_by_organization(
            org_id,
            filter=MetadataFilter(namespaces=["ns1"]),
            request_context=ctx,
        )
        assert all(c.namespace == "ns1" for c in results)
        assert any(c.api_name == "NsClass" for c in results)

    async def test_filter_by_type_does_not_filter_api_name(
        self, db: dict[str, Any], repo: SQLAlchemyMetadataRepository,
    ) -> None:
        org_id = db["org_id"]
        ctx = _ctx(org_id)
        await repo.save(
            org_id, _make_component("ApexClass", "FilteredClass", "Filtered Class"),
            request_context=ctx,
        )
        await repo.save(
            org_id, _make_component("Report", "FilteredReport", "Filtered Report"),
            request_context=ctx,
        )

        results = await repo.get_by_organization(
            org_id,
            filter=MetadataFilter(types=["ApexClass"]),
            request_context=ctx,
        )

        assert {c.type for c in results} == {"ApexClass"}
        assert any(c.api_name == "FilteredClass" for c in results)
        assert all(c.api_name != "FilteredReport" for c in results)

    async def test_search_by_text(
        self, db: dict[str, Any], repo: SQLAlchemyMetadataRepository,
    ) -> None:
        org_id = db["org_id"]
        ctx = _ctx(org_id)
        await repo.save(
            org_id, _make_component("Report", "SearchReport", "Quarterly Revenue"),
            request_context=ctx,
        )

        results = await repo.search(
            org_id, "Revenue",
            type_filter=["Report"],
            request_context=ctx,
        )
        assert any(c.api_name == "SearchReport" for c in results)

    async def test_count_and_types(
        self, db: dict[str, Any], repo: SQLAlchemyMetadataRepository,
    ) -> None:
        org_id = db["org_id"]
        ctx = _ctx(org_id)
        count = await repo.count_by_organization(org_id, request_context=ctx)
        types = await repo.get_types(org_id, request_context=ctx)
        assert count >= 0
        assert isinstance(types, list)
        assert all(isinstance(t, str) for t in types)


class TestOrganizationIsolation:
    """Tenant isolation across organizations."""

    async def test_orgs_do_not_see_each_others_data(
        self, db: dict[str, Any], repo: SQLAlchemyMetadataRepository,
    ) -> None:
        org_id = db["org_id"]
        other_org_id = uuid.uuid4()
        ctx = _ctx(org_id)

        await repo.save(
            org_id, _make_component("Profile", "IsolatedProfile", "Isolated Profile"),
            request_context=ctx,
        )

        # A second organization should not see org1's components.
        other_ctx = _ctx(other_org_id)
        found = await repo.get_by_api_name(
            other_org_id, "IsolatedProfile", request_context=other_ctx,
        )
        assert found is None

    async def test_request_context_org_mismatch_raises(
        self, db: dict[str, Any], repo: SQLAlchemyMetadataRepository,
    ) -> None:
        org_id = db["org_id"]
        wrong_ctx = _ctx(uuid.uuid4())

        with pytest.raises(PermissionError, match="does not match"):
            await repo.get_by_api_name(org_id, "Anything", request_context=wrong_ctx)


class TestBulkOperations:
    """Bulk save and bulk load against a real database."""

    async def test_save_batch_then_bulk_load(
        self, db: dict[str, Any], repo: SQLAlchemyMetadataRepository,
    ) -> None:
        org_id = db["org_id"]
        ctx = _ctx(org_id)
        components = [
            _make_component("ApexClass", f"BulkClass{i}", f"Bulk Class {i}")
            for i in range(4)
        ]
        saved = await repo.save_batch(org_id, components, request_context=ctx)
        assert len(saved) == 4

        loaded = await repo.get_by_api_names(
            org_id,
            [f"BulkClass{i}" for i in range(4)],
            request_context=ctx,
        )
        assert len(loaded) == 4
        assert {c.api_name for c in loaded} == {f"BulkClass{i}" for i in range(4)}

    async def test_bulk_load_ignores_missing(
        self, db: dict[str, Any], repo: SQLAlchemyMetadataRepository,
    ) -> None:
        org_id = db["org_id"]
        ctx = _ctx(org_id)
        await repo.save(
            org_id, _make_component("ApexClass", "PresentClass", "Present"),
            request_context=ctx,
        )
        loaded = await repo.get_by_api_names(
            org_id, ["PresentClass", "MissingClass"], request_context=ctx,
        )
        assert len(loaded) == 1
        assert loaded[0].api_name == "PresentClass"


class TestRelationshipsAndDependencies:
    """Relationship and dependency lookups against a real database."""

    async def test_relationship_lookup(
        self, db: dict[str, Any], repo: SQLAlchemyMetadataRepository,
    ) -> None:
        org_id = db["org_id"]
        ctx = _ctx(org_id)
        await repo.save(
            org_id, _make_component("CustomObject", "Account", "Account"),
            request_context=ctx,
        )
        await repo.save(
            org_id, _make_component("CustomObject", "Contact", "Contact"),
            request_context=ctx,
        )

        async with db["session_factory"]() as session:
            session.add(MetadataRelationshipModel(
                id=uuid.uuid4(),
                organization_id=org_id,
                source_api_name="Account",
                source_type="CustomObject",
                target_api_name="Contact",
                target_type="CustomObject",
                relationship_type="lookup",
            ))
            await session.commit()

        results = await repo.get_relationships(org_id, "Account", request_context=ctx)
        assert any(c.api_name == "Contact" for c in results)

    async def test_dependency_lookup(
        self, db: dict[str, Any], repo: SQLAlchemyMetadataRepository,
    ) -> None:
        org_id = db["org_id"]
        ctx = _ctx(org_id)
        await repo.save(
            org_id, _make_component("ApexClass", "HelperClass", "Helper"),
            request_context=ctx,
        )
        await repo.save(
            org_id, _make_component("ApexClass", "MainClass", "Main"),
            request_context=ctx,
        )

        async with db["session_factory"]() as session:
            session.add(MetadataDependencyModel(
                id=uuid.uuid4(),
                organization_id=org_id,
                source_api_name="MainClass",
                source_type="ApexClass",
                target_api_name="HelperClass",
                target_type="ApexClass",
                dependency_type="code",
            ))
            await session.commit()

        results = await repo.get_dependencies(org_id, "MainClass", request_context=ctx)
        assert any(c.api_name == "HelperClass" for c in results)


class TestVersionLookup:
    """Version history lookup against a real database."""

    async def _seed_versions(
        self, db: dict[str, Any], api_name: str, count: int = 3,
    ) -> None:
        org_id = db["org_id"]
        sync_job_id = uuid.uuid4()
        async with db["session_factory"]() as session:
            session.add(SyncJobModel(
                id=sync_job_id,
                organization_id=org_id,
                connection_id=uuid.uuid4(),
                sync_type="metadata",
                status="completed",
            ))
            for i in range(1, count + 1):
                session.add(MetadataVersionModel(
                    id=uuid.uuid4(),
                    organization_id=org_id,
                    sync_job_id=sync_job_id,
                    component_type="ApexClass",
                    component_name=api_name,
                    component_id=str(uuid.uuid4()),
                    hash=f"hash-v{i}",
                    version_number=i,
                    action="created" if i == 1 else "updated",
                ))
            await session.commit()

    async def test_get_versions_returns_history(
        self, db: dict[str, Any], repo: SQLAlchemyMetadataRepository,
    ) -> None:
        org_id = db["org_id"]
        ctx = _ctx(org_id)
        await self._seed_versions(db, "VersionedClass", count=3)

        versions = await repo.get_versions(org_id, "VersionedClass", request_context=ctx)
        assert len(versions) == 3
        # Newest first.
        assert versions[0].version_number == 3
        assert versions[-1].version_number == 1

    async def test_get_latest_version(
        self, db: dict[str, Any], repo: SQLAlchemyMetadataRepository,
    ) -> None:
        org_id = db["org_id"]
        ctx = _ctx(org_id)
        await self._seed_versions(db, "LatestClass", count=4)

        latest = await repo.get_latest_version(org_id, "LatestClass", request_context=ctx)
        assert latest is not None
        assert latest.version_number == 4

    async def test_get_latest_version_missing(
        self, db: dict[str, Any], repo: SQLAlchemyMetadataRepository,
    ) -> None:
        org_id = db["org_id"]
        ctx = _ctx(org_id)
        latest = await repo.get_latest_version(org_id, "NoSuchVersion", request_context=ctx)
        assert latest is None

    async def test_list_versions_by_organization(
        self, db: dict[str, Any], repo: SQLAlchemyMetadataRepository,
    ) -> None:
        org_id = db["org_id"]
        ctx = _ctx(org_id)
        await self._seed_versions(db, "BulkClassA", count=2)
        await self._seed_versions(db, "BulkClassB", count=1)

        versions = await repo.list_versions_by_organization(
            org_id, limit=1000, request_context=ctx,
        )
        names = {v.component_name for v in versions}
        assert "BulkClassA" in names
        assert "BulkClassB" in names

    async def test_save_versions_bulk(
        self, db: dict[str, Any], repo: SQLAlchemyMetadataRepository,
    ) -> None:
        from sfir_backend.domain.entities.metadata_sync import MetadataVersion
        from sfir_backend.domain.value_objects.metadata import MetadataAction

        org_id = db["org_id"]
        sync_job_id = uuid.uuid4()
        async with db["session_factory"]() as session:
            session.add(SyncJobModel(
                id=sync_job_id,
                organization_id=org_id,
                connection_id=uuid.uuid4(),
                sync_type="metadata",
                status="completed",
            ))
            await session.commit()

        versions = [
            MetadataVersion.create(
                organization_id=org_id,
                sync_job_id=sync_job_id,
                component_type="ApexClass",
                component_name=f"SavedBulk{i}",
                component_id=None,
                hash=f"hash-sb{i}",
                version_number=1,
                action=MetadataAction.CREATED,
                payload={"api_name": f"SavedBulk{i}", "fingerprint": f"fp-sb{i}"},
                change_source="sync",
            )
            for i in range(3)
        ]
        ctx = _ctx(org_id)

        saved = await repo.save_versions(org_id, versions, request_context=ctx)
        assert len(saved) == 3

        found = await repo.list_versions_by_organization(
            org_id, limit=100, request_context=ctx,
        )
        names = {v.component_name for v in found}
        assert {"SavedBulk0", "SavedBulk1", "SavedBulk2"}.issubset(names)


class TestExtendedTypesCrud:
    """CRUD round-trips for the additional canonical metadata types."""

    @pytest.mark.parametrize(
        "type_name, api_name",
        [
            ("Role", "IntegrationRole"),
            ("Queue", "IntegrationQueue"),
            ("PublicGroup", "IntegrationGroup"),
            ("SharingRule", "Integration_Sharing"),
            ("GlobalValueSet", "Integration_GVS"),
            ("CustomMetadata", "Integration_CMT"),
            ("CustomSetting", "Integration_CST"),
            ("FlowVersion", "Integration_Flow_V1"),
            ("EmailTemplate", "Integration_Email"),
            ("NamedCredential", "Integration_NC"),
            ("ConnectedApp", "Integration_CA"),
            ("LightningPage", "Integration_LP"),
            ("QuickAction", "Integration_QA"),
            ("Formula", "Integration_Formula"),
            ("ApprovalProcess", "Integration_Approval"),
        ],
    )
    async def test_extended_type_round_trip(
        self, db: dict[str, Any], repo: SQLAlchemyMetadataRepository,
        type_name: str, api_name: str,
    ) -> None:
        org_id = db["org_id"]
        ctx = _ctx(org_id)
        component = _make_component(type_name, api_name, f"{type_name} Label")

        saved = await repo.save(org_id, component, request_context=ctx)
        assert saved.api_name == api_name

        found = await repo.get_by_api_name(org_id, api_name, request_context=ctx)
        assert found is not None
        assert found.type == type_name

    async def test_extended_types_in_get_types(
        self, db: dict[str, Any], repo: SQLAlchemyMetadataRepository,
    ) -> None:
        org_id = db["org_id"]
        ctx = _ctx(org_id)
        for type_name, api_name in [
            ("Role", "TypesRole"),
            ("Queue", "TypesQueue"),
            ("Formula", "TypesFormula"),
        ]:
            await repo.save(org_id, _make_component(type_name, api_name, api_name), request_context=ctx)

        types = await repo.get_types(org_id, request_context=ctx)
        assert "Role" in types
        assert "Queue" in types
        assert "Formula" in types


# Volatile identity fields assigned by the repository, not the client.
_VOLATILE_FIELDS = {"id", "organization_id", "created_at", "updated_at"}


def _typed_component(metadata_type: str, suffix: str = "") -> MetadataComponent:
    """Build a typed canonical component with representative type-specific
    fields (mirrors the unit round-trip suite)."""
    cls = _TYPE_TO_CANONICAL_CLASS[metadata_type]
    now = datetime.now(timezone.utc)
    api_name = f"Exact_{suffix}{metadata_type}"
    kwargs: dict[str, Any] = dict(
        type=metadata_type,
        api_name=api_name,
        label=f"Exact {metadata_type}",
        description=f"Exact {metadata_type} description",
        hash="exact-hash",
        status=MetadataStatus.ACTIVE,
        source_platform=SourcePlatform.SALESFORCE,
        metadata_properties={"custom": "kept"},
        created_at=now,
        updated_at=now,
    )
    if metadata_type == "ApexClass":
        kwargs.update(api_version=60, body="public class X {}", length=10)
    elif metadata_type == "Trigger":
        kwargs.update(object_api_name="Account", api_version=60, body="trigger T {}")
    elif metadata_type == "Object":
        kwargs.update(
            plural_label="Accounts", enable_activities=True,
            fields=[MetadataField(api_name="F1", label="F1", object_api_name="Account")],
            record_types=[{"fullName": "RT1"}],
        )
    elif metadata_type == "Field":
        kwargs.update(
            object_api_name="Account", field_type="text", length=255,
            formula="X", reference_to="Contact", track_feed_history=True,
        )
    elif metadata_type == "ValidationRule":
        kwargs.update(object_api_name="Account", active=True, formula="TRUE")
    elif metadata_type == "RecordType":
        kwargs.update(object_api_name="Account", active=True)
    elif metadata_type == "Flow":
        kwargs.update(
            flow_status=MetadataStatus.DRAFT, record_creates=["Account"],
            versions=[MetadataFlowVersion(api_name="F-1", flow_api_name="F", version_number=1)],
        )
    elif metadata_type == "FlowVersion":
        kwargs.update(flow_api_name="F", version_number=2, definition={"x": 1})
    elif metadata_type == "Layout":
        kwargs.update(object_api_name="Account", layout_type="Standard")
    elif metadata_type == "Profile":
        kwargs.update(user_license="Salesforce", setup_sections=[{"name": "s1"}])
    elif metadata_type == "PermissionSet":
        kwargs.update(user_license="Salesforce", setup_sections=[{"name": "s1"}])
    elif metadata_type == "Report":
        kwargs.update(
            object_api_name="Account", report_format="tabular", params={"p": 1},
        )
    elif metadata_type == "Dashboard":
        kwargs.update(background_fitness="Blur", left_section=[{"name": "l1"}])
    elif metadata_type == "Workflow":
        kwargs.update(object_api_name="Account", formula_criteria="TRUE")
    elif metadata_type == "Role":
        kwargs.update(parent_role="CEO", may_forecast_manager=True)
    elif metadata_type == "Queue":
        kwargs.update(email="q@example.com", queue_sobjects=[{"sobject": "Account"}])
    elif metadata_type == "PublicGroup":
        kwargs.update(members=[{"name": "m1"}])
    elif metadata_type == "SharingRule":
        kwargs.update(object_api_name="Account", shared_to="Group1")
    elif metadata_type == "GlobalValueSet":
        kwargs.update(master_label="ML1", grouped=True)
    elif metadata_type == "CustomMetadata":
        kwargs.update(visibility="Protected", fields=[{"name": "f1"}])
    elif metadata_type == "CustomSetting":
        kwargs.update(setting_type="List", visibility="Protected")
    elif metadata_type == "EmailTemplate":
        kwargs.update(template_type="Text", content="Hello", subject="Subj")
    elif metadata_type == "NamedCredential":
        kwargs.update(endpoint="https://x", principal_type="NamedUser")
    elif metadata_type == "ConnectedApp":
        kwargs.update(version="1.0", contact_email="a@b.c")
    elif metadata_type == "LightningPage":
        kwargs.update(master_label="ML1", page_type="AppPage")
    elif metadata_type == "QuickAction":
        kwargs.update(object_api_name="Account", action_type="Create")
    elif metadata_type == "Formula":
        kwargs.update(
            object_api_name="Account", field_api_name="F1", formula_expression="X",
        )
    elif metadata_type == "ApprovalProcess":
        kwargs.update(object_api_name="Account", active=True)
    return cls(**kwargs)


class TestExactRoundTripAllTypes:
    """Phase 3.6 Repository Contract, proven against a real database:
    save(entity) -> get(entity.api_name) returns an EXACTLY equal component
    for every one of the 27 entity types."""

    @pytest.mark.parametrize("metadata_type", sorted(_TYPE_TO_CANONICAL_CLASS))
    async def test_exact_round_trip(
        self, db: dict[str, Any], repo: SQLAlchemyMetadataRepository,
        metadata_type: str,
    ) -> None:
        org_id = db["org_id"]
        ctx = _ctx(org_id)
        component = _typed_component(metadata_type, suffix="RT_")
        component.relationships = [
            CanonicalRelationship(
                type=RelationshipType.REFERENCES,
                target_type="Object",
                target_api_name="Account",
                target_label="Account",
                metadata={"k": "v"},
            ),
        ]

        await repo.save(org_id, component, request_context=ctx)
        loaded = await repo.get_by_api_name(
            org_id, component.api_name, request_context=ctx,
        )
        assert loaded is not None, f"get_by_api_name returned None for {metadata_type}"

        a = component.model_dump()
        b = loaded.model_dump()
        for key in _VOLATILE_FIELDS:
            a.pop(key, None)
            b.pop(key, None)
        assert a == b, (
            f"exact round-trip failed for {metadata_type}: "
            f"expected={a!r} loaded={b!r}"
        )

    @pytest.mark.parametrize("metadata_type", sorted(_TYPE_TO_CANONICAL_CLASS))
    async def test_relationships_survive_real_persist(
        self, db: dict[str, Any], repo: SQLAlchemyMetadataRepository,
        metadata_type: str,
    ) -> None:
        org_id = db["org_id"]
        ctx = _ctx(org_id)
        # The relationship target must exist as a real component for
        # get_relationships to resolve it.
        target = _typed_component("Object", suffix=f"TGT_{metadata_type}_")
        await repo.save(org_id, target, request_context=ctx)
        component = _typed_component(metadata_type, suffix=f"REL_{metadata_type}_")
        component.relationships = [
            CanonicalRelationship(
                type=RelationshipType.REFERENCES,
                target_type="Object",
                target_api_name=target.api_name,
                target_label="Exact Object",
            ),
        ]
        await repo.save(org_id, component, request_context=ctx)
        loaded = await repo.get_by_api_name(
            org_id, component.api_name, request_context=ctx,
        )
        assert loaded is not None
        assert len(loaded.relationships) == 1
        assert loaded.relationships[0].target_api_name == target.api_name
        # The edge must also be queryable through get_relationships.
        rels = await repo.get_relationships(
            org_id, component.api_name, request_context=ctx,
        )
        assert any(c.api_name == target.api_name for c in rels)
