from __future__ import annotations

from typing import Any

from sfir_backend.domain.canonical import MetadataComponent
from sfir_backend.domain.graph.models import (
    Graph,
    GraphNode,
    GraphSnapshot,
)
from sfir_backend.infrastructure.graph.builder import GraphBuilder
from sfir_backend.infrastructure.graph.cache import GraphCacheCoordinator
from sfir_backend.infrastructure.graph.cycle import CycleDetectionEngine
from sfir_backend.infrastructure.graph.resolver import DependencyResolver
from sfir_backend.infrastructure.graph.statistics import GraphStatistics
from sfir_backend.infrastructure.graph.traversal import GraphTraversalEngine
from sfir_backend.infrastructure.graph.validator import GraphValidator
from sfir_backend.infrastructure.graph.version import GraphVersionManager


class DependencyGraphEngine:
    def __init__(
        self,
        builder: GraphBuilder | None = None,
        traversal: GraphTraversalEngine | None = None,
        resolver: DependencyResolver | None = None,
        cycle_detector: CycleDetectionEngine | None = None,
        validator: GraphValidator | None = None,
        version_manager: GraphVersionManager | None = None,
        cache: GraphCacheCoordinator | None = None,
        statistics: GraphStatistics | None = None,
    ) -> None:
        self._builder = builder or GraphBuilder()
        self._traversal = traversal or GraphTraversalEngine()
        self._resolver = resolver or DependencyResolver(self._traversal)
        self._cycle_detector = cycle_detector or CycleDetectionEngine()
        self._validator = validator or GraphValidator()
        self._version_manager = version_manager or GraphVersionManager()
        self._cache = cache or GraphCacheCoordinator()
        self._statistics = statistics or GraphStatistics()
        self._graph: Graph = Graph()

    @property
    def graph(self) -> Graph:
        return self._graph

    @property
    def version(self) -> str:
        return self._version_manager.current_version

    def build(
        self,
        components: list[MetadataComponent],
        relationships: list[Any] | None = None,
        cache_key: str | None = None,
    ) -> Graph:
        self._graph = self._builder.build(components, relationships)
        self._version_manager.create_snapshot(
            self._graph,
            change_summary=(
                f"Built from {len(components)} components, "
                f"{len(relationships or [])} relationships"
            ),
        )
        if cache_key:
            self._cache.set(cache_key, self._graph)
        return self._graph

    def build_from_parse_results(
        self,
        parse_results: list[Any],
        cache_key: str | None = None,
    ) -> Graph:
        self._graph = self._builder.build_from_parse_results(parse_results)
        self._version_manager.create_snapshot(
            self._graph,
            change_summary=f"Built from {len(parse_results)} parse results",
        )
        if cache_key:
            self._cache.set(cache_key, self._graph)
        return self._graph

    def incremental_update(
        self,
        new_components: list[MetadataComponent] | None = None,
        changed_components: list[MetadataComponent] | None = None,
        deleted_api_names: list[str] | None = None,
        new_relationships: list[Any] | None = None,
    ) -> Graph:
        self._graph = self._builder.incremental_update(
            self._graph,
            new_components=new_components,
            changed_components=changed_components,
            deleted_api_names=deleted_api_names,
            new_relationships=new_relationships,
        )
        self._version_manager.create_snapshot(
            self._graph,
            change_summary="Incremental update",
        )
        return self._graph

    # ── Normalized input methods ───────────────────────────────

    def build_from_normalized(
        self,
        normalized_components: list[dict],
        cache_key: str | None = None,
    ) -> Graph:
        self._graph = self._builder.build_from_normalized(normalized_components)
        self._version_manager.create_snapshot(
            self._graph,
            change_summary=(
                f"Built from {len(normalized_components)} normalized documents, "
                f"{self._graph.edge_count} relationships"
            ),
        )
        if cache_key:
            self._cache.set(cache_key, self._graph)
        return self._graph

    def incremental_update_from_normalized(
        self,
        normalized_components: list[dict] | None = None,
        deleted_api_names: list[str] | None = None,
    ) -> Graph:
        self._graph = self._builder.incremental_update_from_normalized(
            self._graph,
            normalized_components=normalized_components,
            deleted_api_names=deleted_api_names,
        )
        self._version_manager.create_snapshot(
            self._graph,
            change_summary="Incremental update from normalized",
        )
        return self._graph

    def get_snapshot(self, snapshot_id: str) -> GraphSnapshot | None:
        return self._version_manager.get_snapshot(snapshot_id)

    def rollback(self, version: str) -> GraphSnapshot | None:
        snapshot = self._version_manager.rollback_to_version(version)
        if snapshot is not None:
            self._graph = snapshot.graph
        return snapshot

    def list_snapshots(self) -> list[GraphSnapshot]:
        return self._version_manager.list_snapshots()

    # ── Traversal ──────────────────────────────────────────────

    def dfs(self, node_key: str, **kwargs: Any) -> Any:
        from sfir_backend.domain.graph.traversal import TraversalContext
        ctx = TraversalContext(**kwargs)
        return self._traversal.dfs(self._graph, node_key, ctx)

    def bfs(self, node_key: str, **kwargs: Any) -> Any:
        from sfir_backend.domain.graph.traversal import TraversalContext
        ctx = TraversalContext(**kwargs)
        return self._traversal.bfs(self._graph, node_key, ctx)

    def shortest_path(self, from_node: str, to_node: str, **kwargs: Any) -> Any:
        from sfir_backend.domain.graph.traversal import TraversalContext
        ctx = TraversalContext(**kwargs)
        return self._traversal.shortest_path(self._graph, from_node, to_node, ctx)

    # ── Resolution ─────────────────────────────────────────────

    def where_used(self, api_name: str, metadata_type: str | None = None) -> list[GraphNode]:
        return self._resolver.where_used(self._graph, api_name, metadata_type)

    def what_depends_on(self, api_name: str, metadata_type: str | None = None) -> list[GraphNode]:
        return self._resolver.what_depends_on(self._graph, api_name, metadata_type)

    def find_orphaned(self) -> list[GraphNode]:
        return self._resolver.find_orphaned(self._graph)

    def find_unreachable(self) -> list[GraphNode]:
        return self._resolver.find_unreachable(self._graph)

    # ── Cycle Detection ────────────────────────────────────────

    def detect_cycles(self) -> list[list[str]]:
        return self._cycle_detector.detect_cycles(self._graph)

    def has_cycles(self) -> bool:
        return self._cycle_detector.has_cycles(self._graph)

    def cycle_diagnostics(self) -> dict[str, Any]:
        return self._cycle_detector.cycle_diagnostics(self._graph)

    # ── Validation ─────────────────────────────────────────────

    def validate(self) -> dict[str, Any]:
        return self._validator.integrity_check(self._graph)

    def consistency_check(self) -> dict[str, Any]:
        return self._validator.consistency_check(self._graph)

    # ── Statistics ─────────────────────────────────────────────

    def statistics(self) -> dict[str, Any]:
        return self._statistics.snapshot(self._graph)

    def node_counts_by_type(self) -> dict[str, int]:
        return self._statistics.node_count_by_type(self._graph)

    def edge_counts_by_type(self) -> dict[str, int]:
        return self._statistics.edge_count_by_type(self._graph)
