"""Unit tests for the MetadataRepository implementation."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.domain.canonical.base import (
    MetadataComponent,
    MetadataStatus,
    SourcePlatform,
)
from sfir_backend.domain.repositories.metadata_repo import (
    IMetadataRepository,
    MetadataFilter,
    Pagination,
    SortOrder,
)
from sfir_backend.domain.request_context import RequestContext
from sfir_backend.infrastructure.persistence.repositories.metadata_repo import (
    SQLAlchemyMetadataRepository,
    _component_to_orm,
    _orm_to_component,
    _TYPE_TO_ORM_MODEL,
)


def _make_component(
    type: str = "ApexClass",
    api_name: str = "MyClass",
    label: str = "My Class",
    namespace: str | None = None,
) -> MetadataComponent:
    return MetadataComponent(
        id=str(uuid.uuid4()),
        organization_id=str(uuid.uuid4()),
        type=type,
        api_name=api_name,
        label=label,
        namespace=namespace,
        description="Test component",
        hash="abc123",
        status=MetadataStatus.ACTIVE,
        source_platform=SourcePlatform.SALESFORCE,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _make_request_context(
    org_id: uuid.UUID | None = None,
) -> RequestContext:
    return RequestContext.authenticated(
        user_id=uuid.uuid4(),
        organization_id=org_id or uuid.uuid4(),
    )


class TestTypeMapping:
    """Verify that the type-to-ORM mapping covers all expected types."""

    def test_apex_class_mapped(self) -> None:
        assert "ApexClass" in _TYPE_TO_ORM_MODEL

    def test_trigger_mapped(self) -> None:
        assert "Trigger" in _TYPE_TO_ORM_MODEL

    def test_object_mapped(self) -> None:
        assert "Object" in _TYPE_TO_ORM_MODEL

    def test_field_mapped(self) -> None:
        assert "Field" in _TYPE_TO_ORM_MODEL

    def test_validation_rule_mapped(self) -> None:
        assert "ValidationRule" in _TYPE_TO_ORM_MODEL

    def test_record_type_mapped(self) -> None:
        assert "RecordType" in _TYPE_TO_ORM_MODEL

    def test_flow_mapped(self) -> None:
        assert "Flow" in _TYPE_TO_ORM_MODEL

    def test_layout_mapped(self) -> None:
        assert "Layout" in _TYPE_TO_ORM_MODEL

    def test_profile_mapped(self) -> None:
        assert "Profile" in _TYPE_TO_ORM_MODEL

    def test_permission_set_mapped(self) -> None:
        assert "PermissionSet" in _TYPE_TO_ORM_MODEL

    def test_report_mapped(self) -> None:
        assert "Report" in _TYPE_TO_ORM_MODEL

    def test_dashboard_mapped(self) -> None:
        assert "Dashboard" in _TYPE_TO_ORM_MODEL

    def test_workflow_mapped(self) -> None:
        assert "Workflow" in _TYPE_TO_ORM_MODEL

    def test_extended_types_mapped(self) -> None:
        """The 15 additional canonical types must be mapped to ORM models."""
        for t in [
            "Role", "Queue", "PublicGroup", "SharingRule", "GlobalValueSet",
            "CustomMetadata", "CustomSetting", "FlowVersion", "EmailTemplate",
            "NamedCredential", "ConnectedApp", "LightningPage", "QuickAction",
            "Formula", "ApprovalProcess", "Relationship",
        ]:
            assert t in _TYPE_TO_ORM_MODEL, f"{t} missing from _TYPE_TO_ORM_MODEL"

    def test_all_mapped_types_have_models(self) -> None:
        """Verify every mapped type has a corresponding ORM model."""
        from sfir_backend.infrastructure.persistence.models.metadata_components import (
            MetadataApexClassModel,
            MetadataApprovalProcessModel,
            MetadataConnectedAppModel,
            MetadataCustomMetadataModel,
            MetadataCustomSettingModel,
            MetadataDashboardModel,
            MetadataEmailTemplateModel,
            MetadataFieldModel,
            MetadataFlowModel,
            MetadataFlowVersionModel,
            MetadataFormulaModel,
            MetadataGlobalValueSetModel,
            MetadataLayoutModel,
            MetadataLightningPageModel,
            MetadataNamedCredentialModel,
            MetadataObjectModel,
            MetadataPermissionSetModel,
            MetadataProfileModel,
            MetadataPublicGroupModel,
            MetadataQueueModel,
            MetadataQuickActionModel,
            MetadataRecordTypeModel,
            MetadataRelationshipModel,
            MetadataReportModel,
            MetadataRoleModel,
            MetadataSharingRuleModel,
            MetadataTriggerModel,
            MetadataValidationRuleModel,
            MetadataWorkflowRuleModel,
        )
        expected_models = {
            MetadataApexClassModel,
            MetadataApprovalProcessModel,
            MetadataConnectedAppModel,
            MetadataCustomMetadataModel,
            MetadataCustomSettingModel,
            MetadataDashboardModel,
            MetadataEmailTemplateModel,
            MetadataFieldModel,
            MetadataFlowModel,
            MetadataFlowVersionModel,
            MetadataFormulaModel,
            MetadataGlobalValueSetModel,
            MetadataLayoutModel,
            MetadataLightningPageModel,
            MetadataNamedCredentialModel,
            MetadataObjectModel,
            MetadataPermissionSetModel,
            MetadataProfileModel,
            MetadataPublicGroupModel,
            MetadataQueueModel,
            MetadataQuickActionModel,
            MetadataRecordTypeModel,
            MetadataRelationshipModel,
            MetadataReportModel,
            MetadataRoleModel,
            MetadataSharingRuleModel,
            MetadataTriggerModel,
            MetadataValidationRuleModel,
            MetadataWorkflowRuleModel,
        }
        mapped_models = set(_TYPE_TO_ORM_MODEL.values())
        assert mapped_models == expected_models


class TestTypeAliases:
    """Verify snake_case canonical and legacy Salesforce names resolve."""

    def test_snake_case_aliases(self) -> None:
        from sfir_backend.infrastructure.persistence.repositories.metadata_repo import (
            _resolve_type,
        )
        assert _resolve_type("apex_class") == "ApexClass"
        assert _resolve_type("object") == "Object"
        assert _resolve_type("field") == "Field"
        assert _resolve_type("validation_rule") == "ValidationRule"
        assert _resolve_type("trigger") == "Trigger"
        assert _resolve_type("workflow") == "Workflow"
        assert _resolve_type("flow_version") == "FlowVersion"
        assert _resolve_type("approval_process") == "ApprovalProcess"

    def test_legacy_salesforce_aliases(self) -> None:
        from sfir_backend.infrastructure.persistence.repositories.metadata_repo import (
            _resolve_type,
        )
        assert _resolve_type("CustomObject") == "Object"
        assert _resolve_type("CustomField") == "Field"
        assert _resolve_type("ApexTrigger") == "Trigger"
        assert _resolve_type("WorkflowRule") == "Workflow"

    def test_unknown_type_passthrough(self) -> None:
        from sfir_backend.infrastructure.persistence.repositories.metadata_repo import (
            _resolve_type,
        )
        assert _resolve_type("BogusThing") == "BogusThing"


class TestComponentToOrmConversion:
    """Verify conversion from canonical component to ORM values."""

    def test_converts_base_fields(self) -> None:
        org_id = uuid.uuid4()
        component = _make_component(type="ApexClass", api_name="MyClass")

        values = _component_to_orm(org_id, component)

        assert values["organization_id"] == org_id
        assert values["api_name"] == "MyClass"
        assert values["label"] == "My Class"
        assert values["fingerprint"] == "abc123"
        assert isinstance(values["metadata_properties"], dict)

    def test_handles_no_namespace(self) -> None:
        org_id = uuid.uuid4()
        component = _make_component(namespace=None)

        values = _component_to_orm(org_id, component)
        assert values["namespace"] is None

    def test_handles_with_namespace(self) -> None:
        org_id = uuid.uuid4()
        component = _make_component(namespace="myns")

        values = _component_to_orm(org_id, component)
        assert values["namespace"] == "myns"


class TestOrmToComponentConversion:
    """Verify conversion from ORM model to canonical component."""

    def test_converts_base_fields(self) -> None:
        mock_orm = MagicMock()
        mock_orm.id = uuid.uuid4()
        mock_orm.organization_id = uuid.uuid4()
        mock_orm.api_name = "MyClass"
        mock_orm.label = "My Class"
        mock_orm.namespace = None
        mock_orm.description = "A test class"
        mock_orm.fingerprint = "def456"
        mock_orm.metadata_properties = {"key": "value"}
        mock_orm.created_at = datetime.now(timezone.utc)
        mock_orm.updated_at = datetime.now(timezone.utc)

        component = _orm_to_component(mock_orm, "ApexClass")

        assert component.type == "ApexClass"
        assert component.api_name == "MyClass"
        assert component.label == "My Class"
        assert component.description == "A test class"
        assert component.hash == "def456"
        assert component.metadata_properties == {"key": "value"}
        assert component.status == MetadataStatus.ACTIVE
        assert component.source_platform == SourcePlatform.SALESFORCE


class TestTenantVerification:
    """Verify tenant isolation via RequestContext."""

    async def test_raises_on_org_mismatch(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)
        org_id = uuid.uuid4()
        wrong_ctx = _make_request_context(org_id=uuid.uuid4())

        with pytest.raises(PermissionError, match="does not match"):
            repo._verify_tenant(org_id, wrong_ctx)

    async def test_passes_on_org_match(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)
        org_id = uuid.uuid4()
        ctx = _make_request_context(org_id=org_id)

        # Should not raise
        repo._verify_tenant(org_id, ctx)

    async def test_passes_without_request_context(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)
        org_id = uuid.uuid4()

        # Should not raise
        repo._verify_tenant(org_id, None)


class TestSave:
    """Verify save operations."""

    async def test_save_creates_orm_instance(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)
        org_id = uuid.uuid4()
        component = _make_component(type="ApexClass", api_name="TestClass")

        result = await repo.save(org_id, component)

        assert result.api_name == "TestClass"
        session.add.assert_called_once()
        session.flush.assert_awaited_once()

    async def test_save_raises_for_unsupported_type(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)
        org_id = uuid.uuid4()
        component = _make_component(type="UnknownType", api_name="Test")

        with pytest.raises(ValueError, match="Unsupported metadata type"):
            await repo.save(org_id, component)

    async def test_save_with_request_context(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)
        org_id = uuid.uuid4()
        ctx = _make_request_context(org_id=org_id)
        component = _make_component(type="ApexClass", api_name="TestClass")

        result = await repo.save(org_id, component, request_context=ctx)

        assert result.api_name == "TestClass"


class TestSaveBatch:
    """Verify batch save operations."""

    async def test_saves_multiple_components(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)
        org_id = uuid.uuid4()
        components = [
            _make_component(type="ApexClass", api_name="Class1"),
            _make_component(type="ApexClass", api_name="Class2"),
        ]

        results = await repo.save_batch(org_id, components)

        assert len(results) == 2
        assert results[0].api_name == "Class1"
        assert results[1].api_name == "Class2"
        # Single flush for the whole batch, not one per component.
        session.add_all.assert_called_once()
        session.flush.assert_awaited_once()

    async def test_save_batch_raises_for_unsupported_type(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)
        org_id = uuid.uuid4()
        components = [
            _make_component(type="ApexClass", api_name="Class1"),
            _make_component(type="UnknownType", api_name="Bad"),
        ]

        with pytest.raises(ValueError, match="Unsupported metadata type"):
            await repo.save_batch(org_id, components)


class TestUpdate:
    """Verify update operations."""

    async def test_update_existing_component(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)

        # Mock the execute to return an existing instance
        mock_result = MagicMock()
        mock_instance = MagicMock()
        mock_instance.api_name = "OldClass"
        mock_instance.label = "Old Label"
        mock_instance.namespace = None
        mock_instance.description = None
        mock_instance.fingerprint = ""
        mock_instance.metadata_properties = {}
        mock_instance.created_at = datetime.now(timezone.utc)
        mock_instance.updated_at = datetime.now(timezone.utc)
        mock_result.scalar_one_or_none.return_value = mock_instance
        session.execute.return_value = mock_result

        org_id = uuid.uuid4()
        component = _make_component(type="ApexClass", api_name="OldClass", label="New Label")

        result = await repo.update(org_id, component)

        assert result.label == "New Label"
        session.flush.assert_awaited_once()

    async def test_update_nonexistent_raises(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        org_id = uuid.uuid4()
        component = _make_component(type="ApexClass", api_name="NonExistent")

        with pytest.raises(ValueError, match="Component not found"):
            await repo.update(org_id, component)


class TestDelete:
    """Verify delete operations."""

    async def test_delete_existing_component(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)

        mock_result = MagicMock()
        mock_instance = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_instance
        session.execute.return_value = mock_result

        org_id = uuid.uuid4()
        result = await repo.delete(org_id, "TestClass")

        assert result is True
        # delete() iterates all 13 ORM models; the mock instance matches every
        # query, so delete is invoked for each model.
        assert session.delete.called
        assert session.delete.call_count >= 1
        session.flush.assert_awaited_once()

    async def test_delete_nonexistent_returns_false(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        org_id = uuid.uuid4()
        result = await repo.delete(org_id, "NonExistent")

        assert result is False


class TestGetById:
    """Verify get_by_id operations."""

    async def test_finds_by_uuid(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)

        mock_result = MagicMock()
        mock_instance = MagicMock()
        mock_instance.id = uuid.uuid4()
        mock_instance.organization_id = uuid.uuid4()
        mock_instance.api_name = "TestClass"
        mock_instance.label = "Test Class"
        mock_instance.namespace = None
        mock_instance.description = None
        mock_instance.fingerprint = ""
        mock_instance.metadata_properties = {}
        mock_instance.created_at = datetime.now(timezone.utc)
        mock_instance.updated_at = datetime.now(timezone.utc)
        mock_result.scalar_one_or_none.return_value = mock_instance
        session.execute.return_value = mock_result

        org_id = uuid.uuid4()
        result = await repo.get_by_id(org_id, str(mock_instance.id))

        assert result is not None
        assert result.api_name == "TestClass"

    async def test_returns_none_for_missing(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        org_id = uuid.uuid4()
        result = await repo.get_by_id(org_id, str(uuid.uuid4()))

        assert result is None


class TestGetByApiName:
    """Verify get_by_api_name operations."""

    async def test_finds_by_api_name(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)

        mock_result = MagicMock()
        mock_instance = MagicMock()
        mock_instance.id = uuid.uuid4()
        mock_instance.organization_id = uuid.uuid4()
        mock_instance.api_name = "MyClass"
        mock_instance.label = "My Class"
        mock_instance.namespace = None
        mock_instance.description = None
        mock_instance.fingerprint = ""
        mock_instance.metadata_properties = {}
        mock_instance.created_at = datetime.now(timezone.utc)
        mock_instance.updated_at = datetime.now(timezone.utc)
        mock_result.scalar_one_or_none.return_value = mock_instance
        session.execute.return_value = mock_result

        org_id = uuid.uuid4()
        result = await repo.get_by_api_name(org_id, "MyClass")

        assert result is not None
        assert result.api_name == "MyClass"

    async def test_returns_none_for_missing(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        org_id = uuid.uuid4()
        result = await repo.get_by_api_name(org_id, "NonExistent")

        assert result is None


class TestGetByType:
    """Verify get_by_type operations."""

    async def test_returns_components_for_type(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)

        # scalars().all() is called synchronously, so MagicMock (not AsyncMock)
        mock_result = MagicMock()
        mock_instances = []
        for i in range(3):
            inst = MagicMock()
            inst.id = uuid.uuid4()
            inst.organization_id = uuid.uuid4()
            inst.api_name = f"Class{i}"
            inst.label = f"Class {i}"
            inst.namespace = None
            inst.description = None
            inst.fingerprint = ""
            inst.metadata_properties = {}
            inst.created_at = datetime.now(timezone.utc)
            inst.updated_at = datetime.now(timezone.utc)
            mock_instances.append(inst)
        mock_result.scalars.return_value.all.return_value = mock_instances
        session.execute.return_value = mock_result

        org_id = uuid.uuid4()
        results = await repo.get_by_type(org_id, "ApexClass")

        assert len(results) == 3
        assert results[0].api_name == "Class0"

    async def test_returns_empty_for_unsupported_type(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)

        org_id = uuid.uuid4()
        results = await repo.get_by_type(org_id, "UnknownType")

        assert results == []

    async def test_respects_pagination(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)

        mock_result = MagicMock()
        mock_instance = MagicMock()
        mock_instance.id = uuid.uuid4()
        mock_instance.organization_id = uuid.uuid4()
        mock_instance.api_name = "Class0"
        mock_instance.label = "Class 0"
        mock_instance.namespace = None
        mock_instance.description = None
        mock_instance.fingerprint = ""
        mock_instance.metadata_properties = {}
        mock_instance.created_at = datetime.now(timezone.utc)
        mock_instance.updated_at = datetime.now(timezone.utc)
        mock_result.scalars.return_value.all.return_value = [mock_instance]
        session.execute.return_value = mock_result

        org_id = uuid.uuid4()
        results = await repo.get_by_type(
            org_id, "ApexClass",
            pagination=Pagination(limit=10, offset=0),
        )

        assert len(results) == 1


class TestCountByOrganization:
    """Verify count operations."""

    async def test_counts_all_types(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)

        # scalar_one() is called synchronously, so MagicMock (not AsyncMock)
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 5
        session.execute.return_value = mock_result

        org_id = uuid.uuid4()
        total = await repo.count_by_organization(org_id)

        assert total > 0


class TestGetTypes:
    """Verify get_types operations."""

    async def test_returns_non_empty_types(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)

        mock_result = MagicMock()
        # Return 0 for all types to simulate empty database
        mock_result.scalar_one.return_value = 0
        session.execute.return_value = mock_result

        org_id = uuid.uuid4()
        types = await repo.get_types(org_id)

        assert isinstance(types, list)


class TestInterfaceConformance:
    """Verify SQLAlchemyMetadataRepository implements IMetadataRepository."""

    def test_implements_interface(self) -> None:
        """Verify the repository implements all required methods."""
        from sfir_backend.domain.repositories.metadata_repo import IMetadataRepository

        repo_methods = {
            name for name in dir(SQLAlchemyMetadataRepository)
            if not name.startswith("_")
        }
        interface_methods = {
            name for name in dir(IMetadataRepository)
            if not name.startswith("_") and not name.startswith("class")
        }

        # All interface methods should be implemented
        for method in interface_methods:
            assert method in repo_methods, f"Missing method: {method}"

    def test_interface_covers_required_capabilities(self) -> None:
        """Verify the interface exposes all Phase 3.3 required capabilities."""
        from sfir_backend.domain.repositories.metadata_repo import IMetadataRepository

        required = {
            "save",
            "save_batch",
            "update",
            "delete",
            "get_by_id",
            "get_by_api_name",
            "get_by_api_names",  # bulk loading
            "get_by_type",
            "get_by_organization",
            "get_by_namespace",
            "search",
            "get_relationships",
            "get_dependencies",
            "get_versions",  # version lookup
            "get_latest_version",  # version lookup
            "list_versions_by_organization",  # bulk version load
            "save_version",  # single version write
            "save_versions",  # bulk version write
            "count_by_organization",
            "get_types",
        }
        interface_methods = {
            name for name in dir(IMetadataRepository)
            if not name.startswith("_") and not name.startswith("class")
        }
        assert required.issubset(interface_methods)


class TestPaginationClass:
    """Verify Pagination value object."""

    def test_default_values(self) -> None:
        p = Pagination()
        assert p.limit == 100
        assert p.offset == 0

    def test_enforces_max_limit(self) -> None:
        p = Pagination(limit=2000)
        assert p.limit == 1000

    def test_enforces_min_limit(self) -> None:
        p = Pagination(limit=0)
        assert p.limit == 1

    def test_enforces_min_offset(self) -> None:
        p = Pagination(offset=-1)
        assert p.offset == 0


class TestSortOrderClass:
    """Verify SortOrder value object."""

    def test_default_values(self) -> None:
        s = SortOrder()
        assert s.field == "api_name"
        assert s.descending is False

    def test_ascending_sort(self) -> None:
        s = SortOrder(field="label", descending=False)
        assert s.field == "label"
        assert s.descending is False

    def test_descending_sort(self) -> None:
        s = SortOrder(field="created_at", descending=True)
        assert s.field == "created_at"
        assert s.descending is True


class TestMetadataFilterClass:
    """Verify MetadataFilter value object."""

    def test_default_values(self) -> None:
        f = MetadataFilter()
        assert f.types is None
        assert f.search_text is None

    def test_with_types(self) -> None:
        f = MetadataFilter(types=["ApexClass", "Flow"])
        assert f.types == ["ApexClass", "Flow"]

    def test_with_search_text(self) -> None:
        f = MetadataFilter(search_text="Account")
        assert f.search_text == "Account"

    def test_with_namespaces(self) -> None:
        f = MetadataFilter(namespaces=["ns1", "ns2"])
        assert f.namespaces == ["ns1", "ns2"]


class TestGetByApiNames:
    """Verify bulk loading by API names avoids N+1."""

    async def test_returns_matching_components(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)

        inst = MagicMock()
        inst.id = uuid.uuid4()
        inst.organization_id = uuid.uuid4()
        inst.api_name = "MyClass"
        inst.label = "My Class"
        inst.namespace = None
        inst.description = None
        inst.fingerprint = ""
        inst.metadata_properties = {}
        inst.created_at = datetime.now(timezone.utc)
        inst.updated_at = datetime.now(timezone.utc)

        # First type query returns the instance; the rest return nothing.
        hit = MagicMock()
        hit.scalars.return_value.all.return_value = [inst]
        empty = MagicMock()
        empty.scalars.return_value.all.return_value = []
        n_queryable = sum(
            1 for m in _TYPE_TO_ORM_MODEL.values() if hasattr(m, "api_name")
        )
        session.execute.side_effect = [hit] + [empty] * n_queryable

        org_id = uuid.uuid4()
        results = await repo.get_by_api_names(org_id, ["MyClass", "Other"])

        assert len(results) == 1
        assert results[0].api_name == "MyClass"
        # Bounded: one query per queryable type, not one per api_name (avoids N+1).
        assert session.execute.call_count == n_queryable

    async def test_returns_empty_for_no_names(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)
        org_id = uuid.uuid4()

        results = await repo.get_by_api_names(org_id, [])

        assert results == []
        session.execute.assert_not_called()

    async def test_verifies_tenant(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)
        org_id = uuid.uuid4()
        wrong_ctx = _make_request_context(org_id=uuid.uuid4())

        with pytest.raises(PermissionError, match="does not match"):
            await repo.get_by_api_names(org_id, ["A"], request_context=wrong_ctx)


class TestDelete:
    """Verify delete semantics."""

    async def test_relationship_cleanup_is_scoped_to_org(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)
        org_id = uuid.uuid4()

        hit = MagicMock()
        hit.scalar_one_or_none.return_value = MagicMock()
        empty = MagicMock()
        empty.scalar_one_or_none.return_value = None
        n_queryable = sum(
            1 for m in _TYPE_TO_ORM_MODEL.values() if hasattr(m, "api_name")
        )
        session.execute.side_effect = [hit] + [empty] * (n_queryable - 1) + [empty]

        await repo.delete(org_id, "Account")

        cleanup_stmt = session.execute.call_args_list[-1][0][0]
        compiled = str(cleanup_stmt)
        assert "metadata_relationships.organization_id" in compiled
        assert "metadata_relationships.source_api_name" in compiled
        assert "metadata_relationships.target_api_name" in compiled


class TestGetVersions:
    """Verify version history lookup."""

    def _make_version_orm(self, version_number: int) -> MagicMock:
        m = MagicMock()
        m.id = uuid.uuid4()
        m.organization_id = uuid.uuid4()
        m.sync_job_id = uuid.uuid4()
        m.component_type = "ApexClass"
        m.component_name = "MyClass"
        m.component_id = str(uuid.uuid4())
        m.hash = f"hash{version_number}"
        m.version_number = version_number
        m.action = "created"
        m.payload = {"key": "value"}
        m.salesforce_last_modified = None
        m.sync_timestamp = datetime.now(timezone.utc)
        m.change_source = "sync"
        m.created_at = datetime.now(timezone.utc)
        return m

    async def test_returns_versions_newest_first(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            self._make_version_orm(2),
            self._make_version_orm(1),
        ]
        session.execute.return_value = mock_result

        org_id = uuid.uuid4()
        versions = await repo.get_versions(org_id, "MyClass")

        assert len(versions) == 2
        assert versions[0].version_number == 2
        assert versions[1].version_number == 1
        assert versions[0].component_name == "MyClass"
        assert versions[0].action.value == "created"

    async def test_respects_pagination(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            self._make_version_orm(3),
        ]
        session.execute.return_value = mock_result

        org_id = uuid.uuid4()
        versions = await repo.get_versions(
            org_id, "MyClass", pagination=Pagination(limit=1, offset=0),
        )

        assert len(versions) == 1
        assert versions[0].version_number == 3

    async def test_verifies_tenant(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)
        org_id = uuid.uuid4()
        wrong_ctx = _make_request_context(org_id=uuid.uuid4())

        with pytest.raises(PermissionError, match="does not match"):
            await repo.get_versions(org_id, "MyClass", request_context=wrong_ctx)


class TestGetLatestVersion:
    """Verify latest version lookup."""

    async def test_returns_latest_version(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)

        mock_orm = MagicMock()
        mock_orm.id = uuid.uuid4()
        mock_orm.organization_id = uuid.uuid4()
        mock_orm.sync_job_id = uuid.uuid4()
        mock_orm.component_type = "ApexClass"
        mock_orm.component_name = "MyClass"
        mock_orm.component_id = str(uuid.uuid4())
        mock_orm.hash = "hash5"
        mock_orm.version_number = 5
        mock_orm.action = "updated"
        mock_orm.payload = None
        mock_orm.salesforce_last_modified = None
        mock_orm.sync_timestamp = datetime.now(timezone.utc)
        mock_orm.change_source = "sync"
        mock_orm.created_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_orm
        session.execute.return_value = mock_result

        org_id = uuid.uuid4()
        version = await repo.get_latest_version(org_id, "MyClass")

        assert version is not None
        assert version.version_number == 5
        assert version.component_name == "MyClass"

    async def test_returns_none_when_missing(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        org_id = uuid.uuid4()
        version = await repo.get_latest_version(org_id, "Missing")

        assert version is None

    async def test_verifies_tenant(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)
        org_id = uuid.uuid4()
        wrong_ctx = _make_request_context(org_id=uuid.uuid4())

        with pytest.raises(PermissionError, match="does not match"):
            await repo.get_latest_version(org_id, "MyClass", request_context=wrong_ctx)


class TestListVersionsByOrganization:
    """Verify bulk version loading used for change detection."""

    def _make_version_orm(self, component_name: str, version_number: int) -> MagicMock:
        m = MagicMock()
        m.id = uuid.uuid4()
        m.organization_id = uuid.uuid4()
        m.sync_job_id = uuid.uuid4()
        m.component_type = "ApexClass"
        m.component_name = component_name
        m.component_id = str(uuid.uuid4())
        m.hash = f"hash-{component_name}-{version_number}"
        m.version_number = version_number
        m.action = "updated" if version_number > 1 else "created"
        m.payload = {"fingerprint": f"fp-{component_name}-{version_number}"}
        m.salesforce_last_modified = None
        m.sync_timestamp = datetime.now(timezone.utc)
        m.change_source = "sync"
        m.created_at = datetime.now(timezone.utc)
        return m

    async def test_returns_all_versions_for_org(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            self._make_version_orm("A", 1),
            self._make_version_orm("A", 2),
            self._make_version_orm("B", 1),
        ]
        session.execute.return_value = mock_result

        org_id = uuid.uuid4()
        versions = await repo.list_versions_by_organization(org_id, limit=100000)

        assert len(versions) == 3
        # Fingerprint payload preserved for change detection.
        assert versions[0].payload["fingerprint"] == "fp-A-1"
        assert versions[0].action.value == "created"
        assert versions[1].action.value == "updated"

    async def test_respects_limit(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            self._make_version_orm("A", 1),
        ]
        session.execute.return_value = mock_result

        org_id = uuid.uuid4()
        versions = await repo.list_versions_by_organization(org_id, limit=1)

        assert len(versions) == 1

    async def test_verifies_tenant(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)
        org_id = uuid.uuid4()
        wrong_ctx = _make_request_context(org_id=uuid.uuid4())

        with pytest.raises(PermissionError, match="does not match"):
            await repo.list_versions_by_organization(
                org_id, request_context=wrong_ctx,
            )


class TestSaveVersions:
    """Verify bulk version writes use a single flush."""

    def _make_version(self, name: str = "MyClass", version_number: int = 1) -> MagicMock:
        from sfir_backend.domain.entities.metadata_sync import MetadataVersion
        from sfir_backend.domain.value_objects.metadata import MetadataAction
        return MetadataVersion.create(
            organization_id=uuid.uuid4(),
            sync_job_id=uuid.uuid4(),
            component_type="ApexClass",
            component_name=name,
            component_id=str(uuid.uuid4()),
            hash=f"hash-{name}",
            version_number=version_number,
            action=(
                MetadataAction.UPDATED if version_number > 1 else MetadataAction.CREATED
            ),
            payload={"api_name": name, "fingerprint": f"fp-{name}"},
            change_source="sync",
        )

    async def test_save_versions_flushes_once(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)
        org_id = uuid.uuid4()

        versions = [
            self._make_version("A", 1),
            self._make_version("B", 1),
        ]
        saved = await repo.save_versions(org_id, versions)

        assert len(saved) == 2
        session.add_all.assert_called_once()
        session.flush.assert_awaited_once()

    async def test_save_versions_empty_is_noop(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)
        org_id = uuid.uuid4()

        saved = await repo.save_versions(org_id, [])

        assert saved == []
        session.add_all.assert_not_called()
        session.flush.assert_not_called()

    async def test_save_version_single(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)
        org_id = uuid.uuid4()

        version = self._make_version("MyClass", 1)
        saved = await repo.save_version(org_id, version)

        assert saved is not None
        session.add.assert_called_once()
        session.flush.assert_awaited_once()

    async def test_verifies_tenant(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)
        org_id = uuid.uuid4()
        wrong_ctx = _make_request_context(org_id=uuid.uuid4())

        with pytest.raises(PermissionError, match="does not match"):
            await repo.save_versions(org_id, [self._make_version()], request_context=wrong_ctx)


class TestRelationshipsBatch:
    """Verify get_relationships/get_dependencies batch-fetch (no N+1)."""

    async def test_get_relationships_batches_fetch(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)

        rel = MagicMock()
        rel.source_api_name = "Account"
        rel.target_api_name = "Contact"

        rel_result = MagicMock()
        rel_result.scalars.return_value.all.return_value = [rel]

        inst = MagicMock()
        inst.id = uuid.uuid4()
        inst.organization_id = uuid.uuid4()
        inst.api_name = "Contact"
        inst.label = "Contact"
        inst.namespace = None
        inst.description = None
        inst.fingerprint = ""
        inst.metadata_properties = {}
        inst.created_at = datetime.now(timezone.utc)
        inst.updated_at = datetime.now(timezone.utc)

        hit = MagicMock()
        hit.scalars.return_value.all.return_value = [inst]
        empty = MagicMock()
        empty.scalars.return_value.all.return_value = []
        n_queryable = sum(
            1 for m in _TYPE_TO_ORM_MODEL.values() if hasattr(m, "api_name")
        )
        # 1 relationship query + bounded per-type batch queries.
        session.execute.side_effect = [rel_result, hit] + [empty] * n_queryable

        org_id = uuid.uuid4()
        results = await repo.get_relationships(org_id, "Account")

        assert len(results) == 1
        assert results[0].api_name == "Contact"
        # 1 (relationship) + queryable types — bounded, independent of rel count.
        assert session.execute.call_count == 1 + n_queryable

    async def test_get_relationships_empty_when_no_rels(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)

        rel_result = MagicMock()
        rel_result.scalars.return_value.all.return_value = []
        session.execute.return_value = rel_result

        org_id = uuid.uuid4()
        results = await repo.get_relationships(org_id, "Account")

        assert results == []
        session.execute.assert_called_once()

    async def test_get_dependencies_batches_fetch(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session)

        dep = MagicMock()
        dep.source_api_name = "Account"
        dep.target_api_name = "Opportunity"

        dep_result = MagicMock()
        dep_result.scalars.return_value.all.return_value = [dep]

        inst = MagicMock()
        inst.id = uuid.uuid4()
        inst.organization_id = uuid.uuid4()
        inst.api_name = "Opportunity"
        inst.label = "Opportunity"
        inst.namespace = None
        inst.description = None
        inst.fingerprint = ""
        inst.metadata_properties = {}
        inst.created_at = datetime.now(timezone.utc)
        inst.updated_at = datetime.now(timezone.utc)

        hit = MagicMock()
        hit.scalars.return_value.all.return_value = [inst]
        empty = MagicMock()
        empty.scalars.return_value.all.return_value = []
        n_queryable = sum(
            1 for m in _TYPE_TO_ORM_MODEL.values() if hasattr(m, "api_name")
        )
        session.execute.side_effect = [dep_result, hit] + [empty] * n_queryable

        org_id = uuid.uuid4()
        results = await repo.get_dependencies(org_id, "Account")

        assert len(results) == 1
        assert results[0].api_name == "Opportunity"
        assert session.execute.call_count == 1 + n_queryable
