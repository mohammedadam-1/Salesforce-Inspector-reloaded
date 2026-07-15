from __future__ import annotations

from typing import Any

from sfir_backend.domain.search.models import (
    SearchDocument,
    SearchResponse,
)
from sfir_backend.infrastructure.search.autocomplete import AutocompleteService
from sfir_backend.infrastructure.search.coordinator import SearchCoordinator
from sfir_backend.infrastructure.search.filter import SearchFilterEngine
from sfir_backend.infrastructure.search.formatter import SearchResultFormatter
from sfir_backend.infrastructure.search.index import SearchIndex
from sfir_backend.infrastructure.search.query_parser import QueryParser
from sfir_backend.infrastructure.search.ranking import SearchRankingEngine
from sfir_backend.infrastructure.search.services import (
    DependencySearchService,
    GlobalSearchService,
    MetadataSearchService,
)
from sfir_backend.infrastructure.search.statistics import SearchStatistics

_DEFAULT_TYPE_WEIGHTS: dict[str, float] = {
    "object": 1.0,
    "field": 1.0,
    "apex_class": 0.95,
    "trigger": 0.9,
    "flow": 0.9,
    "validation_rule": 0.85,
    "formula": 0.8,
    "permission_set": 0.8,
    "profile": 0.8,
    "layout": 0.75,
    "report": 0.75,
    "dashboard": 0.75,
    "record_type": 0.7,
    "global_value_set": 0.7,
    "custom_metadata": 0.7,
    "custom_setting": 0.7,
    "named_credential": 0.65,
    "role": 0.6,
    "queue": 0.6,
    "public_group": 0.6,
    "sharing_rule": 0.6,
    "lightning_page": 0.65,
    "quick_action": 0.6,
    "email_template": 0.6,
    "connected_app": 0.6,
    "workflow": 0.7,
    "approval_process": 0.7,
}


class SearchEngine:
    def __init__(
        self,
        index: SearchIndex | None = None,
        graph_engine: Any = None,
    ) -> None:
        self._index = index or SearchIndex()
        self._graph_engine = graph_engine
        self._parser = QueryParser()
        self._ranking = SearchRankingEngine()
        self._filter = SearchFilterEngine()
        self._formatter = SearchResultFormatter()
        self._autocomplete = AutocompleteService(self._index)
        self._metadata_service = MetadataSearchService(
            self._index, self._parser, self._ranking, self._filter, self._formatter,
        )
        self._global_service = GlobalSearchService(self._metadata_service)
        self._dependency_service = DependencySearchService(
            self._index, self._parser, self._ranking, self._filter, self._formatter, graph_engine,
        )
        self._coordinator = SearchCoordinator(
            self._global_service, self._metadata_service, self._dependency_service,
            self._autocomplete, self._formatter,
        )
        self._statistics = SearchStatistics(self._index)

    @property
    def index(self) -> SearchIndex:
        return self._index

    @property
    def coordinator(self) -> SearchCoordinator:
        return self._coordinator

    @property
    def statistics(self) -> SearchStatistics:
        return self._statistics

    def index_components(
        self,
        components: list[Any],
        graph_engine: Any | None = None,
    ) -> int:
        count = 0
        if graph_engine is not None:
            self._graph_engine = graph_engine
            self._dependency_service.set_graph_engine(graph_engine)

        dep_scores: dict[str, float] = {}
        edge_counts: dict[str, int] = {}
        if self._graph_engine is not None and hasattr(self._graph_engine, "graph"):
            graph = self._graph_engine.graph
            for node_key, node in graph.nodes.items():
                if node.api_name:
                    dep_scores[node.api_name] = 1.0
                    out_edges = graph.get_outgoing_edges(node_key)
                    in_edges = graph.get_incoming_edges(node_key)
                    edge_counts[node.api_name] = len(out_edges) + len(in_edges)

        for component in components:
            doc = self._component_to_document(component, dep_scores, edge_counts)
            if doc:
                self._index.index_document(doc)
                count += 1
        return count

    def _component_to_document(
        self,
        component: Any,
        dep_scores: dict[str, float],
        edge_counts: dict[str, int],
    ) -> SearchDocument | None:
        if component is None:
            return None
        if isinstance(component, SearchDocument):
            api = component.api_name
            component.dependency_score = dep_scores.get(api, component.dependency_score)
            component.edge_count = edge_counts.get(api, component.edge_count)
            return component
        api_name = getattr(component, "api_name", "") or ""
        if not api_name:
            return None
        metadata_type = getattr(component, "type", "") or ""
        if not metadata_type:
            metadata_type = type(component).__name__.lower().replace("metadata", "")
        doc_id = f"{metadata_type}:{api_name}"
        return SearchDocument(
            id=doc_id,
            api_name=api_name,
            label=getattr(component, "label", "") or "",
            description=getattr(component, "description", None),
            metadata_type=metadata_type,
            namespace=getattr(component, "namespace", None),
            organization_id=getattr(component, "organization_id", "") or "",
            status=getattr(component, "status", "active"),
            created_at=getattr(component, "created_at", None),
            updated_at=getattr(component, "updated_at", None),
            metadata_properties=getattr(component, "metadata_properties", {}) or {},
            dependency_score=dep_scores.get(api_name, 0.0),
            edge_count=edge_counts.get(api_name, 0),
        )

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
        import time
        start = time.time()
        try:
            result = self._coordinator.global_search(
                query=query, filters=filters, sort_field=sort_field,
                sort_direction=sort_direction, offset=offset, limit=limit,
                organization_id=organization_id,
            )
            self._statistics.record_query("global", (time.time() - start) * 1000, True)
            return result
        except Exception:
            self._statistics.record_query("global", (time.time() - start) * 1000, False)
            raise

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
        import time
        start = time.time()
        try:
            result = self._coordinator.search_metadata(
                query=query, metadata_types=metadata_types, filters=filters,
                sort_field=sort_field, sort_direction=sort_direction,
                offset=offset, limit=limit, organization_id=organization_id,
                namespace=namespace,
            )
            self._statistics.record_query("metadata", (time.time() - start) * 1000, True)
            return result
        except Exception:
            self._statistics.record_query("metadata", (time.time() - start) * 1000, False)
            raise

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
        import time
        start = time.time()
        try:
            result = self._coordinator.search_dependencies(
                query=query, node_key=node_key, direction=direction,
                filters=filters, sort_field=sort_field,
                sort_direction=sort_direction, offset=offset, limit=limit,
                organization_id=organization_id,
            )
            self._statistics.record_query("dependency", (time.time() - start) * 1000, True)
            return result
        except Exception:
            self._statistics.record_query("dependency", (time.time() - start) * 1000, False)
            raise

    def autocomplete(
        self,
        prefix: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        return self._coordinator.autocomplete(prefix, limit)

    def recent_searches(self, limit: int = 10) -> list[str]:
        return self._coordinator.recent_searches(limit)

    def record_search(self, query: str, result_count: int = 0) -> None:
        self._coordinator.record_search(query, result_count)

    def search_statistics(self) -> dict[str, Any]:
        return self._statistics.snapshot()

    def index_stats(self) -> dict[str, int]:
        return {
            "total_documents": self._index.total_documents,
            "total_types": len(self._index.count_by_type()),
        }

    def clear_index(self) -> None:
        self._index.clear()
        self._autocomplete.clear()
        self._statistics.reset()

    def set_graph_engine(self, graph_engine: Any) -> None:
        self._graph_engine = graph_engine
        self._dependency_service.set_graph_engine(graph_engine)
