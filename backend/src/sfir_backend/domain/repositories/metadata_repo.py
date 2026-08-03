"""Metadata Repository interface — single source of truth for metadata."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any, Protocol

from sfir_backend.domain.canonical.base import MetadataComponent
from sfir_backend.domain.entities.metadata_sync import MetadataVersion
from sfir_backend.domain.request_context import RequestContext


class MetadataFilter:
    """Filter criteria for metadata queries."""

    def __init__(
        self,
        *,
        types: list[str] | None = None,
        namespaces: list[str] | None = None,
        search_text: str | None = None,
        status: str | None = None,
        is_custom: bool | None = None,
        tags: list[str] | None = None,
        metadata_properties: dict[str, Any] | None = None,
    ) -> None:
        self.types = types
        self.namespaces = namespaces
        self.search_text = search_text
        self.status = status
        self.is_custom = is_custom
        self.tags = tags
        self.metadata_properties = metadata_properties


class Pagination:
    """Pagination parameters."""

    def __init__(self, limit: int = 100, offset: int = 0) -> None:
        self.limit = max(1, min(limit, 1000))
        self.offset = max(0, offset)


class SortOrder:
    """Sort options for metadata queries."""

    def __init__(
        self,
        field: str = "api_name",
        descending: bool = False,
    ) -> None:
        self.field = field
        self.descending = descending


class IMetadataRepository(ABC):
    """Single source of truth for metadata operations.

    Every public method accepts RequestContext for tenant isolation.
    No ORM models are exposed outside infrastructure.
    """

    @abstractmethod
    async def save(
        self,
        organization_id: uuid.UUID,
        component: MetadataComponent,
        *,
        request_context: RequestContext | None = None,
    ) -> MetadataComponent:
        """Save a single metadata component."""
        ...

    @abstractmethod
    async def save_batch(
        self,
        organization_id: uuid.UUID,
        components: list[MetadataComponent],
        *,
        request_context: RequestContext | None = None,
    ) -> list[MetadataComponent]:
        """Save multiple metadata components in a single transaction."""
        ...

    @abstractmethod
    async def update(
        self,
        organization_id: uuid.UUID,
        component: MetadataComponent,
        *,
        request_context: RequestContext | None = None,
    ) -> MetadataComponent:
        """Update an existing metadata component."""
        ...

    @abstractmethod
    async def delete(
        self,
        organization_id: uuid.UUID,
        api_name: str,
        *,
        request_context: RequestContext | None = None,
    ) -> bool:
        """Delete a metadata component by api_name."""
        ...

    @abstractmethod
    async def get_by_id(
        self,
        organization_id: uuid.UUID,
        component_id: str,
        *,
        request_context: RequestContext | None = None,
    ) -> MetadataComponent | None:
        """Find a component by its ID."""
        ...

    @abstractmethod
    async def get_by_api_name(
        self,
        organization_id: uuid.UUID,
        api_name: str,
        *,
        request_context: RequestContext | None = None,
    ) -> MetadataComponent | None:
        """Find a component by its API name."""
        ...

    @abstractmethod
    async def get_by_api_names(
        self,
        organization_id: uuid.UUID,
        api_names: list[str],
        *,
        request_context: RequestContext | None = None,
    ) -> list[MetadataComponent]:
        """Bulk-load components by API name across all metadata types.

        Implementations MUST avoid N+1 queries — a bounded set of batched
        queries is expected regardless of the number of api_names.
        """
        ...

    @abstractmethod
    async def get_versions(
        self,
        organization_id: uuid.UUID,
        api_name: str,
        *,
        pagination: Pagination | None = None,
        request_context: RequestContext | None = None,
    ) -> list[MetadataVersion]:
        """Return the version history for a component, newest first."""
        ...

    @abstractmethod
    async def get_latest_version(
        self,
        organization_id: uuid.UUID,
        api_name: str,
        *,
        request_context: RequestContext | None = None,
    ) -> MetadataVersion | None:
        """Return the latest version of a component, or None."""
        ...

    @abstractmethod
    async def list_versions_by_organization(
        self,
        organization_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
        request_context: RequestContext | None = None,
    ) -> list[MetadataVersion]:
        """Bulk-load version rows for an organization (change detection).

        Ordered by component_name then version_number ascending so callers can
        cheaply derive per-component latest versions while scanning.
        """
        ...

    @abstractmethod
    async def save_version(
        self,
        organization_id: uuid.UUID,
        version: MetadataVersion,
        *,
        request_context: RequestContext | None = None,
    ) -> MetadataVersion:
        """Persist a single metadata version."""
        ...

    @abstractmethod
    async def save_versions(
        self,
        organization_id: uuid.UUID,
        versions: list[MetadataVersion],
        *,
        request_context: RequestContext | None = None,
    ) -> list[MetadataVersion]:
        """Persist many versions in a single transaction (no per-row commits)."""
        ...

    @abstractmethod
    async def get_by_type(
        self,
        organization_id: uuid.UUID,
        metadata_type: str,
        *,
        pagination: Pagination | None = None,
        sort: SortOrder | None = None,
        request_context: RequestContext | None = None,
    ) -> list[MetadataComponent]:
        """Find all components of a given metadata type."""
        ...

    @abstractmethod
    async def get_by_organization(
        self,
        organization_id: uuid.UUID,
        *,
        filter: MetadataFilter | None = None,
        pagination: Pagination | None = None,
        sort: SortOrder | None = None,
        request_context: RequestContext | None = None,
    ) -> list[MetadataComponent]:
        """Find all components for an organization with optional filtering."""
        ...

    @abstractmethod
    async def get_by_namespace(
        self,
        organization_id: uuid.UUID,
        namespace: str,
        *,
        pagination: Pagination | None = None,
        request_context: RequestContext | None = None,
    ) -> list[MetadataComponent]:
        """Find all components in a given namespace."""
        ...

    @abstractmethod
    async def search(
        self,
        organization_id: uuid.UUID,
        query: str,
        *,
        type_filter: list[str] | None = None,
        pagination: Pagination | None = None,
        request_context: RequestContext | None = None,
    ) -> list[MetadataComponent]:
        """Full-text search across metadata components."""
        ...

    @abstractmethod
    async def get_relationships(
        self,
        organization_id: uuid.UUID,
        api_name: str,
        *,
        request_context: RequestContext | None = None,
    ) -> list[MetadataComponent]:
        """Get all components that relate to the given component."""
        ...

    @abstractmethod
    async def get_dependencies(
        self,
        organization_id: uuid.UUID,
        api_name: str,
        *,
        request_context: RequestContext | None = None,
    ) -> list[MetadataComponent]:
        """Get all components that depend on the given component."""
        ...

    @abstractmethod
    async def count_by_organization(
        self,
        organization_id: uuid.UUID,
        *,
        type_filter: list[str] | None = None,
        request_context: RequestContext | None = None,
    ) -> int:
        """Count components for an organization."""
        ...

    @abstractmethod
    async def get_types(
        self,
        organization_id: uuid.UUID,
        *,
        request_context: RequestContext | None = None,
    ) -> list[str]:
        """Get distinct metadata types present for an organization."""
        ...