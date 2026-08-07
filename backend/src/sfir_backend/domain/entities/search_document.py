"""SearchDocument — a searchable row of the persisted search index.

One search document per graph node identity per tenant, mirroring the
canonical document and graph node it is derived from: versioned, only
ever soft-deleted, and enriched with the relationship context that powers
metadata lookup (parent object, references, relationship kinds, reference
count and relationship score for ranking).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sfir_backend.domain.entities.canonical_document import CanonicalDocument
from sfir_backend.domain.entities.graph_node import GraphNode


@dataclass
class SearchDocument:
    id: uuid.UUID
    organization_id: uuid.UUID
    identity: str
    metadata_type: str
    api_name: str
    developer_name: str
    display_name: str
    namespace: str | None
    content: str
    object_api_name: str = ""
    parent_identities: list[str] = field(default_factory=list)
    child_identities: list[str] = field(default_factory=list)
    reference_identities: list[str] = field(default_factory=list)
    relationship_types: list[str] = field(default_factory=list)
    reference_count: int = 0
    relationship_score: int = 0
    version: int = 1
    previous_version: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    deleted_at: datetime | None = None
    last_sync_job_id: uuid.UUID | None = None

    @staticmethod
    def from_graph_node(
        node: GraphNode,
        sync_job_id: uuid.UUID | None = None,
    ) -> SearchDocument:
        now = datetime.now(UTC)
        return SearchDocument(
            id=uuid.uuid4(),
            organization_id=node.organization_id,
            identity=node.identity,
            metadata_type=node.type,
            api_name=node.api_name,
            developer_name=node.api_name,
            display_name=node.api_name,
            namespace=node.namespace,
            content=node.api_name,
            deleted_at=node.deleted_at,
            last_sync_job_id=sync_job_id or node.last_sync_job_id,
            created_at=now,
            updated_at=now,
        )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def enrich_from_document(self, document: CanonicalDocument) -> None:
        """Pull developer name, display name and full-text content from the
        canonical document (its payload holds the normalized component)."""
        payload = document.payload or {}
        label = payload.get("label") or payload.get("display_name") or ""
        description = payload.get("description") or ""
        self.developer_name = document.developer_name or document.api_name
        self.display_name = str(label) if label else document.api_name
        if document.namespace is not None:
            self.namespace = document.namespace
        parts = [self.api_name, self.developer_name, self.display_name]
        if self.namespace:
            parts.append(self.namespace)
        if label:
            parts.append(str(label))
        if description:
            parts.append(str(description))
        self.content = " ".join(dict.fromkeys(parts))

    def soft_delete(self, sync_job_id: uuid.UUID | None = None) -> None:
        if self.deleted_at is None:
            self.deleted_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)
        if sync_job_id is not None:
            self.last_sync_job_id = sync_job_id

    def reactivate(self, sync_job_id: uuid.UUID | None = None) -> None:
        """Restore a previously deleted search document as a new version."""
        self.previous_version = self.version
        self.version += 1
        self.deleted_at = None
        self.updated_at = datetime.now(UTC)
        if sync_job_id is not None:
            self.last_sync_job_id = sync_job_id

    def unchanged_from(self, node: GraphNode) -> bool:
        """True when the document already reflects the node's state."""
        return (
            self.metadata_type == node.type
            and self.api_name == node.api_name
            and self.namespace == node.namespace
            and not self.is_deleted
        )


@dataclass
class SearchUpsertResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    soft_deleted: int = 0
    errors: list[str] = field(default_factory=list)
