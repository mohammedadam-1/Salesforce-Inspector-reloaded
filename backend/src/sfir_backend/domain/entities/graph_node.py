"""GraphNode — a dependency-graph node derived from a canonical document.

One graph node per canonical document identity per tenant. The node mirrors
the document's lifecycle: it is versioned (a node re-appearing after
deletion gets a new version), soft-delete aware, and tracks the canonical
document version and fingerprint it was last built from so incremental
rebuilds can skip unchanged nodes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sfir_backend.domain.entities.canonical_document import CanonicalDocument


@dataclass
class GraphNode:
    id: uuid.UUID
    organization_id: uuid.UUID
    identity: str
    type: str
    api_name: str
    namespace: str | None
    document_version: int
    document_fingerprint: str
    version: int
    previous_version: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    last_sync_job_id: uuid.UUID | None = None

    @staticmethod
    def from_document(
        document: CanonicalDocument,
        sync_job_id: uuid.UUID | None = None,
    ) -> GraphNode:
        now = datetime.now(UTC)
        return GraphNode(
            id=uuid.uuid4(),
            organization_id=document.organization_id,
            identity=document.identity,
            type=document.type,
            api_name=document.api_name,
            namespace=document.namespace,
            document_version=document.version,
            document_fingerprint=document.fingerprint,
            version=1,
            previous_version=0,
            created_at=now,
            updated_at=now,
            deleted_at=document.deleted_at if document.is_deleted else None,
            last_sync_job_id=sync_job_id,
        )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def as_deleted(self, sync_job_id: uuid.UUID | None = None) -> None:
        """Mark the node deleted (mirrors a soft-deleted canonical document)."""
        if self.deleted_at is None:
            self.deleted_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)
        if sync_job_id is not None:
            self.last_sync_job_id = sync_job_id

    def reactivate(
        self,
        document: CanonicalDocument,
        sync_job_id: uuid.UUID | None = None,
    ) -> None:
        """Restore a previously deleted node as a new version."""
        self.previous_version = self.version
        self.version += 1
        self.deleted_at = None
        self.document_version = document.version
        self.document_fingerprint = document.fingerprint
        self.type = document.type
        self.api_name = document.api_name
        self.namespace = document.namespace
        self.updated_at = datetime.now(UTC)
        if sync_job_id is not None:
            self.last_sync_job_id = sync_job_id

    def apply_document(
        self,
        document: CanonicalDocument,
        sync_job_id: uuid.UUID | None = None,
    ) -> None:
        """Refresh node content from an updated document (version preserved)."""
        self.type = document.type
        self.api_name = document.api_name
        self.namespace = document.namespace
        self.document_version = document.version
        self.document_fingerprint = document.fingerprint
        self.updated_at = datetime.now(UTC)
        if sync_job_id is not None:
            self.last_sync_job_id = sync_job_id

    def unchanged(self, document: CanonicalDocument) -> bool:
        """True when the node already reflects the document's state."""
        return (
            self.type == document.type
            and self.api_name == document.api_name
            and self.namespace == document.namespace
            and self.document_version == document.version
            and self.document_fingerprint == document.fingerprint
            and not self.is_deleted
        )


@dataclass
class GraphUpsertResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    soft_deleted: int = 0
    errors: list[str] = field(default_factory=list)
