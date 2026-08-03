"""Repository-fed Dependency Graph service (Phase 4).

The Metadata Repository is the ONLY source of metadata. This service never
queries Salesforce and never uses parsers/extractors. It builds and queries
the dependency graph exclusively from ``IMetadataRepository`` components.

Design guarantees:
  - Deterministic: no AI, no LLM, no heuristics — only verified metadata.
  - Tenant isolation: every repository call carries ``request_context`` and
    every graph is cached/loaded per ``organization_id``.
  - RequestContext propagation: passed to every repo call and recorded in
    graph metadata.
  - Public method surface is compatible with the legacy ``GraphService``
    (``build_graph``, ``get_node_dependencies``, ``find_impact``,
    ``find_cycles``, ``graph_summary``) so existing API routes, AI tools and
    impact code keep working unchanged.
"""

from __future__ import annotations

from typing import Any

import structlog

from sfir_backend.application.cache.services import GraphCacheService
from sfir_backend.domain.canonical.base import MetadataComponent
from sfir_backend.domain.graph.models import DependencyGraph, Graph, GraphNode
from sfir_backend.domain.repositories.metadata_repo import (
    IMetadataRepository,
    MetadataFilter,
    Pagination,
)
from sfir_backend.domain.request_context import RequestContext
from sfir_backend.infrastructure.graph.cache import GraphCacheCoordinator
from sfir_backend.infrastructure.graph.engine import DependencyGraphEngine

logger = structlog.get_logger(__name__)

# Cap for bulk loads — paginate over the repository instead of N+1.
_PAGE_SIZE = 1000


