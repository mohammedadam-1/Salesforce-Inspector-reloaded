"""GraphEdge — a dependency-graph edge derived from a canonical relationship.

One graph edge per (tenant, source identity, target identity, relationship
type). The edge mirrors the canonical relationship's lifecycle: versioned
(reactivation bumps the version), soft-delete aware, idempotent.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sfir_backend.domain.entities.canonical_relationship import (
    CanonicalRelationship,
    CanonicalRelationshipType,
)


@dataclass
class GraphEdge:
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
    def from_relationship(
        relationship: CanonicalRelationship,
    ) -> GraphEdge:
        return GraphEdge(
            id=uuid.uuid4(),
            organization_id=relationship.organization_id,
            source_identity=relationship.source_identity,
            source_api_name=relationship.source_api_name,
            source_type=relationship.source_type,
            target_identity=relationship.target_identity,
            target_api_name=relationship.target_api_name,
            target_type=relationship.target_type,
            relationship_type=relationship.relationship_type,
            version=1,
            previous_version=0,
            created_at=relationship.created_at,
            updated_at=relationship.updated_at,
            deleted_at=relationship.deleted_at,
            last_sync_job_id=relationship.last_sync_job_id,
        )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def as_deleted(self) -> None:
        """Mark the edge deleted (mirrors a soft-deleted relationship)."""
        if self.deleted_at is None:
            self.deleted_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

    def reactivate(
        self,
        relationship: CanonicalRelationship,
    ) -> None:
        """Restore a previously deleted edge as a new version."""
        self.previous_version = self.version
        self.version += 1
        self.deleted_at = None
        self.source_api_name = relationship.source_api_name
        self.source_type = relationship.source_type
        self.target_api_name = relationship.target_api_name
        self.target_type = relationship.target_type
        self.updated_at = datetime.now(UTC)
        if relationship.last_sync_job_id is not None:
            self.last_sync_job_id = relationship.last_sync_job_id

    def apply_relationship(
        self,
        relationship: CanonicalRelationship,
    ) -> None:
        """Refresh edge content from an updated relationship (version preserved)."""
        self.source_api_name = relationship.source_api_name
        self.source_type = relationship.source_type
        self.target_api_name = relationship.target_api_name
        self.target_type = relationship.target_type
        self.updated_at = datetime.now(UTC)
        if relationship.last_sync_job_id is not None:
            self.last_sync_job_id = relationship.last_sync_job_id

    def unchanged(self, relationship: CanonicalRelationship) -> bool:
        """True when the edge already reflects the relationship's state."""
        return (
            self.source_api_name == relationship.source_api_name
            and self.source_type == relationship.source_type
            and self.target_api_name == relationship.target_api_name
            and self.target_type == relationship.target_type
            and not self.is_deleted
        )
