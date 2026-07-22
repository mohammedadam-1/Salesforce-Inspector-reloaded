from __future__ import annotations

from typing import Any

from sfir_backend.domain.graph.models import (
    DependencyEdge,
    DependencyGraph,
    DependencyNode,
    DependencyType,
)
from sfir_backend.domain.metadata.layouts import Layout
from sfir_backend.infrastructure.salesforce.graph.base import DependencyExtractor


class LayoutDependencyExtractor(DependencyExtractor):
    component_type = "Layout"

    def can_extract(self, component_type: str) -> bool:
        return component_type == "Layout"

    async def extract(
        self,
        graph: DependencyGraph,
        component_name: str,
        parsed: Any,
        _raw: dict[str, Any] | None = None,
    ) -> DependencyGraph:
        if not isinstance(parsed, Layout):
            return graph

        source = graph.add_node(DependencyNode(
            component_type="Layout",
            component_name=component_name,
            component_id=parsed.component_id,
        ))

        if parsed.object_type:
            obj_node = graph.add_node(DependencyNode(
                component_type="CustomObject",
                component_name=parsed.object_type,
            ))
            graph.add_edge(DependencyEdge(
                source=source, target=obj_node,
                dependency_type=DependencyType.USES_OBJECT,
            ))

        for section in parsed.sections:
            items = section.layout_columns or []
            for col in items:
                for item in col.items if hasattr(col, "items") else []:
                    if item.field and "." in item.field:
                        parts = item.field.split(".")
                        obj_node = graph.add_node(DependencyNode(
                            component_type="CustomObject",
                            component_name=parts[0],
                        ))
                        graph.add_edge(DependencyEdge(
                            source=source, target=obj_node,
                            dependency_type=DependencyType.USES_OBJECT,
                            source_field=item.field,
                        ))

        for rl in parsed.related_lists:
            target = graph.add_node(DependencyNode(
                component_type="CustomObject",
                component_name=rl.object_name,
            ))
            graph.add_edge(DependencyEdge(
                source=source, target=target,
                dependency_type=DependencyType.USES_OBJECT,
            ))

        return graph
