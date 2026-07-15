from __future__ import annotations

from typing import Any

from sfir_backend.domain.search.models import (
    SearchQuery,
    SearchResponse,
)
from sfir_backend.infrastructure.search.filter import SearchFilterEngine
from sfir_backend.infrastructure.search.formatter import SearchResultFormatter
from sfir_backend.infrastructure.search.index import SearchIndex
from sfir_backend.infrastructure.search.query_parser import QueryParser
from sfir_backend.infrastructure.search.ranking import SearchRankingEngine


class MetadataSearchService:
    def __init__(
        self,
        index: SearchIndex,
        parser: QueryParser,
        ranking: SearchRankingEngine,
        filter_engine: SearchFilterEngine,
        formatter: SearchResultFormatter,
    ) -> None:
        self._index = index
        self._parser = parser
        self._ranking = ranking
        self._filter = filter_engine
        self._formatter = formatter

    def search(
        self,
        query_str: str,
        metadata_types: list[str] | None = None,
        filters: list[dict[str, Any]] | None = None,
        sort_field: str | None = None,
        sort_direction: str = "desc",
        offset: int = 0,
        limit: int = 20,
        organization_id: str = "",
        namespace: str | None = None,
    ) -> SearchResponse:
        query = self._parser.parse(
            raw_query=query_str,
            filters=filters,
            sort_field=sort_field,
            sort_direction=sort_direction,
            offset=offset,
            limit=limit,
            metadata_types=metadata_types,
            organization_id=organization_id,
            namespace=namespace,
        )
        return self._execute_search(query)

    def _execute_search(self, query: SearchQuery) -> SearchResponse:
        import time
        start = time.time()

        doc_ids = self._index.search(query.tokens, operator="AND")

        documents = [
            self._index.get_document(did)
            for did in doc_ids
            if self._index.get_document(did) is not None
        ]
        documents = self._filter.apply(documents, query)
        if not documents:
            return self._formatter.format(
                [], query, 0, start, suggestions=self._index.suggest(query.raw_query, 5),
            )
        scored = self._ranking.rank(documents, query)
        return self._formatter.format(
            scored, query, len(scored), start, suggestions=self._index.suggest(query.raw_query, 5),
        )


class GlobalSearchService:
    def __init__(
        self,
        metadata_service: MetadataSearchService,
    ) -> None:
        self._metadata_service = metadata_service

    def search(
        self,
        query_str: str,
        filters: list[dict[str, Any]] | None = None,
        sort_field: str | None = None,
        sort_direction: str = "desc",
        offset: int = 0,
        limit: int = 20,
        organization_id: str = "",
    ) -> SearchResponse:
        return self._metadata_service.search(
            query_str=query_str,
            filters=filters,
            sort_field=sort_field,
            sort_direction=sort_direction,
            offset=offset,
            limit=limit,
            organization_id=organization_id,
        )


class DependencySearchService:
    def __init__(
        self,
        index: SearchIndex,
        parser: QueryParser,
        ranking: SearchRankingEngine,
        filter_engine: SearchFilterEngine,
        formatter: SearchResultFormatter,
        graph_engine: Any = None,
    ) -> None:
        self._index = index
        self._parser = parser
        self._ranking = ranking
        self._filter = filter_engine
        self._formatter = formatter
        self._graph = graph_engine

    def set_graph_engine(self, graph_engine: Any) -> None:
        self._graph = graph_engine

    def search(
        self,
        query_str: str,
        node_key: str | None = None,
        direction: str = "both",
        filters: list[dict[str, Any]] | None = None,
        sort_field: str | None = None,
        sort_direction: str = "desc",
        offset: int = 0,
        limit: int = 20,
        organization_id: str = "",
        min_depth: int = 0,
        max_depth: int | None = None,
    ) -> SearchResponse:
        import time
        start = time.time()

        query = self._parser.parse(
            raw_query=query_str,
            filters=filters,
            sort_field=sort_field,
            sort_direction=sort_direction,
            offset=offset,
            limit=limit,
            organization_id=organization_id,
        )
        query.min_dependency_depth = min_depth
        query.max_dependency_depth = max_depth

        base_ids = self._index.search(query.tokens, operator="AND")
        if node_key and self._graph:
            related = self._get_related_nodes(node_key, direction)
            base_ids &= related

        documents = [
            self._index.get_document(did)
            for did in base_ids
            if self._index.get_document(did) is not None
        ]
        documents = self._filter.apply(documents, query)
        if not documents:
            return self._formatter.format(
                [], query, 0, start, suggestions=self._index.suggest(query.raw_query, 5),
            )
        scored = self._ranking.rank(documents, query)
        return self._formatter.format(
            scored, query, len(scored), start, suggestions=self._index.suggest(query.raw_query, 5),
        )

    def _get_related_nodes(self, node_key: str, direction: str) -> set[str]:
        if self._graph is None or not hasattr(self._graph, "graph"):
            return set()
        graph = self._graph.graph
        related: set[str] = set()
        if direction in ("outgoing", "both"):
            for edge in graph.get_outgoing_edges(node_key):
                related.add(edge.target_id)
        if direction in ("incoming", "both"):
            for edge in graph.get_incoming_edges(node_key):
                related.add(edge.source_id)
        return related
