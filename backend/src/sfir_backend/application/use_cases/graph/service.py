from __future__ import annotations

from typing import Any

from sfir_backend.domain.graph.models import DependencyGraph
from sfir_backend.domain.repositories.sync_repos import IMetadataVersionRepository
from sfir_backend.infrastructure.salesforce.graph.extractor import CompositeExtractor
from sfir_backend.infrastructure.salesforce.parsers.registry import ParserRegistry


class GraphService:
    def __init__(
        self,
        version_repo: IMetadataVersionRepository,
        parser_registry: ParserRegistry,
        extractor: CompositeExtractor,
    ) -> None:
        self._version_repo = version_repo
        self._parser_registry = parser_registry
        self._extractor = extractor

    async def build_graph(
        self,
        organization_id: Any,
        metadata_types: list[str] | None = None,
    ) -> DependencyGraph:
        graph = DependencyGraph()

        versions = await self._version_repo.list_by_organization(organization_id)
        if metadata_types:
            versions = [v for v in versions if v.component_type in metadata_types]

        for version in versions:
            raw = version.payload or {}
            result = await self._parser_registry.parse(version.component_type, raw)
            if result.success and result.data is not None:
                await self._extractor.extract(
                    graph, version.component_name, result.data, raw,
                )

        return graph

    async def get_node_dependencies(
        self,
        graph: DependencyGraph,
        component_type: str,
        component_name: str,
        depth: int = 1,
    ) -> dict[str, Any]:
        node_key = f"{component_type}:{component_name}"
        node = graph.get_node(component_type, component_name)

        upstream = graph.get_upstream(node_key, depth)
        downstream = graph.get_downstream(node_key, depth)

        return {
            "node": {
                "component_type": component_type,
                "component_name": component_name,
                "component_id": node.component_id if node else None,
            } if node else None,
            "upstream": [
                {"component_type": n.component_type, "component_name": n.component_name}
                for n in upstream
            ],
            "downstream": [
                {"component_type": n.component_type, "component_name": n.component_name}
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
        node_key = f"{component_type}:{component_name}"
        downstream = graph.get_downstream(node_key, max_depth)

        impacted: list[dict[str, Any]] = []
        seen: set[str] = set()
        for node in downstream:
            if node.key not in seen:
                seen.add(node.key)
                impacted.append({
                    "component_type": node.component_type,
                    "component_name": node.component_name,
                    "component_id": node.component_id,
                })
        return impacted

    async def find_cycles(self, graph: DependencyGraph) -> list[list[str]]:
        return graph.find_cycles()

    async def graph_summary(self, graph: DependencyGraph) -> dict[str, Any]:
        return {
            "node_count": graph.node_count,
            "edge_count": graph.edge_count,
            "cycles": len(graph.find_cycles()),
            "component_types": _count_by_type(graph),
        }

    async def get_parser_registry(self) -> ParserRegistry:
        return self._parser_registry


def _count_by_type(graph: DependencyGraph) -> dict[str, int]:
    counts: dict[str, int] = {}
    for node in graph.nodes.values():
        counts[node.component_type] = counts.get(node.component_type, 0) + 1
    return counts
