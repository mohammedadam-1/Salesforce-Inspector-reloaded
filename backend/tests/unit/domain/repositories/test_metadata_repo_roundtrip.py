"""Round-trip tests for the Metadata Repository conversion functions.

Phase 3.6 — Repository Contract:
    Given: entity, When: save(entity), Then: loaded = get(entity.id).
    loaded == entity.  Not approximately.  Exactly.  Every property.  Every
    metadata field.  Every relationship.  Every type-specific attribute.

These tests exercise the two pure conversion functions
(``_component_to_orm`` -> ``_orm_to_component``) plus real ORM model
construction for EVERY canonical entity type, proving the write/read paths
are symmetric and lossless (excluding repository-assigned volatile identity
fields: ``id``, ``organization_id``, ``created_at``, ``updated_at``).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

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
from sfir_backend.infrastructure.persistence.repositories.metadata_repo import (
    SQLAlchemyMetadataRepository,
    _RESERVED_RELATIONSHIPS,
    _RESERVED_TYPED,
    _TYPE_TO_CANONICAL_CLASS,
    _TYPE_TO_ORM_MODEL,
    _component_to_orm,
    _orm_to_component,
)

# Volatile identity fields assigned by the repository, not by the client.
VOLATILE_FIELDS = {"id", "organization_id", "created_at", "updated_at"}

# Types whose ORM model has NEITHER a namespace NOR a description column.
# Writing these used to raise TypeError (Critical Issue 1).
NO_NAMESPACE_NO_DESCRIPTION = {
    "Field", "RecordType", "Layout", "Profile", "PermissionSet",
}

# Types whose ORM model has a description column but NO namespace column.
NO_NAMESPACE_HAS_DESCRIPTION = {
    "ValidationRule", "Report", "Dashboard", "Workflow",
}

# The 27 entity types (Relationship is an edge, excluded).
ALL_ENTITY_TYPES = [t for t in _TYPE_TO_ORM_MODEL if t != "Relationship"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _typed_kwargs(metadata_type: str) -> dict:
    """Type-specific canonical fields (with non-trivial values) per type."""
    if metadata_type == "ApexClass":
        return {
            "api_version": 60,
            "body": "public class Foo { public void bar() {} }",
            "length": 1024,
            "package_versions": [{"majorVersion": 60, "minorVersion": 0}],
            "urls": ["https://example.com/Foo"],
        }
    if metadata_type == "Trigger":
        return {
            "object_api_name": "Account",
            "api_version": 61,
            "body": "trigger T on Account (after insert) {}",
            "trigger_events": ["afterInsert"],
            "usage_after_insert": True,
            "usage_before_update": True,
            "usage_is_bulk": True,
        }
    if metadata_type == "Object":
        return {
            "plural_label": "Accounts",
            "sharing_model": "ReadWrite",
            "deployment_status": "Deployed",
            "enable_activities": True,
            "enable_divisions": True,
            "enable_notes": True,
            "enable_history": True,
            "enable_streaming_api": True,
            "fields": [
                MetadataField(
                    api_name="F1",
                    label="F1",
                    object_api_name="Account",
                    field_type="text",
                    length=100,
                ),
            ],
            "field_sets": [{"fullName": "FS1"}],
            "validation_rules": [{"fullName": "VR1"}],
            "record_types": [{"fullName": "RT1"}],
            "indexes": [{"fullName": "I1"}],
            "business_processes": [{"fullName": "BP1"}],
            "compact_layouts": [{"fullName": "CL1"}],
            "list_views": [{"fullName": "LV1"}],
            "web_links": [{"fullName": "WL1"}],
        }
    if metadata_type == "Field":
        return {
            "object_api_name": "Account",
            "field_type": "text",
            "length": 255,
            "precision": 18,
            "scale": 2,
            "required": True,
            "external_id": True,
            "default_value": "abc",
            "picklist_values": [{"value": "a", "label": "A"}],
            "relationship_name": "Account",
            "reference_to": "Contact",
            "cascade_delete": True,
            "formula": "CONCAT(a, b)",
            "formula_treat_blanks_as": "BlankAsBlank",
            "help_text": "Help me",
            "business_owner_group": "grp",
            "business_owner_user": "usr",
            "compliance": True,
            "tracked_history": True,
            "track_feed_history": True,
        }
    if metadata_type == "ValidationRule":
        return {
            "object_api_name": "Account",
            "active": True,
            "error_message": "Must be valid",
            "error_display_field": "Name",
            "formula": "NOT(1=1)",
        }
    if metadata_type == "RecordType":
        return {
            "object_api_name": "Account",
            "active": True,
            "business_process": "BP",
            "compact_layout_assignment": "CL",
            "picklist_values": [{"value": "x"}],
        }
    if metadata_type == "Flow":
        return {
            "process_type": "Flow",
            "flow_status": MetadataStatus.DRAFT,
            "version_number": 1,
            "api_version": 60,
            "interview_label": "IL",
            "run_in_mode": "SystemModeWithoutSharing",
            "variables": [{"name": "v1"}],
            "stages": [{"name": "s1"}],
            "elements": [{"name": "e1"}],
            "record_creates": ["Account"],
            "record_updates": ["Contact"],
            "record_deletes": ["Lead"],
            "subflows": ["SubFlow"],
            "versions": [
                MetadataFlowVersion(
                    api_name="F-1",
                    flow_api_name="F",
                    version_number=1,
                    definition={"x": 1},
                ),
            ],
        }
    if metadata_type == "FlowVersion":
        return {
            "flow_api_name": "F",
            "version_number": 2,
            "definition": {"nodes": [{"name": "n1"}]},
        }
    if metadata_type == "Layout":
        return {
            "object_api_name": "Account",
            "layout_type": "Standard",
            "sections": [{"name": "s1"}],
            "related_lists": [{"name": "rl1"}],
            "mini_layout": {"name": "ml"},
            "quick_actions": [{"name": "qa1"}],
            "summary_layout": {"name": "sl"},
            "headings": [{"name": "h1"}],
        }
    if metadata_type == "Profile":
        return {
            "user_license": "Salesforce",
            "custom": True,
            "object_permissions": [{"name": "Account"}],
            "field_permissions": [{"name": "F1"}],
            "class_permissions": [{"name": "C1"}],
            "page_permissions": [{"name": "P1"}],
            "user_permissions": [{"name": "U1"}],
            "record_type_visibilities": [{"name": "RT1"}],
            "login_hours": {"monday": "1"},
            "login_ip_ranges": [{"start": "1.1.1.1"}],
            "setup_sections": [{"name": "s1"}],
        }
    if metadata_type == "PermissionSet":
        return {
            "user_license": "Salesforce",
            "is_owned_by_profile": True,
            "profile_name": "Admin",
            "has_activation": True,
            "object_permissions": [{"name": "Account"}],
            "field_permissions": [{"name": "F1"}],
            "class_permissions": [{"name": "C1"}],
            "page_permissions": [{"name": "P1"}],
            "user_permissions": [{"name": "U1"}],
            "record_type_visibilities": [{"name": "RT1"}],
            "login_hours": {"monday": "1"},
            "login_ip_ranges": [{"start": "1.1.1.1"}],
            "setup_sections": [{"name": "s1"}],
        }
    if metadata_type == "Report":
        return {
            "object_api_name": "Account",
            "report_type": "Tabular",
            "report_format": "tabular",
            "folder_name": "folder1",
            "params": {"scope": "mine"},
            "columns": [{"name": "c1"}],
            "filters": [{"name": "f1"}],
            "groupings": [{"name": "g1"}],
        }
    if metadata_type == "Dashboard":
        return {
            "folder_name": "folder1",
            "background_fitness": "Blur",
            "dashboard_type": "Specified",
            "dashboard_result": "d1",
            "components": [{"name": "c1"}],
            "left_section": [{"name": "l1"}],
            "middle_section": [{"name": "m1"}],
            "right_section": [{"name": "r1"}],
        }
    if metadata_type == "Workflow":
        return {
            "object_api_name": "Account",
            "active": True,
            "formula_criteria": "TRUE",
            "evaluation_criteria": "Everytime",
            "triggered_type": "onCreateOnly",
            "actions": [{"name": "a1"}],
        }
    if metadata_type == "Role":
        return {
            "parent_role": "CEO",
            "case_access_level": "Read",
            "contact_access_level": "Read",
            "opportunity_access_level": "Edit",
            "account_access_level": "Read",
            "may_forecast_manager": True,
        }
    if metadata_type == "Queue":
        return {
            "email": "q@example.com",
            "queue_sobjects": [{"sobject": "Account"}],
            "queue_members": [{"name": "u1"}],
            "queue_rules": [{"name": "r1"}],
        }
    if metadata_type == "PublicGroup":
        return {"members": [{"name": "m1"}]}
    if metadata_type == "SharingRule":
        return {
            "object_api_name": "Account",
            "shared_to": "Group1",
            "shared_from": "Owner1",
            "access_level": "Read",
            "rule_type": "CriteriaBased",
        }
    if metadata_type == "GlobalValueSet":
        return {
            "master_label": "ML1",
            "custom_value": [{"value": "v1"}],
            "grouped": True,
            "sorting_order": "Custom",
            "value_settings": [{"name": "vs1"}],
        }
    if metadata_type == "CustomMetadata":
        return {"visibility": "Protected", "fields": [{"name": "f1"}]}
    if metadata_type == "CustomSetting":
        return {
            "setting_type": "List",
            "visibility": "Protected",
            "fields": [{"name": "f1"}],
        }
    if metadata_type == "EmailTemplate":
        return {
            "template_type": "Text",
            "object_type": "Account",
            "available": True,
            "content": "Hello",
            "subject": "Subj",
            "encoding": "UTF-8",
            "style": "None",
            "ui_type": "Aloha",
        }
    if metadata_type == "NamedCredential":
        return {
            "endpoint": "https://api.example.com",
            "principal_type": "NamedUser",
            "protocol": "NoAuthentication",
            "auth_provider": None,
            "generate_authorization_header": False,
            "allow_merge_fields_in_header": True,
            "allow_merge_fields_in_body": False,
            "outbound_network_connection": None,
        }
    if metadata_type == "ConnectedApp":
        return {
            "version": "1.0",
            "contact_email": "a@b.c",
            "contact_phone": "123",
            "icon_url": "i",
            "info_url": "i",
            "logo_url": "l",
            "mobile_app": None,
            "mobile_start_url": None,
            "oauth_config": {"scopes": ["full"]},
            "permissions": [{"name": "p1"}],
            "permissions_enabled": [{"name": "p1"}],
            "plugin": None,
            "plugin_execution_user": None,
            "start_url": "s",
        }
    if metadata_type == "LightningPage":
        return {
            "master_label": "ML1",
            "page_type": "AppPage",
            "template": "flexipage",
            "regions": [{"name": "r1"}],
        }
    if metadata_type == "QuickAction":
        return {
            "object_api_name": "Account",
            "action_type": "Create",
            "target_object": "Account",
            "target_record_type": "RT",
            "target_field_list": "f1",
            "height": 1,
            "width": 2,
            "icon": "i1",
            "options_create": True,
            "options_edit": True,
            "options_event": False,
        }
    if metadata_type == "Formula":
        return {
            "object_api_name": "Account",
            "field_api_name": "F1",
            "formula_expression": "X",
            "formula_type": "text",
            "formula_treat_blanks_as": "BlankAsBlank",
            "return_type": "Text",
        }
    if metadata_type == "ApprovalProcess":
        return {
            "object_api_name": "Account",
            "active": True,
            "record_editability": "Editable",
            "allow_sequential": True,
            "show_approval_related_lists": True,
            "entry_criteria": "TRUE",
            "final_approval_field_lookup": "F1",
            "final_rejection_field_lookup": "R1",
            "steps": [{"name": "s1"}],
        }
    return {}


def _build_component(
    metadata_type: str,
    *,
    api_name: str | None = None,
    metadata_properties: dict | None = None,
    relationships: list[CanonicalRelationship] | None = None,
) -> MetadataComponent:
    """Build a fully-populated typed canonical component."""
    cls = _TYPE_TO_CANONICAL_CLASS[metadata_type]
    component = cls(
        type=metadata_type,
        api_name=api_name or f"RT_{metadata_type}",
        label=f"Round Trip {metadata_type}",
        description="Round trip description",
        namespace="ns1" if metadata_type not in NO_NAMESPACE_NO_DESCRIPTION else None,
        hash="abc123hash",
        status=MetadataStatus.ACTIVE,
        source_platform=SourcePlatform.SALESFORCE,
        metadata_properties=dict(metadata_properties or {"custom": "v"}),
        created_at=_now(),
        updated_at=_now(),
        **_typed_kwargs(metadata_type),
    )
    component.relationships = relationships or []
    return component


def _roundtrip(component: MetadataComponent) -> MetadataComponent:
    """Write -> construct real ORM row -> read back."""
    model = _TYPE_TO_ORM_MODEL[component.type]
    values = _component_to_orm(
        uuid.uuid4(), component, model_class=model,
    )
    row = model(**values)
    return _orm_to_component(row, component.type)


def _assert_equivalent(original: MetadataComponent, loaded: MetadataComponent) -> None:
    """Assert exact equality, excluding repository-assigned volatile fields."""
    assert type(loaded).__name__ == type(original).__name__, (
        f"expected {type(original).__name__}, got {type(loaded).__name__}"
    )
    a = original.model_dump()
    b = loaded.model_dump()
    for key in VOLATILE_FIELDS:
        a.pop(key, None)
        b.pop(key, None)
    assert a == b, (
        f"round-trip mismatch for {original.type}: "
        f"expected={a!r} loaded={b!r}"
    )


class TestComponentToOrmSchemaAware:
    """Critical Issue 1: never emit columns the ORM model does not have."""

    @pytest.mark.parametrize("metadata_type", ALL_ENTITY_TYPES)
    def test_no_unsupported_columns_emitted(self, metadata_type: str) -> None:
        model = _TYPE_TO_ORM_MODEL[metadata_type]
        component = _build_component(metadata_type)
        values = _component_to_orm(uuid.uuid4(), component, model_class=model)
        for key in values:
            assert hasattr(model, key), (
                f"{metadata_type}: emitted non-column key {key!r}"
            )

    @pytest.mark.parametrize("metadata_type", sorted(NO_NAMESPACE_NO_DESCRIPTION))
    def test_no_crash_for_missing_namespace_and_description(self, metadata_type: str) -> None:
        """The 5 models with neither column must not raise TypeError."""
        component = _build_component(metadata_type)
        values = _component_to_orm(
            uuid.uuid4(), component, model_class=_TYPE_TO_ORM_MODEL[metadata_type],
        )
        assert "namespace" not in values
        assert "description" not in values

    @pytest.mark.parametrize("metadata_type", sorted(NO_NAMESPACE_HAS_DESCRIPTION))
    def test_no_crash_for_missing_namespace(self, metadata_type: str) -> None:
        """The 4 models with description but no namespace must not raise."""
        component = _build_component(metadata_type)
        values = _component_to_orm(
            uuid.uuid4(), component, model_class=_TYPE_TO_ORM_MODEL[metadata_type],
        )
        assert "namespace" not in values
        assert values["description"] == component.description

    def test_namespace_emitted_only_when_column_exists(self) -> None:
        apex = _build_component("ApexClass")  # has namespace column
        values = _component_to_orm(
            uuid.uuid4(), apex, model_class=_TYPE_TO_ORM_MODEL["ApexClass"],
        )
        assert values["namespace"] == "ns1"

    def test_two_arg_call_still_works(self) -> None:
        """Backward compatibility: 2-arg _component_to_orm resolves the model."""
        component = _build_component("Field")
        values = _component_to_orm(uuid.uuid4(), component)
        assert values["api_name"] == component.api_name
        assert values["fingerprint"] == component.hash
        assert isinstance(values["metadata_properties"], dict)


class TestOrmToComponentTyped:
    """Critical Issue 2: the read path returns the TYPED canonical model."""

    @pytest.mark.parametrize("metadata_type", ALL_ENTITY_TYPES)
    def test_returns_typed_model(self, metadata_type: str) -> None:
        loaded = _roundtrip(_build_component(metadata_type))
        assert type(loaded).__name__ == _TYPE_TO_CANONICAL_CLASS[metadata_type].__name__

    @pytest.mark.parametrize("metadata_type", ALL_ENTITY_TYPES)
    def test_type_is_pascal_case(self, metadata_type: str) -> None:
        loaded = _roundtrip(_build_component(metadata_type))
        assert loaded.type == metadata_type

    def test_restores_type_specific_columns(self) -> None:
        loaded = _roundtrip(_build_component("Field"))
        assert loaded.object_api_name == "Account"
        assert loaded.reference_to == "Contact"
        assert loaded.formula == "CONCAT(a, b)"
        assert loaded.length == 255

    def test_restores_stashed_non_column_fields(self) -> None:
        loaded = _roundtrip(_build_component("Object"))
        assert loaded.enable_activities is True
        assert len(loaded.fields) == 1
        assert loaded.fields[0].api_name == "F1"
        assert loaded.record_types == [{"fullName": "RT1"}]

    def test_reserved_keys_stripped_from_metadata_properties(self) -> None:
        component = _build_component("Field")
        loaded = _roundtrip(component)
        assert _RESERVED_TYPED not in loaded.metadata_properties
        assert _RESERVED_RELATIONSHIPS not in loaded.metadata_properties
        assert loaded.metadata_properties == component.metadata_properties

    def test_legacy_enum_casing_coerced(self) -> None:
        """Column values like 'Active'/'Draft' survive into lowercase enums."""
        apex = _build_component("ApexClass")
        values = _component_to_orm(
            uuid.uuid4(), apex, model_class=_TYPE_TO_ORM_MODEL["ApexClass"],
        )
        values["status"] = "Active"  # legacy capitalised DB value
        row = _TYPE_TO_ORM_MODEL["ApexClass"](**values)
        loaded = _orm_to_component(row, "ApexClass")
        assert loaded.status == MetadataStatus.ACTIVE


class TestExactRoundTrip:
    """The Repository Contract: loaded == entity, exactly, for every type."""

    @pytest.mark.parametrize("metadata_type", ALL_ENTITY_TYPES)
    def test_round_trip_is_exact(self, metadata_type: str) -> None:
        component = _build_component(metadata_type)
        loaded = _roundtrip(component)
        _assert_equivalent(component, loaded)

    @pytest.mark.parametrize("metadata_type", ALL_ENTITY_TYPES)
    def test_round_trip_preserves_metadata_properties(self, metadata_type: str) -> None:
        component = _build_component(metadata_type)
        loaded = _roundtrip(component)
        assert loaded.metadata_properties == component.metadata_properties

    @pytest.mark.parametrize("metadata_type", ALL_ENTITY_TYPES)
    def test_relationships_round_trip(self, metadata_type: str) -> None:
        rels = [
            CanonicalRelationship(
                type=RelationshipType.REFERENCES,
                target_type="Object",
                target_api_name="Account",
                target_label="Account",
                metadata={"note": "n1"},
            ),
        ]
        component = _build_component(metadata_type, relationships=rels)
        loaded = _roundtrip(component)
        assert len(loaded.relationships) == 1
        assert loaded.relationships[0].target_api_name == "Account"
        assert loaded.relationships[0].metadata == {"note": "n1"}
        _assert_equivalent(component, loaded)

    def test_flow_metadata_survives(self) -> None:
        component = _build_component("Flow")
        loaded = _roundtrip(component)
        assert loaded.record_creates == ["Account"]
        assert loaded.record_deletes == ["Lead"]
        assert loaded.flow_status == MetadataStatus.DRAFT
        assert len(loaded.versions) == 1
        assert loaded.versions[0].flow_api_name == "F"

    def test_report_and_dashboard_specifics_survive(self) -> None:
        report = _roundtrip(_build_component("Report"))
        assert report.object_api_name == "Account"
        assert report.report_format == "tabular"
        assert report.params == {"scope": "mine"}
        dashboard = _roundtrip(_build_component("Dashboard"))
        assert dashboard.background_fitness == "Blur"
        assert dashboard.left_section == [{"name": "l1"}]

    def test_workflow_specifics_survive(self) -> None:
        workflow = _roundtrip(_build_component("Workflow"))
        assert workflow.object_api_name == "Account"
        assert workflow.formula_criteria == "TRUE"
        assert workflow.evaluation_criteria == "Everytime"
        assert workflow.triggered_type == "onCreateOnly"

    def test_profile_setup_sections_survive(self) -> None:
        profile = _roundtrip(_build_component("Profile"))
        assert profile.setup_sections == [{"name": "s1"}]
        ps = _roundtrip(_build_component("PermissionSet"))
        assert ps.setup_sections == [{"name": "s1"}]


class TestPropertyBasedRoundTrip:
    """Optional-field combinations must not break the round-trip."""

    @pytest.mark.parametrize("formula", [None, "", "X", "IF(1=1, 'a', 'b')"])
    def test_field_formula_variants(self, formula: str | None) -> None:
        component = _build_component("Field")
        component.formula = formula
        _assert_equivalent(component, _roundtrip(component))

    @pytest.mark.parametrize("reference_to", [None, "", "Contact", "Account__c"])
    def test_field_reference_to_variants(self, reference_to: str | None) -> None:
        component = _build_component("Field")
        component.reference_to = reference_to
        _assert_equivalent(component, _roundtrip(component))

    @pytest.mark.parametrize("active", [True, False])
    def test_workflow_active_variants(self, active: bool) -> None:
        component = _build_component("Workflow")
        component.active = active
        _assert_equivalent(component, _roundtrip(component))

    @pytest.mark.parametrize("record_creates", [[], ["Account"], ["Account", "Contact"]])
    def test_flow_record_creates_variants(self, record_creates: list) -> None:
        component = _build_component("Flow")
        component.record_creates = list(record_creates)
        _assert_equivalent(component, _roundtrip(component))

    @pytest.mark.parametrize("namespace", [None, "ns1"])
    def test_namespace_variants_on_model_with_column(self, namespace: str | None) -> None:
        component = _build_component("ApexClass")
        component.namespace = namespace
        _assert_equivalent(component, _roundtrip(component))

    @pytest.mark.parametrize("length", [None, 0, 255])
    def test_field_length_variants(self, length: int | None) -> None:
        component = _build_component("Field")
        component.length = length
        _assert_equivalent(component, _roundtrip(component))

    def test_empty_relationships_round_trip(self) -> None:
        component = _build_component("Object")
        component.relationships = []
        _assert_equivalent(component, _roundtrip(component))


class TestBaseComponentWithTypedType:
    """Base ``MetadataComponent`` instances typed as Flow/Object (as produced
    by some callers and the validation engine integration tests) must not
    crash the write path and must preserve metadata_properties data."""

    @pytest.mark.parametrize("metadata_type", ["Flow", "Object", "Field", "Report"])
    def test_base_component_save_does_not_crash(self, metadata_type: str) -> None:
        component = MetadataComponent(
            type=metadata_type,
            api_name=f"Base_{metadata_type}",
            label="Base",
            description="Base component",
            hash="h",
            status=MetadataStatus.ACTIVE,
            source_platform=SourcePlatform.SALESFORCE,
            metadata_properties={"record_creates": [{"object": "Account"}]},
            created_at=_now(),
            updated_at=_now(),
        )
        model = _TYPE_TO_ORM_MODEL[metadata_type]
        values = _component_to_orm(uuid.uuid4(), component, model_class=model)
        row = model(**values)
        loaded = _orm_to_component(row, metadata_type)
        # Base-only data must survive.
        assert loaded.api_name == f"Base_{metadata_type}"
        assert loaded.description == "Base component"
        # Non-column metadata_properties data feeds type-specific columns where
        # the canonical schema accepts it, and is otherwise preserved verbatim
        # (this is what the validation engine's BROKEN_REFERENCE check relies on).
        assert loaded.metadata_properties["record_creates"] == [{"object": "Account"}]

    def test_base_flow_with_string_record_creates_returns_typed(self) -> None:
        component = MetadataComponent(
            type="Flow",
            api_name="Base_Flow",
            label="Base",
            description="Base flow",
            hash="h",
            status=MetadataStatus.ACTIVE,
            source_platform=SourcePlatform.SALESFORCE,
            metadata_properties={"record_creates": ["Account"]},
            created_at=_now(),
            updated_at=_now(),
        )
        values = _component_to_orm(
            uuid.uuid4(), component, model_class=_TYPE_TO_ORM_MODEL["Flow"],
        )
        row = _TYPE_TO_ORM_MODEL["Flow"](**values)
        loaded = _orm_to_component(row, "Flow")
        assert type(loaded).__name__ == "MetadataFlow"
        assert loaded.record_creates == ["Account"]

    def test_base_object_component_round_trips(self) -> None:
        component = MetadataComponent(
            type="Object",
            api_name="Account",
            label="Account",
            description="An account",
            hash="h",
            status=MetadataStatus.ACTIVE,
            source_platform=SourcePlatform.SALESFORCE,
            metadata_properties={
                "enable_activities": True,
                "fields": [{"api_name": "F1", "label": "F1", "field_type": "text"}],
            },
            created_at=_now(),
            updated_at=_now(),
        )
        model = _TYPE_TO_ORM_MODEL["Object"]
        values = _component_to_orm(uuid.uuid4(), component, model_class=model)
        row = model(**values)
        loaded = _orm_to_component(row, "Object")
        assert loaded.enable_activities is True
        assert loaded.fields[0].api_name == "F1"
        assert loaded.description == "An account"


class _FakeRepoForValidation:
    """Minimal IMetadataRepository stand-in returning pre-loaded components."""

    def __init__(self, components: list) -> None:
        self.components = components

    async def get_by_organization(
        self, organization_id, *, request_context=None,
    ) -> list:
        return self.components

    async def get_types(self, organization_id, *, request_context=None) -> list:
        return sorted({c.type for c in self.components})

    async def get_relationships(self, organization_id, api_name, *, request_context=None):
        return []

    async def get_dependencies(self, organization_id, api_name, *, request_context=None):
        return []


class TestValidationEngineFedByReadPath:
    """Phase 3.5 proved the read path dropped type-specific data, so the
    validation engine reported REFERENCE_DATA_MISSING. Phase 3.6's typed read
    path restores that data; the engine must now pass with zero such findings."""

    async def test_engine_passes_with_typed_read_path(self) -> None:
        from sfir_backend.application.use_cases.metadata.validation_engine import (
            MetadataValidationEngine,
        )

        org_id = uuid.uuid4()
        # A coherent org: the referenced object exists, the field's reference
        # target exists, so the engine sees no broken references.
        obj = _build_component("Object", api_name="Account")
        field = _build_component("Field", api_name="Account.Name")
        field.object_api_name = "Account"
        field.reference_to = None  # plain text field, no lookup target
        contact = _build_component("Object", api_name="Contact")
        apex = _build_component("ApexClass")

        # Load through the real write/read conversion (the production read path).
        loaded = [_roundtrip(obj), _roundtrip(field), _roundtrip(contact), _roundtrip(apex)]

        engine = MetadataValidationEngine(metadata_repo=_FakeRepoForValidation(loaded))
        report = await engine.validate(org_id)

        assert report.passed is True
        assert not report.integrity_failures
        assert not report.consistency_failures
        ref_missing = [
            f for f in report.findings if f.error_code == "REFERENCE_DATA_MISSING"
        ]
        assert ref_missing == []

    async def test_typed_read_path_restores_object_api_name_for_engine(self) -> None:
        """The exact Phase 3.5 regression: object_api_name must survive."""
        field = _build_component("Field")
        field.object_api_name = "Account"
        loaded = _roundtrip(field)
        # read_prop's typed-attribute fallback now finds the value.
        assert loaded.object_api_name == "Account"

    async def test_engine_detects_broken_reference_through_read_path(self) -> None:
        """BROKEN_REFERENCE detection must still work through the typed path."""
        from sfir_backend.application.use_cases.metadata.validation_engine import (
            MetadataValidationEngine,
        )

        org_id = uuid.uuid4()
        # A flow whose record_creates references a non-existent object.
        flow = _build_component("Flow")
        flow.record_creates = ["GhostObject"]
        flow.metadata_properties["record_creates"] = ["GhostObject"]
        loaded = [_roundtrip(flow)]

        engine = MetadataValidationEngine(metadata_repo=_FakeRepoForValidation(loaded))
        report = await engine.validate(org_id)

        assert report.passed is False
        assert any(
            f.error_code == "BROKEN_REFERENCE"
            and f.reference_api_name == "GhostObject"
            for f in report.consistency_failures
        )


class TestSaveRelationshipGuards:
    """Relationship is an edge, not an entity."""
    async def test_save_relationship_raises_value_error(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session=session)
        org_id = uuid.uuid4()
        rel = MetadataComponent(
            type="Relationship",
            api_name="Account.Contact",
            label="Edge",
            hash="x",
            status=MetadataStatus.ACTIVE,
            source_platform=SourcePlatform.SALESFORCE,
            metadata_properties={},
        )
        with pytest.raises(ValueError, match="edges, not entities"):
            await repo.save(org_id, rel)

    async def test_save_batch_relationship_raises_value_error(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session=session)
        org_id = uuid.uuid4()
        rel = MetadataComponent(
            type="Relationship",
            api_name="A.B",
            label="Edge",
            hash="x",
            status=MetadataStatus.ACTIVE,
            source_platform=SourcePlatform.SALESFORCE,
            metadata_properties={},
        )
        with pytest.raises(ValueError, match="edges, not entities"):
            await repo.save_batch(org_id, [rel])


class TestRelationshipEdgeMirror:
    """Relationship edges are mirrored to the edge table for cross-component
    queries (get_relationships / get_dependencies)."""

    async def test_save_mirrors_relationships(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session=session)
        org_id = uuid.uuid4()
        component = _build_component(
            "Object",
            relationships=[
                CanonicalRelationship(
                    type=RelationshipType.REFERENCES,
                    target_type="Object",
                    target_api_name="Contact",
                    target_label="Contact",
                    metadata={"k": "v"},
                ),
            ],
        )
        await repo.save(org_id, component)

        # One edge-row add for the relationship mirror.
        edge_adds = [
            c for c in session.add.call_args_list
            if "MetadataRelationshipModel" in repr(c)
        ]
        assert len(edge_adds) == 1
        added: MagicMock = edge_adds[0][0][0]
        assert added.source_api_name == component.api_name
        assert added.target_api_name == "Contact"
        assert added.target_type == "Object"
        assert added.metadata_properties == {"k": "v"}

    async def test_save_without_relationships_does_not_touch_edge_table(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session=session)
        org_id = uuid.uuid4()
        component = _build_component("ApexClass")  # no relationships
        await repo.save(org_id, component)
        # single add + single flush, no extra flush for the edge mirror
        assert session.add.call_count == 1
        assert session.flush.await_count == 1

    async def test_save_with_relationships_flushes_twice(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        repo = SQLAlchemyMetadataRepository(session=session)
        org_id = uuid.uuid4()
        component = _build_component(
            "Object",
            relationships=[
                CanonicalRelationship(
                    type=RelationshipType.REFERENCES,
                    target_type="Object",
                    target_api_name="Contact",
                    target_label="Contact",
                ),
            ],
        )
        await repo.save(org_id, component)
        assert session.flush.await_count == 2
