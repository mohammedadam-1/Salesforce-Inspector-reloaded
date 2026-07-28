from __future__ import annotations

import re
import uuid
from typing import Any

import structlog

from sfir_backend.application.use_cases.graph.service import GraphService
from sfir_backend.domain.graph.models import DependencyGraph, EdgeType

logger = structlog.get_logger(__name__)


class DependencyAnalyzer:
    def __init__(self, graph_service: GraphService) -> None:
        self._graph_service = graph_service

    async def analyze_all_references(
        self,
        organization_id: uuid.UUID,
        component_type: str,
        component_name: str,
        depth: int = 2,
    ) -> dict[str, Any]:
        graph = await self._graph_service.build_graph(organization_id)
        if not graph:
            return {"error": "Graph not available"}

        node_key = f"{component_type}:{component_name}"
        node = graph.get_node(node_key)

        upstream = graph.get_upstream(node_key, depth)
        downstream = graph.get_downstream(node_key, depth)

        outgoing_edges = graph.get_outgoing_edges(node_key)
        incoming_edges = graph.get_incoming_edges(node_key)

        deps_by_type: dict[str, list[str]] = {}
        for edge in outgoing_edges:
            t = edge.edge_type.value
            if t not in deps_by_type:
                deps_by_type[t] = []
            target_key = edge.target_id
            target_node = graph.get_node(target_key)
            if target_node:
                deps_by_type[t].append(f"{target_node.node_type.value}:{target_node.api_name}")

        refs_by_type: dict[str, list[str]] = {}
        for edge in incoming_edges:
            t = edge.edge_type.value
            if t not in refs_by_type:
                refs_by_type[t] = []
            source_key = edge.source_id
            source_node = graph.get_node(source_key)
            if source_node:
                refs_by_type[t].append(f"{source_node.node_type.value}:{source_node.api_name}")

        return {
            "component": f"{component_type}:{component_name}",
            "found_in_graph": node is not None,
            "upstream_count": len(upstream),
            "downstream_count": len(downstream),
            "upstream": [
                {"type": n.node_type.value, "name": n.api_name}
                for n in upstream
            ],
            "downstream": [
                {"type": n.node_type.value, "name": n.api_name}
                for n in downstream
            ],
            "dependencies_by_type": deps_by_type,
            "references_by_type": refs_by_type,
        }

    async def analyze_field_references(
        self,
        organization_id: uuid.UUID,
        object_name: str,
        field_name: str,
    ) -> list[dict[str, Any]]:
        graph = await self._graph_service.build_graph(organization_id)
        if not graph:
            return []

        pattern = f"{object_name}.{field_name}"
        pattern_lower = pattern.lower()
        obj_lower = object_name.lower()
        field_lower = field_name.lower()

        references: list[dict[str, Any]] = []
        seen: set[str] = set()

        for node_key, node in graph.nodes.items():
            body = self._get_node_body(node)
            if not body:
                continue

            body_lower = body.lower()

            if pattern_lower in body_lower:
                ref_type = self._classify_field_reference(body_lower, pattern_lower)
                if node_key not in seen:
                    seen.add(node_key)
                    references.append({
                        "component_type": node.node_type.value,
                        "component_name": node.api_name,
                        "field": pattern,
                        "reference_type": ref_type,
                        "confidence": "high" if ref_type == "direct_reference" else "medium",
                    })
                continue

            if field_lower in body_lower and obj_lower in body_lower:
                if node_key not in seen:
                    seen.add(node_key)
                    references.append({
                        "component_type": node.node_type.value,
                        "component_name": node.api_name,
                        "field": pattern,
                        "reference_type": "co_occurrence",
                        "confidence": "medium",
                    })

            outgoing = graph.get_outgoing_edges(node_key)
            for edge in outgoing:
                if edge.edge_type == EdgeType.FORMULA_REFERENCE and pattern_lower in edge.metadata.get("formula", "").lower():
                    if node_key not in seen:
                        seen.add(node_key)
                        references.append({
                            "component_type": node.node_type.value,
                            "component_name": node.api_name,
                            "field": pattern,
                            "reference_type": "formula_reference",
                            "confidence": "high",
                        })

        return references

    async def analyze_flow_dependencies(
        self,
        organization_id: uuid.UUID,
        flow_name: str,
    ) -> dict[str, Any]:
        graph = await self._graph_service.build_graph(organization_id)
        if not graph:
            return {"error": "Graph not available"}

        node_key = f"Flow:{flow_name}"
        node = graph.get_node(node_key)
        if not node:
            node_key = f"flow:{flow_name}"
            node = graph.get_node(node_key)
        if not node:
            return {"error": f"Flow '{flow_name}' not found"}

        upstream = graph.get_upstream(node_key, 2)
        downstream = graph.get_downstream(node_key, 2)
        outgoing = graph.get_outgoing_edges(node_key)
        incoming = graph.get_incoming_edges(node_key)

        objects_used: list[str] = []
        subflows: list[str] = []
        apex_called: list[str] = []

        for edge in outgoing:
            target_node = graph.get_node(edge.target_id)
            if not target_node:
                continue
            if target_node.node_type.value in ("object", "custom_object"):
                objects_used.append(target_node.api_name)
            elif edge.edge_type == EdgeType.INVOKES:
                apex_called.append(f"{target_node.node_type.value}:{target_node.api_name}")
            elif "Flow:" in edge.target_id or "flow:" in edge.target_id:
                subflows.append(target_node.api_name)

        metadata = node.metadata or {}
        body = metadata.get("body", "") or metadata.get("description", "") or ""

        elements_count = body.count("FlowElement") if body else 0
        decision_count = body.count("Decision") if body else 0
        record_create_count = body.count("RecordCreate") if body else 0
        record_update_count = body.count("RecordUpdate") if body else 0

        return {
            "flow_name": flow_name,
            "objects_used": list(set(objects_used)),
            "subflows": list(set(subflows)),
            "apex_actions": list(set(apex_called)),
            "elements_estimated": elements_count,
            "decisions_estimated": decision_count,
            "record_operations_estimated": record_create_count + record_update_count,
            "upstream_dependencies": [f"{n.node_type.value}:{n.api_name}" for n in upstream],
            "downstream_dependents": [f"{n.node_type.value}:{n.api_name}" for n in downstream],
            "total_dependencies": len(upstream) + len(downstream),
        }

    async def analyze_apex_references(
        self,
        organization_id: uuid.UUID,
        class_name: str,
    ) -> dict[str, Any]:
        graph = await self._graph_service.build_graph(organization_id)
        if not graph:
            return {"error": "Graph not available"}

        for node_type_prefix in ("ApexClass", "ApexTrigger", "apex_class", "trigger"):
            node_key = f"{node_type_prefix}:{class_name}"
            node = graph.get_node(node_key)
            if node:
                break
        else:
            return {"error": f"Apex class '{class_name}' not found"}

        upstream = graph.get_upstream(node_key, 2)
        downstream = graph.get_downstream(node_key, 2)
        outgoing = graph.get_outgoing_edges(node_key)
        incoming = graph.get_incoming_edges(node_key)

        extends: list[str] = []
        implements: list[str] = []
        classes_used: list[str] = []
        objects_referenced: list[str] = []

        for edge in outgoing:
            target_node = graph.get_node(edge.target_id)
            if not target_node:
                continue
            name = f"{target_node.node_type.value}:{target_node.api_name}"
            if edge.edge_type == EdgeType.EXTENDS:
                extends.append(name)
            elif edge.edge_type == EdgeType.IMPLEMENTS:
                implements.append(name)
            elif edge.edge_type in (EdgeType.APEX_REFERENCE, EdgeType.REFERENCES):
                classes_used.append(name)
            elif edge.edge_type == EdgeType.SOQL_REFERENCE:
                objects_referenced.append(target_node.api_name)
            elif target_node.node_type.value in ("object", "custom_object"):
                objects_referenced.append(target_node.api_name)

        return {
            "class_name": class_name,
            "extends": extends,
            "implements": implements,
            "classes_used": list(set(classes_used)),
            "objects_referenced": list(set(objects_referenced)),
            "used_by": [f"{n.node_type.value}:{n.api_name}" for n in downstream],
            "uses": [f"{n.node_type.value}:{n.api_name}" for n in upstream],
            "outgoing_edge_count": len(outgoing),
            "incoming_edge_count": len(incoming),
        }

    async def analyze_cross_object_refs(
        self,
        organization_id: uuid.UUID,
        object_name: str,
    ) -> dict[str, Any]:
        graph = await self._graph_service.build_graph(organization_id)
        if not graph:
            return {"error": "Graph not available"}

        obj_lower = object_name.lower()
        results: dict[str, list[dict[str, str]]] = {}

        for node_key, node in graph.nodes.items():
            body = self._get_node_body(node)
            if not body or node.node_type.value in ("object", "field"):
                continue

            if obj_lower in body.lower():
                ntype = node.node_type.value
                if ntype not in results:
                    results[ntype] = []
                if len(results[ntype]) < 50:
                    results[ntype].append({
                        "name": node.api_name,
                        "reference": self._classify_object_reference(body, obj_lower),
                    })

        total = sum(len(v) for v in results.values())
        return {
            "object_name": object_name,
            "total_references": total,
            "component_types_referencing": list(results.keys()),
            "references_by_type": results,
            "top_referencing_types": sorted(
                results.items(), key=lambda x: -len(x[1]),
            )[:10],
        }

    async def extract_soql_sosl(
        self,
        organization_id: uuid.UUID,
        class_name: str | None = None,
    ) -> list[dict[str, Any]]:
        graph = await self._graph_service.build_graph(organization_id)
        if not graph:
            return []

        results: list[dict[str, Any]] = []

        soql_pattern = re.compile(
            r"\[SELECT\s+.*?\s+FROM\s+(\w+)(?:\s+.*?)?\]",
            re.IGNORECASE | re.DOTALL,
        )
        sosl_pattern = re.compile(
            r"\[FIND\s+.*?\s+(?:IN\s+\w+)?\s*RETURNING\s+(\w+)",
            re.IGNORECASE | re.DOTALL,
        )
        query_pattern = re.compile(
            r"Database\.query\(\s*'([^']+)'\s*\)",
            re.IGNORECASE | re.DOTALL,
        )
        count_pattern = re.compile(
            r"\[\s*SELECT\s+COUNT\(\s*\w*\s*\)\s+FROM\s+(\w+)",
            re.IGNORECASE | re.DOTALL,
        )

        for node_key, node in graph.nodes.items():
            if class_name and class_name.lower() not in node_key.lower():
                continue
            if node.node_type.value not in ("apex_class", "trigger", "ApexClass", "ApexTrigger"):
                continue

            body = self._get_node_body(node)
            if not body:
                continue

            for match in soql_pattern.finditer(body):
                results.append({
                    "component": f"{node.node_type.value}:{node.api_name}",
                    "type": "SOQL",
                    "object": match.group(1),
                    "full_query": match.group(0)[:200],
                })

            for match in sosl_pattern.finditer(body):
                results.append({
                    "component": f"{node.node_type.value}:{node.api_name}",
                    "type": "SOSL",
                    "object": match.group(1),
                    "full_query": match.group(0)[:200],
                })

            for match in query_pattern.finditer(body):
                query_text = match.group(1)
                obj_match = re.search(r"FROM\s+(\w+)", query_text, re.IGNORECASE)
                results.append({
                    "component": f"{node.node_type.value}:{node.api_name}",
                    "type": "DynamicSOQL",
                    "object": obj_match.group(1) if obj_match else "unknown",
                    "full_query": query_text[:200],
                })

            for match in count_pattern.finditer(body):
                results.append({
                    "component": f"{node.node_type.value}:{node.api_name}",
                    "type": "SOQL_Count",
                    "object": match.group(1),
                    "full_query": match.group(0)[:200],
                })

        return results

    async def analyze_lwc_imports(
        self,
        organization_id: uuid.UUID,
        lwc_name: str | None = None,
    ) -> list[dict[str, Any]]:
        graph = await self._graph_service.build_graph(organization_id)
        if not graph:
            return []

        results: list[dict[str, Any]] = []
        import_pattern = re.compile(
            r"import\s+\{?\s*(\w+(?:\s*,\s*\w+)*)\s*\}?\s+from\s+['\"]([^'\"]+)['\"]",
        )

        for node_key, node in graph.nodes.items():
            if lwc_name and lwc_name.lower() not in node_key.lower():
                continue
            if node.node_type.value not in ("lightning_page", "lightning_component"):
                continue

            body = self._get_node_body(node)
            if not body:
                continue

            for match in import_pattern.finditer(body):
                results.append({
                    "component": f"{node.node_type.value}:{node.api_name}",
                    "imports": match.group(1),
                    "from": match.group(2),
                })

        return results

    async def analyze_formula_references(
        self,
        organization_id: uuid.UUID,
        formula_field_name: str,
    ) -> list[dict[str, Any]]:
        graph = await self._graph_service.build_graph(organization_id)
        if not graph:
            return []

        references: list[dict[str, Any]] = []
        import re as _re

        for node_key, node in graph.nodes.items():
            body = self._get_node_body(node)
            if not body:
                continue

            if node.node_type.value == "formula":
                if formula_field_name.lower() in node.api_name.lower():
                    refs = _re.findall(r"\b([A-Z]\w*__c)\b", body)
                    refs += _re.findall(r"\b([A-Z]\w*\.\w+__c)\b", body)
                    references.append({
                        "formula_field": node.api_name,
                        "referenced_fields": list(set(refs)),
                        "formula_body": body[:500],
                    })

        return references

    def _get_node_body(self, node: Any) -> str:
        metadata = node.metadata or {}
        body = metadata.get("body", "") if isinstance(metadata, dict) else ""
        if not body:
            if hasattr(node, "description") and node.description:
                body = node.description
        if isinstance(body, dict):
            body = ""
        return str(body)

    def _classify_field_reference(self, body_lower: str, pattern_lower: str) -> str:
        if pattern_lower in body_lower and "." in pattern_lower:
            return "direct_reference"
        return "co_occurrence"

    def _classify_object_reference(self, body: str, obj_lower: str) -> str:
        body_lower = body.lower()
        patterns = [
            rf"(?:FROM|UPDATE|INSERT|UPSERT|DELETE\s+FROM)\s+{re.escape(obj_lower)}\b",
            rf"\b{re.escape(obj_lower)}\.",
            rf"(?:SELECT|FIND)\s+.*?\s+FROM\s+{re.escape(obj_lower)}\b",
        ]
        for p in patterns:
            if re.search(p, body_lower, re.IGNORECASE):
                return "direct_reference"
        return "co_occurrence"
