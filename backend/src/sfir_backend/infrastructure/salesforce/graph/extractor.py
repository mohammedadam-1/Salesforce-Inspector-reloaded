from __future__ import annotations

from typing import Any

from sfir_backend.domain.graph.models import DependencyGraph
from sfir_backend.infrastructure.salesforce.graph.base import DependencyExtractor


class CompositeExtractor(DependencyExtractor):
    def __init__(self, extractors: list[DependencyExtractor] | None = None) -> None:
        self._extractors = extractors or []

    def register(self, extractor: DependencyExtractor) -> None:
        self._extractors.append(extractor)

    def can_extract(self, component_type: str) -> bool:
        return any(e.can_extract(component_type) for e in self._extractors)

    async def extract(
        self,
        graph: DependencyGraph,
        component_name: str,
        parsed: Any,
        raw: dict[str, Any] | None = None,
    ) -> DependencyGraph:
        for extractor in self._extractors:
            cls_name = parsed.__class__.__name__ if hasattr(parsed, "__class__") else ""
            if extractor.can_extract(cls_name):
                await extractor.extract(graph, component_name, parsed, raw)
        return graph
