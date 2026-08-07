"""Graph repository contract.

The dependency graph store persists graph nodes (one per canonical document
identity) and graph edges (one per canonical relationship), both keyed by
tenant. Rows are idempotently upserted, versioned, and only ever
soft-deleted — mirroring the canonical store they are derived from.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from sfir_backend.domain.entities.graph_edge import GraphEdge
from sfir_backend.domain.entities.graph_node import GraphNode, GraphUpsertResult


class IGraphRepository(ABC):
    @abstractmethod
    async def upsert_nodes(
        self,
        organization_id: uuid.UUID,
        nodes: list[GraphNode],
    ) -> GraphUpsertResult:
        """Create, update, or reactivate graph nodes.

        Idempotent: unchanged nodes are skipped; nodes built from
        soft-deleted canonical documents are stored as deleted rows.
        """

    @abstractmethod
    async def upsert_edges(
        self,
        organization_id: uuid.UUID,
        edges: list[GraphEdge],
    ) -> GraphUpsertResult:
        """Create, update, or reactivate graph edges.

        Idempotent: unchanged edges are skipped; edges built from
        soft-deleted relationships are stored as deleted rows.
        """

    @abstractmethod
    async def soft_delete_nodes(
        self,
        organization_id: uuid.UUID,
        identities: set[str],
        *,
        sync_job_id: uuid.UUID | None = None,
    ) -> int:
        """Soft-delete graph nodes whose canonical documents are gone."""

    @abstractmethod
    async def soft_delete_edges_for_node(
        self,
        organization_id: uuid.UUID,
        identity: str,
        *,
        sync_job_id: uuid.UUID | None = None,
    ) -> int:
        """Soft-delete every active edge touching a deleted node (both directions)."""

    @abstractmethod
    async def soft_delete_missing_edges_for_source(
        self,
        organization_id: uuid.UUID,
        source_identity: str,
        seen_edges: set[tuple[str, str]],
        *,
        sync_job_id: uuid.UUID | None = None,
    ) -> int:
        """Soft-delete a source's outgoing edges absent from the latest run."""

    @abstractmethod
    async def soft_delete_edges_for_sources(
        self,
        organization_id: uuid.UUID,
        source_identities: set[str],
        *,
        sync_job_id: uuid.UUID | None = None,
    ) -> int:
        """Soft-delete every active outgoing edge of soft-deleted sources."""

    @abstractmethod
    async def get_node(
        self,
        organization_id: uuid.UUID,
        identity: str,
    ) -> GraphNode | None:
        ...

    @abstractmethod
    async def get_nodes_by_identities(
        self,
        organization_id: uuid.UUID,
        identities: set[str],
    ) -> list[GraphNode]:
        ...

    @abstractmethod
    async def get_edges_by_keys(
        self,
        organization_id: uuid.UUID,
        keys: set[tuple[str, str, str]],
    ) -> list[GraphEdge]:
        """Fetch edges by (source identity, target identity, relationship type)."""

    @abstractmethod
    async def list_active_nodes(
        self,
        organization_id: uuid.UUID,
        *,
        limit: int = 1000,
        offset: int = 0,
        metadata_type: str | None = None,
    ) -> list[GraphNode]:
        ...

    @abstractmethod
    async def list_active_edges(
        self,
        organization_id: uuid.UUID,
        *,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[GraphEdge]:
        ...

    @abstractmethod
    async def list_active_edges_for_identities(
        self,
        organization_id: uuid.UUID,
        identities: set[str],
        *,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[GraphEdge]:
        """List active edges touching any of the identities (either direction)."""
        ...

    @abstractmethod
    async def count_nodes(
        self,
        organization_id: uuid.UUID,
    ) -> int:
        ...

    @abstractmethod
    async def count_edges(
        self,
        organization_id: uuid.UUID,
    ) -> int:
        ...
