from __future__ import annotations

import re
from typing import Any

from sfir_backend.domain.graph.models import (
    DependencyEdge,
    DependencyGraph,
    DependencyNode,
    DependencyType,
)
from sfir_backend.domain.metadata.objects import ValidationRule
from sfir_backend.infrastructure.salesforce.graph.base import DependencyExtractor


class ValidationRuleDependencyExtractor(DependencyExtractor):
    component_type = "ValidationRule"

    def can_extract(self, component_type: str) -> bool:
        return component_type == "ValidationRule"

    async def extract(
        self,
        graph: DependencyGraph,
        component_name: str,
        parsed: Any,
        _raw: dict[str, Any] | None = None,
    ) -> DependencyGraph:
        if not isinstance(parsed, ValidationRule):
            return graph

        source = graph.add_node(DependencyNode(
            component_type="ValidationRule",
            component_name=component_name,
        ))

        if parsed.formula:
            self._extract_field_refs(source, parsed.formula, graph)

        return graph

    def _extract_field_refs(
        self, source: DependencyNode, formula: str, graph: DependencyGraph,
    ) -> None:
        re.compile(r"__c\b")
        parts = re.split(r"[\(\)\[\]\s,;=<>!+\-*/&|]+", formula)
        seen: set[str] = set()
        for part in parts:
            if not part:
                continue
            if part.endswith("__c") and "." in part:
                obj_part, _field_part = part.split(".", 1)
                seen_key = f"CustomField:{part}"
                if seen_key not in seen:
                    seen.add(seen_key)
                    target = graph.add_node(DependencyNode(
                        component_type="CustomField",
                        component_name=part,
                    ))
                    graph.add_edge(DependencyEdge(
                        source=source, target=target,
                        dependency_type=DependencyType.USES_FIELD,
                    ))
                    obj_node = graph.add_node(DependencyNode(
                        component_type="CustomObject",
                        component_name=obj_part,
                    ))
                    graph.add_edge(DependencyEdge(
                        source=source, target=obj_node,
                        dependency_type=DependencyType.USES_OBJECT,
                    ))
