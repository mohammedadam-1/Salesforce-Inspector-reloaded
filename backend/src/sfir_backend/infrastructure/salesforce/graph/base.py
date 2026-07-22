from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from sfir_backend.domain.graph.models import DependencyGraph


class DependencyExtractor(ABC):
    component_type: str = ""

    @abstractmethod
    def can_extract(self, component_type: str) -> bool:
        ...

    @abstractmethod
    async def extract(
        self,
        graph: DependencyGraph,
        component_name: str,
        parsed: Any,
        raw: dict[str, Any] | None = None,
    ) -> DependencyGraph:
        ...
