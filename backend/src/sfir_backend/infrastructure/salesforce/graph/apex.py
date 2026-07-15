from __future__ import annotations

import re
from typing import Any

from sfir_backend.domain.graph.models import (
    DependencyEdge,
    DependencyGraph,
    DependencyNode,
    DependencyType,
)
from sfir_backend.domain.metadata.apex import ApexClass, ApexTrigger
from sfir_backend.infrastructure.salesforce.graph.base import DependencyExtractor


class ApexDependencyExtractor(DependencyExtractor):
    component_type = "ApexClass"

    def can_extract(self, component_type: str) -> bool:
        return component_type in {"ApexClass", "ApexTrigger", "ApexPage", "ApexComponent"}

    async def extract(
        self,
        graph: DependencyGraph,
        component_name: str,
        parsed: Any,
        raw: dict[str, Any] | None = None,
    ) -> DependencyGraph:
        src_type = raw.get("Type", "ApexClass") if raw else "ApexClass"
        source = graph.add_node(DependencyNode(
            component_type=src_type,
            component_name=component_name,
            component_id=parsed.component_id if hasattr(parsed, "component_id") else None,
        ))

        if isinstance(parsed, (ApexClass, ApexTrigger)):
            body = parsed.body
        elif isinstance(parsed, str):
            body = parsed
        elif hasattr(parsed, "body"):
            body = parsed.body
        elif isinstance(parsed, dict):
            body = parsed.get("Body", "")
        else:
            body = ""

        if body:
            self._extract_extends(source, body, graph)
            self._extract_implements(source, body, graph)
            self._extract_class_refs(source, body, graph)
            self._extract_object_refs(source, body, graph)

        if isinstance(parsed, ApexTrigger) and parsed.object_type:
            trigger_target = graph.add_node(DependencyNode(
                component_type="CustomObject",
                component_name=parsed.object_type,
            ))
            graph.add_edge(DependencyEdge(
                source=source,
                target=trigger_target,
                dependency_type=DependencyType.USES_OBJECT,
            ))

        return graph

    def _extract_extends(
        self, source: DependencyNode, body: str, graph: DependencyGraph,
    ) -> None:
        m = re.search(r"(?:class|interface)\s+\w+\s+extends\s+(\w+)", body)
        if m:
            target_name = m.group(1)
            target = graph.add_node(DependencyNode(
                component_type="ApexClass",
                component_name=target_name,
            ))
            graph.add_edge(DependencyEdge(
                source=source, target=target,
                dependency_type=DependencyType.EXTENDS,
            ))

    def _extract_implements(
        self, source: DependencyNode, body: str, graph: DependencyGraph,
    ) -> None:
        m = re.search(r"class\s+\w+\s+implements\s+([\w,\s]+)", body)
        if m:
            for iface in re.split(r"[\s,]+", m.group(1).strip()):
                if iface:
                    target = graph.add_node(DependencyNode(
                        component_type="ApexClass",
                        component_name=iface,
                    ))
                    graph.add_edge(DependencyEdge(
                        source=source, target=target,
                        dependency_type=DependencyType.IMPLEMENTS,
                    ))

    def _extract_class_refs(
        self, source: DependencyNode, body: str, graph: DependencyGraph,
    ) -> None:
        ref_pattern = re.compile(r"\b([A-Z]\w*)\b\.\s*\w+\s*\(")
        seen: set[str] = set()
        builtins = {
            "System", "String", "Integer", "Boolean", "Long", "Double",
            "Decimal", "Date", "Datetime", "Time", "Id", "Blob",
            "Object", "Set", "List", "Map", "SObject",
            "Schema", "JSON", "Math", "Test", "PageReference",
            "Type", "Pattern", "EncodingUtil", "Url", "null", "true", "false",
        }
        for m in ref_pattern.finditer(body):
            ref = m.group(1)
            if ref not in builtins and ref not in seen:
                seen.add(ref)
                target = graph.add_node(DependencyNode(
                    component_type="ApexClass",
                    component_name=ref,
                ))
                graph.add_edge(DependencyEdge(
                    source=source, target=target,
                    dependency_type=DependencyType.USES_CLASS,
                ))

    def _extract_object_refs(
        self, source: DependencyNode, body: str, graph: DependencyGraph,
    ) -> None:
        patterns = [
            (r"\bINSERT\s+(\w+)", DependencyType.USES_OBJECT),
            (r"\bUPDATE\s+(\w+)", DependencyType.USES_OBJECT),
            (r"\bUPSERT\s+(\w+)", DependencyType.USES_OBJECT),
            (r"\bDELETE\s+(\w+)", DependencyType.USES_OBJECT),
            (r"\[SELECT\s+.*?\s+FROM\s+(\w+)", DependencyType.USES_OBJECT),
        ]
        seen: set[str] = set()
        for pat, dep_type in patterns:
            for m in re.finditer(pat, body, re.IGNORECASE | re.DOTALL):
                obj = m.group(1)
                if obj not in seen and obj[0].isupper():
                    seen.add(obj)
                    target = graph.add_node(DependencyNode(
                        component_type="CustomObject",
                        component_name=obj,
                    ))
                    graph.add_edge(DependencyEdge(
                        source=source, target=target,
                        dependency_type=dep_type,
                    ))
