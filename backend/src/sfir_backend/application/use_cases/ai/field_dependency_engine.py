from __future__ import annotations

import uuid
from typing import Any

import structlog

from sfir_backend.application.use_cases.graph.service import GraphService

logger = structlog.get_logger(__name__)


class FieldDependencyEngine:
    def __init__(self, graph_service: GraphService) -> None:
        self._graph_service = graph_service

    async def find_field_references(
        self,
        organization_id: uuid.UUID,
        object_name: str,
        field_name: str,
    ) -> list[dict[str, Any]]:
        graph = await self._graph_service.build_graph(organization_id)
        if not graph:
            return []

        references: list[dict[str, Any]] = []

        for node_id, node in graph.nodes.items():
            if node.component_type == "CustomField":
                continue

            body = (node.properties or {}).get("body", "") or ""
            if not body and hasattr(node, "metadata"):
                body = node.metadata or ""

            if isinstance(body, dict):
                continue

            body_lower = body.lower()
            object_lower = object_name.lower()
            field_lower = field_name.lower()

            object_field_pattern = f"{object_lower}.{field_lower}"

            if object_field_pattern in body_lower:
                references.append({
                    "component_type": node.component_type,
                    "component_name": node.component_name,
                    "reference_type": "direct_reference",
                    "field": f"{object_name}.{field_name}",
                    "confidence": "high",
                })
                continue

            if field_lower in body_lower and object_lower in body_lower:
                references.append({
                    "component_type": node.component_type,
                    "component_name": node.component_name,
                    "reference_type": "co_occurrence",
                    "field": f"{object_name}.{field_name}",
                    "confidence": "medium",
                })

        return references

    async def find_object_references(
        self,
        organization_id: uuid.UUID,
        object_name: str,
    ) -> list[dict[str, Any]]:
        graph = await self._graph_service.build_graph(organization_id)
        if not graph:
            return []

        references: list[dict[str, Any]] = []

        object_lower = object_name.lower()

        for node_id, node in graph.nodes.items():
            body = (node.properties or {}).get("body", "") or ""
            if not body and hasattr(node, "metadata"):
                body = node.metadata or ""

            if isinstance(body, dict):
                continue

            if object_lower in body.lower():
                references.append({
                    "component_type": node.component_type,
                    "component_name": node.component_name,
                    "object": object_name,
                    "confidence": "high" if self._is_direct_reference(body, object_lower) else "medium",
                })

        upstream, downstream = [], []
        try:
            deps = await self._graph_service.get_node_dependencies(
                graph, "CustomObject", object_name, depth=2,
            )
            upstream = deps.get("upstream", [])
            downstream = deps.get("downstream", [])
        except Exception:
            logger.warning("dependency_lookup_failed", object_name=object_name)

        return {
            "text_references": references[:100],
            "graph_upstream": upstream,
            "graph_downstream": downstream,
        }

    def _is_direct_reference(self, body: str, object_lower: str) -> bool:
        body_lower = body.lower()
        import re
        patterns = [
            rf"\b{re.escape(object_lower)}\.",       # Object.Field
            rf"from\s+{re.escape(object_lower)}\b",    # FROM Object (SOQL)
            rf"(?:select|update|delete\s+from)\s+{re.escape(object_lower)}\b",
        ]
        return any(re.search(p, body_lower) for p in patterns)

    async def resolve_cross_object_field(
        self,
        organization_id: uuid.UUID,
        source_object: str,
        source_field: str,
        target_object: str | None = None,
    ) -> list[dict[str, Any]]:
        refs = await self.find_field_references(organization_id, source_object, source_field)
        if target_object:
            refs = [r for r in refs if r.get("object", "").lower() == target_object.lower()]
        return refs[:50]
