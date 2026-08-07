"""Search index repository contract.

The search index store persists one searchable document per graph node
identity per tenant, enriched with relationship context (parent object,
references, relationship kinds, reference count, relationship score). Rows
are idempotently upserted, only ever soft-deleted, and queried with
exact/prefix/fuzzy, case-insensitive, namespace-aware matching.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from sfir_backend.domain.entities.search_document import (
    SearchDocument,
    SearchUpsertResult,
)

SEARCH_MODES = frozenset({"exact", "prefix", "fuzzy"})
SEARCH_FIELDS = frozenset(
    {
        "api_name",
        "developer_name",
        "display_name",
        "namespace",
        "metadata_type",
        "object",
        "content",
    },
)


class ISearchIndexRepository(ABC):
    @abstractmethod
    async def upsert_batch(
        self,
        organization_id: uuid.UUID,
        documents: list[SearchDocument],
    ) -> SearchUpsertResult:
        """Create, update, or reactivate search documents.

        Idempotent: unchanged documents are skipped; documents built from
        deleted state are stored as deleted rows.
        """

    @abstractmethod
    async def soft_delete_by_identities(
        self,
        organization_id: uuid.UUID,
        identities: set[str],
        *,
        sync_job_id: uuid.UUID | None = None,
    ) -> int:
        """Soft-delete search documents whose graph nodes are gone."""

    @abstractmethod
    async def search(
        self,
        organization_id: uuid.UUID,
        query: str,
        *,
        mode: str = "fuzzy",
        fields: set[str] | None = None,
        metadata_type: str | None = None,
        namespace: str | None = None,
        relationship_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[SearchDocument]:
        """Search active documents, ranked by match quality.

        ``mode`` is one of ``exact`` / ``prefix`` / ``fuzzy`` (substring),
        always case-insensitive. Matching is scoped to ``fields`` (default:
        every searchable field). Optional filters narrow by metadata type,
        namespace, or relationship kind.
        """

    @abstractmethod
    async def get_by_identity(
        self,
        organization_id: uuid.UUID,
        identity: str,
    ) -> SearchDocument | None:
        ...

    @abstractmethod
    async def list_active(
        self,
        organization_id: uuid.UUID,
        *,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[SearchDocument]:
        ...

    @abstractmethod
    async def count_by_organization(
        self,
        organization_id: uuid.UUID,
    ) -> int:
        ...
