"""Canonical document — current-state row of the canonical metadata store.

A canonical document is the system-of-record row for one stable metadata
identity (tenant + type + api name + namespace). It holds the current
version, the previous version number, the content fingerprint and the
lifecycle timestamps. Every change creates a new version row in the
version store (metadata_versions); this row only ever tracks the latest
state and is never physically deleted.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sfir_backend.domain.canonical.base import MetadataStatus


@dataclass
class CanonicalDocument:
    id: uuid.UUID
    organization_id: uuid.UUID
    identity: str
    type: str
    api_name: str
    developer_name: str
    namespace: str | None
    version: int
    previous_version: int
    fingerprint: str
    status: MetadataStatus
    created_at: datetime
    updated_at: datetime
    first_seen_at: datetime
    last_seen_at: datetime
    deleted_at: datetime | None = None
    last_sync_job_id: uuid.UUID | None = None
    payload: dict = field(default_factory=dict)

    @staticmethod
    def create(
        organization_id: uuid.UUID,
        identity: str,
        type: str,
        api_name: str,
        developer_name: str,
        namespace: str | None,
        version: int,
        previous_version: int,
        fingerprint: str,
        sync_job_id: uuid.UUID | None = None,
        payload: dict | None = None,
    ) -> CanonicalDocument:
        now = datetime.now(UTC)
        return CanonicalDocument(
            id=uuid.uuid4(),
            organization_id=organization_id,
            identity=identity,
            type=type,
            api_name=api_name,
            developer_name=developer_name,
            namespace=namespace,
            version=version,
            previous_version=previous_version,
            fingerprint=fingerprint,
            status=MetadataStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            first_seen_at=now,
            last_seen_at=now,
            last_sync_job_id=sync_job_id,
            payload=payload or {},
        )

    @property
    def is_deleted(self) -> bool:
        return self.status == MetadataStatus.DELETED

    def record_change(
        self,
        version: int,
        previous_version: int,
        fingerprint: str,
        sync_job_id: uuid.UUID | None = None,
        payload: dict | None = None,
    ) -> None:
        """Advance the current state after a content change (new version)."""
        self.previous_version = previous_version
        self.version = version
        self.fingerprint = fingerprint
        self.updated_at = datetime.now(UTC)
        self.last_seen_at = datetime.now(UTC)
        self.last_sync_job_id = sync_job_id
        if payload is not None:
            self.payload = payload
        if self.is_deleted:
            self.status = MetadataStatus.ACTIVE
            self.deleted_at = None

    def touch(self, sync_job_id: uuid.UUID | None = None) -> None:
        """Refresh last_seen without advancing the version."""
        self.last_seen_at = datetime.now(UTC)
        if sync_job_id is not None:
            self.last_sync_job_id = sync_job_id

    def soft_delete(self, sync_job_id: uuid.UUID | None = None) -> None:
        """Mark deleted; the row is never removed."""
        if not self.is_deleted:
            self.status = MetadataStatus.DELETED
            self.deleted_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)
        self.last_seen_at = datetime.now(UTC)
        if sync_job_id is not None:
            self.last_sync_job_id = sync_job_id


@dataclass
class CanonicalUpsertResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    soft_deleted: int = 0
