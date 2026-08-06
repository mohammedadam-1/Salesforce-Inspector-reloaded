"""CanonicalRelationshipResolver tests.

Phase 5 Step 3 — Canonical Relationship Resolution:
    Given: canonical metadata components (or normalized dicts), When: the
    resolver runs, Then: typed, directional relationships are derived for
    every supported kind, references to unknown targets are counted as
    missing, and references to soft-deleted targets yield deleted rows.
"""

from __future__ import annotations

from sfir_backend.application.pipeline.normalizer.identity_service import (
    IdentityService,
)
from sfir_backend.application.pipeline.resolver.canonical_relationship_resolver import (
    CanonicalRelationshipResolver,
)
from sfir_backend.domain.canonical.base import FieldType, MetadataComponent
from sfir_backend.domain.canonical.code import MetadataTrigger
from sfir_backend.domain.canonical.core import MetadataField, MetadataObject
from sfir_backend.domain.canonical.custom import MetadataCustomMetadata
from sfir_backend.domain.canonical.flows import MetadataFlow
from sfir_backend.domain.canonical.layouts import MetadataLayout, MetadataRecordType
from sfir_backend.domain.canonical.permissions import MetadataPermissionSet
from sfir_backend.domain.canonical.validation import MetadataValidationRule
from sfir_backend.domain.entities.canonical_relationship import (
    CanonicalRelationshipType,
)

ORG_ID = "org-test-123"
PLATFORM = "salesforce"


def _ident(type_name: str, api_name: str) -> str:
    return IdentityService().compute_component_hash(
        organization_id=ORG_ID,
        source_platform=PLATFORM,
        type_name=type_name,
        api_name=api_name,
    )


def _component(
    cls: type,
    api_name: str,
    type_name: str,
    **overrides,
) -> MetadataComponent:
    return cls(
        id=_ident(type_name, api_name),
        api_name=api_name,
        type=type_name,
        organization_id=ORG_ID,
        **overrides,
    )


def _make_account() -> MetadataObject:
    return _component(
        MetadataObject, "Account", "object",
        fields=[
            MetadataField(
                id=_ident("field", "Account.MyField__c"),
                api_name="Account.MyField__c",
                object_api_name="Account",
                type="field",
                organization_id=ORG_ID,
            ),
        ],
        record_types=[{"name": "RT1"}],
        validation_rules=[{"name": "Rule1"}],
    )


def _make_field() -> MetadataField:
    return _component(
        MetadataField, "Account.MyField__c", "field",
        object_api_name="Account",
        field_type=FieldType.LOOKUP,
        reference_to="Contact",
        formula="TEXT(Price__c) + [Discount__c] + $Setup.Config__c.Max__c",
    )


def _make_trigger() -> MetadataTrigger:
    return _component(
        MetadataTrigger, "AccountTrigger", "trigger",
        object_api_name="Account",
        body=(
            "trigger AccountTrigger on Account (before insert) "
            "{ AccountService.handle(); new AuditHelper().run(); }"
        ),
    )


def _make_layout() -> MetadataLayout:
    return _component(MetadataLayout, "AccountLayout", "layout", object_api_name="Account")


def _make_record_type() -> MetadataRecordType:
    return _component(MetadataRecordType, "Account.RT1", "record_type", object_api_name="Account")


def _make_validation_rule() -> MetadataValidationRule:
    return _component(
        MetadataValidationRule, "Account.Rule1", "validation_rule", object_api_name="Account",
    )


def _make_flow() -> MetadataFlow:
    return _component(
        MetadataFlow, "MyFlow", "flow",
        record_creates=["Account"],
        subflows=["SubFlow"],
        elements=[
            {"element_type": "apex", "name": "FlowClass"},
            {"element_type": "actionCall", "name": "DoThing"},
            {"element_type": "subflow", "name": "SubFlow"},
        ],
    )


def _make_permission_set() -> MetadataPermissionSet:
    return _component(
        MetadataPermissionSet, "PS1", "permission_set",
        object_permissions=[{"object": "Account"}],
        field_permissions=[{"field": "Account.MyField__c"}],
        profile_name="Admin",
    )


def _make_custom_metadata() -> MetadataCustomMetadata:
    return _component(
        MetadataCustomMetadata, "Config.Alpha", "custom_metadata",
        fields=[{"type": "reference", "value": "Config.Beta"}],
    )


def _active_targets() -> set[str]:
    return {
        _ident("object", "Account"),
        _ident("object", "Contact"),
        _ident("field", "Account.MyField__c"),
        _ident("field", "Discount__c"),
        _ident("object", "Config__c"),
        _ident("trigger", "AccountTrigger"),
        _ident("apex_class", "AccountService"),
        _ident("layout", "AccountLayout"),
        _ident("record_type", "Account.RT1"),
        _ident("validation_rule", "Account.Rule1"),
        _ident("flow", "MyFlow"),
        _ident("flow", "SubFlow"),
        _ident("apex_class", "FlowClass"),
        _ident("permission_set", "PS1"),
        _ident("profile", "Admin"),
        _ident("custom_metadata", "Config.Alpha"),
        _ident("custom_metadata", "Config.Beta"),
    }


