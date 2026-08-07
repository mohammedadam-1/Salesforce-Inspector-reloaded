"""Canonical document repository — single source of truth for the store.

The canonical store persists normalized documents only. One row per
stable identity per tenant; never physically deleted. Version history
lives in the append-only version store (metadata_versions).
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from sfir_backend.domain.entities.canonical_document import (
    CanonicalDocument,
    CanonicalUpsertResult,
)


class ICanonicalDocumentRepository(ABC):
    @abstractmethod
    async def upsert_batch(
        self,
        organization_id: uuid.UUID,
        documents: list[CanonicalDocument],
    ) -> CanonicalUpsertResult:
        """Upsert current-state rows for changed documents.

        Idempotent: a row that already matches identity and fingerprint is
        not written again. Implementations must be conflict-safe under
        concurrent workers (no duplicates).
        """
        ...

    @abstractmethod
    async def get_by_identity(
        self,
        organization_id: uuid.UUID,
        identity: str,
    ) -> CanonicalDocument | None:
        """Return the current-state row for a stable identity."""
        ...

    @abstractmethod
    async def get_by_identities(
        self,
        organization_id: uuid.UUID,
        identities: set[str],
    ) -> list[CanonicalDocument]:
        """Return current-state rows for a set of stable identities."""
        ...

    @abstractmethod
    async def list_latest(
        self,
        organization_id: uuid.UUID,
        *,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[CanonicalDocument]:
        """List current-state rows for an organization (multi-tenant)."""
        ...

    @abstractmethod
    async def list_latest_by_type(
        self,
        organization_id: uuid.UUID,
        metadata_type: str,
    ) -> list[CanonicalDocument]:
        """List current-state rows of one metadata type."""
        ...

    @abstractmethod
    async def count_by_organization(
        self,
        organization_id: uuid.UUID,
    ) -> int:
        """Count current-state rows for an organization."""
        ...

    @abstractmethod
    async def soft_delete_by_identity(
        self,
        organization_id: uuid.UUID,
        identity: str,
        *,
        sync_job_id: uuid.UUID | None = None,
    ) -> bool:
        """Mark a document deleted; never physically remove the row."""
        ...

    @abstractmethod
    async def soft_delete_missing(
        self,
        organization_id: uuid.UUID,
        metadata_type: str,
        seen_api_names: set[str],
        *,
        sync_job_id: uuid.UUID | None = None,
    ) -> int:
        """Soft-delete active documents of a type absent from a full scan.

        Only runs after the type was fully retrieved, so it never touches
        components that simply were not fetched yet (resume-safe).
        """
        ...