class RepositoryGraphService:
    """Repository-only dependency graph service."""

    def __init__(
        self,
        metadata_repo: IMetadataRepository,
        graph_engine: DependencyGraphEngine | None = None,
        cache: GraphCacheService | None = None,
        cache_coordinator: GraphCacheCoordinator | None = None,
    ) -> None:
        self._repo = metadata_repo
        self._engine = graph_engine or DependencyGraphEngine()
        self._cache = cache
        self._cache_coordinator = cache_coordinator or GraphCacheCoordinator()
        self._cache_key_by_org: dict[str, str] = {}

    # ── construction ───────────────────────────────────────────

    async def build_graph(
        self,
        organization_id: Any,
        metadata_types: list[str] | None = None,
        request_context: RequestContext | None = None,
    ) -> DependencyGraph:
        """Full rebuild exclusively from repository components."""
        org_key = str(organization_id)
        cache_key = f"repo-graph:{org_key}"

        # Fast path: cached graph for this org (org isolation).
        cached = self._cache_coordinator.get(cache_key)
        if cached is not None:
            self._engine.load_cached_graph(cached)
            self._cache_key_by_org[org_key] = cache_key
            return cached

        components = await self._load_all(organization_id, metadata_types, request_context)

        graph = self._engine.build_from_repository(
            components,
            cache_key=cache_key,
        )
        self._cache_key_by_org[org_key] = cache_key
        graph.metadata = {
            **(graph.metadata or {}),
            "organization_id": org_key,
            "source": "metadata_repository",
            "request_id": request_context.request_id if request_context else None,
        }
        # Store into our own coordinator so subsequent calls for the same org
        # hit the fast path (org isolation).
        self._cache_coordinator.set(cache_key, graph)
        return graph

    async def incremental_update(
        self,
        organization_id: Any,
        *,
        new_components: list[MetadataComponent] | None = None,
        changed_components: list[MetadataComponent] | None = None,
        deleted_api_names: list[str] | None = None,
        request_context: RequestContext | None = None,
    ) -> DependencyGraph:
        """Incremental rebuild from repository change sets."""
        org_key = str(organization_id)
        cache_key = self._cache_key_by_org.get(org_key) or f"repo-graph:{org_key}"
        cached = self._cache_coordinator.get(cache_key)
        if cached is not None:
            self._engine.load_cached_graph(cached)
        elif str((self._engine.graph.metadata or {}).get("organization_id")) != org_key:
            await self.build_graph(
                organization_id,
                request_context=request_context,
            )

        graph = self._engine.incremental_update_from_repository(
            new_components=new_components,
            changed_components=changed_components,
            deleted_api_names=deleted_api_names,
        )
        graph.metadata = {
            **(graph.metadata or {}),
            "organization_id": org_key,
            "source": "metadata_repository_incremental",
            "request_id": request_context.request_id if request_context else None,
        }
        self._cache_key_by_org[org_key] = cache_key
        self._cache_coordinator.set(cache_key, graph)
        return graph

    async def build_graph_versioned(
        self,
        organization_id: Any,
        components_by_version: dict[str, list[MetadataComponent]],
        request_context: RequestContext | None = None,
    ) -> DependencyGraph:
        """Version-aware rebuild: latest version of each component wins."""
        graph = self._engine.build_from_repository_versioned(components_by_version)
        org_key = str(organization_id)
        cache_key = f"repo-graph:{org_key}"
        self._cache_coordinator.set(cache_key, graph)
        self._cache_key_by_org[org_key] = cache_key
        graph.metadata = {
            **(graph.metadata or {}),
            "organization_id": org_key,
            "source": "metadata_repository_versioned",
            "request_id": request_context.request_id if request_context else None,
        }
        return graph

    async def _load_all(
        self,
        organization_id: Any,
        metadata_types: list[str] | None,
        request_context: RequestContext | None,
    ) -> list[MetadataComponent]:
        """Bulk-load components via the repository (paginated, no N+1)."""
        all_components: list[MetadataComponent] = []
        offset = 0
        while True:
            page = await self._repo.get_by_organization(
                organization_id,
                filter=MetadataFilter(types=metadata_types),
                pagination=Pagination(limit=_PAGE_SIZE, offset=offset),
                sort=None,
                request_context=request_context,
            )
            all_components.extend(page)
            if len(page) < _PAGE_SIZE:
                break
            offset += _PAGE_SIZE
        return all_components

    # ── graph access ───────────────────────────────────────────

    @property
    def graph(self) -> Graph:
        return self._engine.graph

    async def get_node(self, node_key: str) -> GraphNode | None:
        return self._engine.get_node(node_key)

    async def get_neighbors(
        self,
        node_key: str,
        depth: int = 1,
    ) -> list[GraphNode]:
        return self._engine.get_neighbors(node_key, depth)

    async def get_dependencies(
        self,
        node_key: str,
        max_depth: int = 1,
    ) -> list[GraphNode]:
        """Nodes this node depends on (upstream / outgoing)."""
        return self._engine.get_dependencies(node_key, max_depth)

    async def get_dependents(
        self,
        node_key: str,
        max_depth: int = 1,
    ) -> list[GraphNode]:
        """Nodes that depend on this node (downstream / incoming)."""
        return self._engine.get_dependents(node_key, max_depth)

    async def find_where_used(
        self,
        api_name: str,
        metadata_type: str | None = None,
    ) -> list[GraphNode]:
        """Where is this component used? (reverse dependencies)."""
        return self._engine.where_used(api_name, metadata_type)

    async def find_path(
        self,
        source_key: str,
        target_key: str,
    ) -> list[str] | None:
        return self._engine.find_path(source_key, target_key)

    async def shortest_path(
        self,
        source_key: str,
        target_key: str,
    ) -> Any:
        return self._engine.shortest_path(source_key, target_key)

    async def find_cycles(
        self,
        graph: DependencyGraph | None = None,
    ) -> list[list[str]]:
        """Detect cycles.

        ``graph`` is accepted for legacy API compatibility (ignored — the
        engine's current graph is authoritative).
        """
        return self._engine.detect_cycles()

    async def connected_components(self) -> list[list[str]]:
        return self._engine.connected_components()

    async def get_subgraph(self, node_key: str, depth: int = 1) -> Graph:
        return self._engine.get_subgraph(node_key, depth)

    async def export(self) -> dict[str, Any]:
        return self._engine.export()

    # ── legacy-compatible API surface ──────────────────────────

    async def get_node_dependencies(
        self,
        graph: DependencyGraph,
        component_type: str,
        component_name: str,
        depth: int = 1,
    ) -> dict[str, Any]:
        """Compatible with legacy GraphService.get_node_dependencies.

        ``graph`` is accepted for API compatibility; the authoritative graph is
        the engine's current graph.
        """
        active = self._engine.graph
        node_key = f"{component_type}:{component_name}"
        node = active.get_node(node_key)

        upstream = active.get_upstream(node_key, depth)
        downstream = active.get_downstream(node_key, depth)

        return {
            "node": {
                "component_type": component_type,
                "component_name": component_name,
                "component_id": node.id if node else None,
            } if node else None,
            "upstream": [
                {"component_type": _node_type_str(n), "component_name": n.api_name}
                for n in upstream
            ],
            "downstream": [
                {"component_type": _node_type_str(n), "component_name": n.api_name}
                for n in downstream
            ],
        }

    async def find_impact(
        self,
        graph: DependencyGraph,
        component_type: str,
        component_name: str,
        max_depth: int = 3,
    ) -> list[dict[str, Any]]:
        """Compatible with legacy GraphService.find_impact."""
        active = self._engine.graph
        node_key = f"{component_type}:{component_name}"
        downstream = active.get_downstream(node_key, max_depth)

        impacted: list[dict[str, Any]] = []
        seen: set[str] = set()
        for node in downstream:
            if node.key not in seen:
                seen.add(node.key)
                impacted.append({
                    "component_type": _node_type_str(node),
                    "component_name": node.api_name,
                    "component_id": node.id,
                })
        return impacted

    async def graph_summary(self, graph: DependencyGraph) -> dict[str, Any]:
        """Compatible with legacy GraphService.graph_summary."""
        active = self._engine.graph
        return {
            "node_count": active.node_count,
            "edge_count": active.edge_count,
            "cycles": len(active.find_cycles()),
            "component_types": _count_by_type(active),
        }

    async def invalidate(self, organization_id: Any) -> None:
        """Drop the cached graph for an org (forces next rebuild)."""
        org_key = str(organization_id)
        cache_key = self._cache_key_by_org.pop(org_key, None)
        if cache_key:
            self._cache_coordinator.invalidate(cache_key)
        if self._cache is not None:
            await self._cache.invalidate(organization_id=org_key)


def _node_type_str(node: GraphNode) -> str:
    return node.node_type.value if node.node_type else "unknown"


def _count_by_type(graph: Graph) -> dict[str, int]:
    counts: dict[str, int] = {}
    for node in graph.nodes.values():
        t = _node_type_str(node)
        counts[t] = counts.get(t, 0) + 1
    return counts