def _types(resolver_result) -> set[str]:
    return {r.relationship_type.value for r in resolver_result.relationships}


class TestComponentResolution:
    def test_object_containment_kinds(self) -> None:
        result = CanonicalRelationshipResolver().resolve(
            ORG_ID, [_make_account()], active_targets=_active_targets(),
        )
        kinds = _types(result)
        assert CanonicalRelationshipType.OBJECT_TO_FIELD in kinds
        assert CanonicalRelationshipType.OBJECT_TO_RECORD_TYPE in kinds
        assert CanonicalRelationshipType.OBJECT_TO_VALIDATION_RULE in kinds
        obj_to_field = [
            r for r in result.relationships
            if r.relationship_type == CanonicalRelationshipType.OBJECT_TO_FIELD
        ]
        assert obj_to_field[0].target_identity == _ident("field", "Account.MyField__c")
        assert obj_to_field[0].source_identity == _ident("object", "Account")
        assert result.missing_references == 0

    def test_field_kinds(self) -> None:
        result = CanonicalRelationshipResolver().resolve(
            ORG_ID, [_make_field()], active_targets=_active_targets(),
        )
        kinds = _types(result)
        assert CanonicalRelationshipType.FIELD_TO_OBJECT in kinds
        assert CanonicalRelationshipType.FIELD_TO_LOOKUP_TARGET in kinds
        assert CanonicalRelationshipType.FIELD_TO_FORMULA_REFERENCE in kinds
        assert CanonicalRelationshipType.OBJECT_TO_FIELD in kinds
        formula_refs = [
            r for r in result.relationships
            if r.relationship_type == CanonicalRelationshipType.FIELD_TO_FORMULA_REFERENCE
        ]
        targets = {r.target_api_name: r.target_type for r in formula_refs}
        assert targets == {"Discount__c": "field", "Config__c": "object"}

    def test_trigger_kinds(self) -> None:
        result = CanonicalRelationshipResolver().resolve(
            ORG_ID, [_make_trigger()], active_targets=_active_targets(),
        )
        kinds = _types(result)
        assert CanonicalRelationshipType.TRIGGER_TO_OBJECT in kinds
        assert CanonicalRelationshipType.OBJECT_TO_TRIGGER in kinds
        assert CanonicalRelationshipType.TRIGGER_TO_APEX in kinds
        apex_refs = [
            r for r in result.relationships
            if r.relationship_type == CanonicalRelationshipType.TRIGGER_TO_APEX
        ]
        assert {r.target_api_name for r in apex_refs} == {"AccountService"}
        assert result.missing_references == 1  # AuditHelper is unknown

    def test_layout_and_record_type_kinds(self) -> None:
        result = CanonicalRelationshipResolver().resolve(
            ORG_ID, [_make_layout(), _make_record_type()],
            active_targets=_active_targets(),
        )
        kinds = _types(result)
        assert CanonicalRelationshipType.LAYOUT_TO_OBJECT in kinds
        assert CanonicalRelationshipType.OBJECT_TO_LAYOUT in kinds
        assert CanonicalRelationshipType.RECORD_TYPE_TO_OBJECT in kinds
        assert CanonicalRelationshipType.OBJECT_TO_RECORD_TYPE in kinds

    def test_validation_rule_kind(self) -> None:
        result = CanonicalRelationshipResolver().resolve(
            ORG_ID, [_make_validation_rule()], active_targets=_active_targets(),
        )
        kinds = _types(result)
        assert CanonicalRelationshipType.OBJECT_TO_VALIDATION_RULE in kinds

    def test_flow_kinds(self) -> None:
        result = CanonicalRelationshipResolver().resolve(
            ORG_ID, [_make_flow()], active_targets=_active_targets(),
        )
        kinds = _types(result)
        assert CanonicalRelationshipType.FLOW_TO_OBJECT in kinds
        assert CanonicalRelationshipType.FLOW_TO_APEX in kinds
        assert CanonicalRelationshipType.FLOW_TO_FLOW in kinds
        assert CanonicalRelationshipType.FLOW_TO_INVOCABLE_ACTION in kinds
        invocable = [
            r for r in result.relationships
            if r.relationship_type == CanonicalRelationshipType.FLOW_TO_INVOCABLE_ACTION
        ]
        assert invocable[0].target_api_name == "DoThing"
        # Invocable action targets are external: always persisted, never missing.
        assert result.missing_references == 0

    def test_permission_set_kinds(self) -> None:
        result = CanonicalRelationshipResolver().resolve(
            ORG_ID, [_make_permission_set()], active_targets=_active_targets(),
        )
        kinds = _types(result)
        assert CanonicalRelationshipType.PERMISSION_SET_TO_OBJECT in kinds
        assert CanonicalRelationshipType.PERMISSION_SET_TO_FIELD in kinds
        assert CanonicalRelationshipType.PROFILE_TO_PERMISSION_SET in kinds
        profile_edge = next(
            r for r in result.relationships
            if r.relationship_type == CanonicalRelationshipType.PROFILE_TO_PERMISSION_SET
        )
        assert profile_edge.source_identity == _ident("profile", "Admin")
        assert profile_edge.target_identity == _ident("permission_set", "PS1")

    def test_custom_metadata_kind(self) -> None:
        result = CanonicalRelationshipResolver().resolve(
            ORG_ID, [_make_custom_metadata()], active_targets=_active_targets(),
        )
        kinds = _types(result)
        assert CanonicalRelationshipType.CUSTOM_METADATA_TO_REFERENCE in kinds
        ref = next(
            r for r in result.relationships
            if r.relationship_type == CanonicalRelationshipType.CUSTOM_METADATA_TO_REFERENCE
        )
        assert ref.target_identity == _ident("custom_metadata", "Config.Beta")


