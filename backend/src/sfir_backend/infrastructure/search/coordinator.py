from __future__ import annotations

from typing import Any

from sfir_backend.domain.search.models import (
    SearchResponse,
)
from sfir_backend.infrastructure.search.autocomplete import AutocompleteService
from sfir_backend.infrastructure.search.formatter import SearchResultFormatter
from sfir_backend.infrastructure.search.services import (
    DependencySearchService,
    GlobalSearchService,
    MetadataSearchService,
)


class SearchCoordinator:
    def __init__(
        self,
        global_service: GlobalSearchService,
        metadata_service: MetadataSearchService,
        dependency_service: DependencySearchService,
        autocomplete: AutocompleteService,
        formatter: SearchResultFormatter,
    ) -> None:
        self._global = global_service
        self._metadata = metadata_service
        self._dependency = dependency_service
        self._autocomplete = autocomplete
        self._formatter = formatter

    def global_search(
        self,
        query: str,
        filters: list[dict[str, Any]] | None = None,
        sort_field: str | None = None,
        sort_direction: str = "desc",
        offset: int = 0,
        limit: int = 20,
        organization_id: str = "",
    ) -> SearchResponse:
        response = self._global.search(
            query_str=query,
            filters=filters,
            sort_field=sort_field,
            sort_direction=sort_direction,
            offset=offset,
            limit=limit,
            organization_id=organization_id,
        )
        self._autocomplete.record_search(query, response.total_count)
        return response

    def search_metadata(
        self,
        query: str,
        metadata_types: list[str] | None = None,
        filters: list[dict[str, Any]] | None = None,
        sort_field: str | None = None,
        sort_direction: str = "desc",
        offset: int = 0,
        limit: int = 20,
        organization_id: str = "",
        namespace: str | None = None,
    ) -> SearchResponse:
        response = self._metadata.search(
            query_str=query,
            metadata_types=metadata_types,
            filters=filters,
            sort_field=sort_field,
            sort_direction=sort_direction,
            offset=offset,
            limit=limit,
            organization_id=organization_id,
            namespace=namespace,
        )
        self._autocomplete.record_search(query, response.total_count)
        return response

    def search_dependencies(
        self,
        query: str,
        node_key: str | None = None,
        direction: str = "both",
        filters: list[dict[str, Any]] | None = None,
        sort_field: str | None = None,
        sort_direction: str = "desc",
        offset: int = 0,
        limit: int = 20,
        organization_id: str = "",
    ) -> SearchResponse:
        response = self._dependency.search(
            query_str=query,
            node_key=node_key,
            direction=direction,
            filters=filters,
            sort_field=sort_field,
            sort_direction=sort_direction,
            offset=offset,
            limit=limit,
            organization_id=organization_id,
        )
        self._autocomplete.record_search(query, response.total_count)
        return response

    def autocomplete(
        self,
        prefix: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        suggestions = self._autocomplete.suggest(prefix, limit)
        return self._formatter.format_suggestions(suggestions, prefix)

    def recent_searches(self, limit: int = 10) -> list[str]:
        return self._autocomplete.recent_searches(limit)

    def record_search(self, query: str, result_count: int = 0) -> None:
        self._autocomplete.record_search(query, result_count)

    def get_index_stats(self) -> dict[str, int]:
        return {}
