from __future__ import annotations

import re
from typing import Any

from sfir_backend.domain.graph.models import (
    DependencyEdge,
    DependencyGraph,
    DependencyNode,
    DependencyType,
)
from sfir_backend.domain.metadata.flows import Flow, FlowElement
from sfir_backend.infrastructure.salesforce.graph.base import DependencyExtractor


class FlowDependencyExtractor(DependencyExtractor):
    component_type = "Flow"

    def can_extract(self, component_type: str) -> bool:
        return component_type == "Flow"

    async def extract(
        self,
        graph: DependencyGraph,
        component_name: str,
        parsed: Any,
        raw: dict[str, Any] | None = None,
    ) -> DependencyGraph:
        if not isinstance(parsed, Flow):
            return graph

        source = graph.add_node(DependencyNode(
            component_type="Flow",
            component_name=component_name,
            component_id=parsed.component_id,
        ))

        for obj_name in parsed.record_creates:
            target = graph.add_node(DependencyNode(
                component_type="CustomObject",
                component_name=obj_name,
            ))
            graph.add_edge(DependencyEdge(
                source=source, target=target,
                dependency_type=DependencyType.USES_OBJECT,
            ))

        for obj_name in parsed.record_updates:
            target = graph.add_node(DependencyNode(
                component_type="CustomObject",
                component_name=obj_name,
            ))
            graph.add_edge(DependencyEdge(
                source=source, target=target,
                dependency_type=DependencyType.USES_OBJECT,
            ))

        for obj_name in parsed.record_deletes:
            target = graph.add_node(DependencyNode(
                component_type="CustomObject",
                component_name=obj_name,
            ))
            graph.add_edge(DependencyEdge(
                source=source, target=target,
                dependency_type=DependencyType.USES_OBJECT,
            ))

        for subflow_name in parsed.subflows:
            target = graph.add_node(DependencyNode(
                component_type="Flow",
                component_name=subflow_name,
            ))
            graph.add_edge(DependencyEdge(
                source=source, target=target,
                dependency_type=DependencyType.USES_CLASS,
            ))

        for element in parsed.elements:
            for obj_ref in element.object_references:
                target = graph.add_node(DependencyNode(
                    component_type="CustomObject",
                    component_name=obj_ref,
                ))
                graph.add_edge(DependencyEdge(
                    source=source, target=target,
                    dependency_type=DependencyType.USES_OBJECT,
                ))

            if element.formula:
                self._extract_formula_refs(source, element.formula, graph)

        return graph

    def _extract_formula_refs(
        self, source: DependencyNode, formula: str, graph: DependencyGraph,
    ) -> None:
        parts = re.split(r"[^a-zA-Z0-9_.]+", formula)
        seen: set[str] = set()
        for part in parts:
            if not part or "." not in part:
                continue
            if not part[0].isupper():
                continue
            obj_part = part.split(".")[0]
            seen_key = f"CustomObject:{obj_part}"
            if seen_key not in seen:
                seen.add(seen_key)
                target = graph.add_node(DependencyNode(
                    component_type="CustomObject",
                    component_name=obj_part,
                ))
                graph.add_edge(DependencyEdge(
                    source=source, target=target,
                    dependency_type=DependencyType.USES_OBJECT,
                ))
