"""Canonical relationship — typed, directional, versioned relationship row.

The canonical relationship store records directed edges between canonical
metadata documents (source identity -> target identity) with a typed
relationship kind. Rows are versioned (version bumps when a relationship
re-appears after deletion), tenant-scoped, and never physically deleted —
a ``deleted`` flag tracks lifecycle state so the dependency-graph phase can
read a complete history of what was ever connected.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class CanonicalRelationshipType(StrEnum):
    """The typed relationship kinds resolved between canonical metadata."""

    OBJECT_TO_FIELD = "object_to_field"
    OBJECT_TO_RECORD_TYPE = "object_to_record_type"
    OBJECT_TO_LAYOUT = "object_to_layout"
    OBJECT_TO_VALIDATION_RULE = "object_to_validation_rule"
    OBJECT_TO_TRIGGER = "object_to_trigger"
    FIELD_TO_OBJECT = "field_to_object"
    FIELD_TO_LOOKUP_TARGET = "field_to_lookup_target"
    FIELD_TO_FORMULA_REFERENCE = "field_to_formula_reference"
    FLOW_TO_OBJECT = "flow_to_object"
    FLOW_TO_APEX = "flow_to_apex"
    FLOW_TO_FLOW = "flow_to_flow"
    FLOW_TO_INVOCABLE_ACTION = "flow_to_invocable_action"
    TRIGGER_TO_OBJECT = "trigger_to_object"
    TRIGGER_TO_APEX = "trigger_to_apex"
    PERMISSION_SET_TO_OBJECT = "permission_set_to_object"
    PERMISSION_SET_TO_FIELD = "permission_set_to_field"
    PROFILE_TO_PERMISSION_SET = "profile_to_permission_set"
    LAYOUT_TO_OBJECT = "layout_to_object"
    RECORD_TYPE_TO_OBJECT = "record_type_to_object"
    CUSTOM_METADATA_TO_REFERENCE = "custom_metadata_to_reference"


@dataclass
class CanonicalRelationship:
    id: uuid.UUID
    organization_id: uuid.UUID
    source_identity: str
    source_api_name: str
    source_type: str
    target_identity: str
    target_api_name: str
    target_type: str
    relationship_type: CanonicalRelationshipType
    version: int
    previous_version: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    last_sync_job_id: uuid.UUID | None = None

    @staticmethod
    def create(
        organization_id: uuid.UUID,
        source_identity: str,
        source_api_name: str,
        source_type: str,
        target_identity: str,
        target_api_name: str,
        target_type: str,
        relationship_type: CanonicalRelationshipType,
        sync_job_id: uuid.UUID | None = None,
    ) -> CanonicalRelationship:
        now = datetime.now(UTC)
        return CanonicalRelationship(
            id=uuid.uuid4(),
            organization_id=organization_id,
            source_identity=source_identity,
            source_api_name=source_api_name,
            source_type=source_type,
            target_identity=target_identity,
            target_api_name=target_api_name,
            target_type=target_type,
            relationship_type=relationship_type,
            version=1,
            previous_version=0,
            created_at=now,
            updated_at=now,
            last_sync_job_id=sync_job_id,
        )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def reactivate(
        self,
        sync_job_id: uuid.UUID | None = None,
    ) -> None:
        """Restore a previously deleted relationship as a new version."""
        self.previous_version = self.version
        self.version += 1
        self.deleted_at = None
        self.updated_at = datetime.now(UTC)
        if sync_job_id is not None:
            self.last_sync_job_id = sync_job_id

    def soft_delete(self, sync_job_id: uuid.UUID | None = None) -> None:
        if self.deleted_at is None:
            self.deleted_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)
        if sync_job_id is not None:
            self.last_sync_job_id = sync_job_id


@dataclass
class CanonicalRelationshipUpsertResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    soft_deleted: int = 0
    missing_references: int = 0
    errors: list[str] = field(default_factory=list)
