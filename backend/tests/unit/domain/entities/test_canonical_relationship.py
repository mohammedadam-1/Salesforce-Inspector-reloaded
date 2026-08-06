"""CanonicalRelationship entity tests."""

from __future__ import annotations

import uuid

from sfir_backend.domain.entities.canonical_relationship import (
    CanonicalRelationship,
    CanonicalRelationshipType,
    CanonicalRelationshipUpsertResult,
)

ORG_ID = uuid.uuid4()


def _relationship() -> CanonicalRelationship:
    return CanonicalRelationship.create(
        organization_id=ORG_ID,
        source_identity="src-1",
        source_api_name="Account",
        source_type="object",
        target_identity="tgt-1",
        target_api_name="Account.MyField__c",
        target_type="field",
        relationship_type=CanonicalRelationshipType.OBJECT_TO_FIELD,
    )


class TestCreate:
    def test_create_initializes_version_history(self) -> None:
        rel = _relationship()
        assert rel.version == 1
        assert rel.previous_version == 0
        assert not rel.is_deleted
        assert rel.deleted_at is None
        assert rel.id is not None
        assert rel.created_at is not None
        assert rel.updated_at is not None
        assert rel.last_sync_job_id is None

    def test_create_records_sync_job(self) -> None:
        job_id = uuid.uuid4()
        rel = CanonicalRelationship.create(
            organization_id=ORG_ID,
            source_identity="s",
            source_api_name="S",
            source_type="apex_class",
            target_identity="t",
            target_api_name="T",
            target_type="apex_class",
            relationship_type=CanonicalRelationshipType.TRIGGER_TO_APEX,
            sync_job_id=job_id,
        )
        assert rel.last_sync_job_id == job_id


class TestLifecycle:
    def test_soft_delete_is_idempotent(self) -> None:
        rel = _relationship()
        rel.soft_delete()
        deleted_at = rel.deleted_at
        assert rel.is_deleted
        rel.soft_delete()
        assert rel.deleted_at == deleted_at

    def test_reactivate_bumps_version(self) -> None:
        rel = _relationship()
        rel.soft_delete()
        assert rel.version == 1
        rel.reactivate()
        assert rel.version == 2
        assert rel.previous_version == 1
        assert not rel.is_deleted
        assert rel.deleted_at is None

    def test_reactivate_from_never_deleted_keeps_version(self) -> None:
        rel = _relationship()
        rel.reactivate()
        assert rel.version == 2
        assert rel.previous_version == 1

    def test_soft_delete_and_reactivate_record_sync_job(self) -> None:
        job_a = uuid.uuid4()
        job_b = uuid.uuid4()
        rel = _relationship()
        rel.soft_delete(sync_job_id=job_a)
        assert rel.last_sync_job_id == job_a
        rel.reactivate(sync_job_id=job_b)
        assert rel.last_sync_job_id == job_b


class TestEnum:
    def test_all_relationship_kinds_are_defined(self) -> None:
        kinds = {member.value for member in CanonicalRelationshipType}
        assert kinds == {
            "object_to_field",
            "object_to_record_type",
            "object_to_layout",
            "object_to_validation_rule",
            "object_to_trigger",
            "field_to_object",
            "field_to_lookup_target",
            "field_to_formula_reference",
            "flow_to_object",
            "flow_to_apex",
            "flow_to_flow",
            "flow_to_invocable_action",
            "trigger_to_object",
            "trigger_to_apex",
            "permission_set_to_object",
            "permission_set_to_field",
            "profile_to_permission_set",
            "layout_to_object",
            "record_type_to_object",
            "custom_metadata_to_reference",
        }

    def test_relationship_type_is_str_enum(self) -> None:
        assert CanonicalRelationshipType.OBJECT_TO_FIELD == "object_to_field"


class TestUpsertResult:
    def test_defaults(self) -> None:

        result = CanonicalRelationshipUpsertResult()
        assert result.created == 0
        assert result.updated == 0
        assert result.skipped == 0
        assert result.soft_deleted == 0
        assert result.missing_references == 0
        assert result.errors == []