class TestTargetStateHandling:
    def test_missing_references_are_dropped_and_counted(self) -> None:
        field = _make_field()  # references Contact (known) and no unknown
        ghost = _component(
            MetadataField, "Ghost.Lookup__c", "field",
            object_api_name="Ghost", reference_to="NeverExisted",
        )
        result = CanonicalRelationshipResolver().resolve(
            ORG_ID, [field, ghost],
            active_targets=_active_targets(),
        )
        assert result.missing_references == 3  # Ghost, its field, NeverExisted

    def test_deleted_target_yields_deleted_relationship(self) -> None:
        deleted_account = _ident("object", "Account")
        result = CanonicalRelationshipResolver().resolve(
            ORG_ID, [_make_field()],
            active_targets=_active_targets() - {deleted_account},
            deleted_targets={deleted_account},
        )
        field_to_object = next(
            r for r in result.relationships
            if r.relationship_type == CanonicalRelationshipType.FIELD_TO_OBJECT
        )
        assert field_to_object.is_deleted
        assert field_to_object.deleted_at is not None

    def test_deleted_source_yields_deleted_relationships(self) -> None:
        from sfir_backend.domain.canonical.base import MetadataStatus

        deleted_trigger = _make_trigger()
        deleted_trigger.status = MetadataStatus.DELETED
        result = CanonicalRelationshipResolver().resolve(
            ORG_ID, [deleted_trigger], active_targets=_active_targets(),
        )
        assert result.relationships
        assert all(r.is_deleted for r in result.relationships)

    def test_duplicate_edges_within_batch_are_deduplicated(self) -> None:
        field = _make_field()
        result = CanonicalRelationshipResolver().resolve(
            ORG_ID, [field, field],
            active_targets=_active_targets(),
        )
        object_to_field = [
            r for r in result.relationships
            if r.relationship_type == CanonicalRelationshipType.OBJECT_TO_FIELD
        ]
        assert len(object_to_field) == 1

    def test_no_targets_means_unknown_targets_are_dropped(self) -> None:
        result = CanonicalRelationshipResolver().resolve(
            ORG_ID, [_make_flow()], active_targets=set(),
        )
        persisted_types = _types(result)
        # Invocable-action targets are external and always kept.
        assert persisted_types == {CanonicalRelationshipType.FLOW_TO_INVOCABLE_ACTION}
        assert result.missing_references == 3  # Account, SubFlow, FlowClass


class TestDictResolution:
    def test_normalized_dicts_resolve_parent_and_reference_kinds(self) -> None:
        account_ident = _ident("object", "Account")
        trigger_dict = {
            "identity": _ident("trigger", "AccountTrigger"),
            "type": "Trigger",
            "api_name": "AccountTrigger",
            "organization_id": ORG_ID,
            "namespace": None,
            "deleted": False,
            "status": "active",
            "properties": {},
            "raw_source": {},
            "parent_key": {"type": "object", "api_name": "Account", "namespace": None},
        }
        result = CanonicalRelationshipResolver().resolve(
            ORG_ID, [trigger_dict],
            active_targets={account_ident, _ident("trigger", "AccountTrigger")},
        )
        kinds = _types(result)
        assert CanonicalRelationshipType.TRIGGER_TO_OBJECT in kinds
        assert CanonicalRelationshipType.OBJECT_TO_TRIGGER in kinds
        trigger_to_object = next(
            r for r in result.relationships
            if r.relationship_type == CanonicalRelationshipType.TRIGGER_TO_OBJECT
        )
        assert trigger_to_object.target_identity == account_ident
