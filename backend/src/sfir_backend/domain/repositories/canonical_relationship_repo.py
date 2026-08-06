"""Canonical relationship repository contract.

The canonical relationship store is the system of record for typed,
directional relationships between canonical metadata documents. Rows are
keyed by (tenant, source identity, target identity, relationship type),
idempotently upserted, and only ever soft-deleted.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from sfir_backend.domain.entities.canonical_relationship import (
    CanonicalRelationship,
    CanonicalRelationshipUpsertResult,
)


class ICanonicalRelationshipRepository(ABC):
    @abstractmethod
    async def upsert_batch(
        self,
        organization_id: uuid.UUID,
        relationships: list[CanonicalRelationship],
    ) -> CanonicalRelationshipUpsertResult:
        """Create or reactivate relationships; unchanged rows are skipped.

        Idempotent: re-running the same batch never duplicates rows and
        never bumps versions for relationships that are already active.
        """

    @abstractmethod
    async def soft_delete_missing_for_source(
        self,
        organization_id: uuid.UUID,
        source_identity: str,
        seen_edges: set[tuple[str, str]],
        *,
        sync_job_id: uuid.UUID | None = None,
    ) -> int:
        """Soft-delete a source's outgoing edges absent from the latest run."""

    @abstractmethod
    async def soft_delete_by_source_identities(
        self,
        organization_id: uuid.UUID,
        source_identities: set[str],
        *,
        sync_job_id: uuid.UUID | None = None,
    ) -> int:
        """Soft-delete every outgoing edge of soft-deleted sources."""

    @abstractmethod
    async def list_by_source(
        self,
        organization_id: uuid.UUID,
        source_identity: str,
    ) -> list[CanonicalRelationship]:
        ...

    @abstractmethod
    async def list_active(
        self,
        organization_id: uuid.UUID,
        *,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[CanonicalRelationship]:
        """Current active relationships for a tenant (paged)."""

    @abstractmethod
    async def count_by_organization(
        self,
        organization_id: uuid.UUID,
    ) -> int:
        ...
