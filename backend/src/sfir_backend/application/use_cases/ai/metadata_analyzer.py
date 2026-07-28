from __future__ import annotations

import uuid
from typing import Any

import structlog

from sfir_backend.application.use_cases.graph.service import GraphService
from sfir_backend.domain.graph.models import EdgeType
from sfir_backend.infrastructure.salesforce.parsers.registry import ParserRegistry
from sfir_backend.infrastructure.search.engine import SearchEngine

logger = structlog.get_logger(__name__)


class MetadataAnalyzer:
    def __init__(
        self,
        graph_service: GraphService,
        search_engine: SearchEngine | None = None,
        parser_registry: ParserRegistry | None = None,
    ) -> None:
        self._graph_service = graph_service
        self._search_engine = search_engine
        self._parser_registry = parser_registry

    async def analyze_object(
        self,
        organization_id: uuid.UUID,
        object_name: str,
    ) -> dict[str, Any]:
        graph = await self._graph_service.build_graph(organization_id)
        if not graph:
            return {"error": "Graph not available"}

        obj_lower = object_name.lower()
        obj_node: Any = None
        fields: list[dict[str, Any]] = []
        outgoing_edges: list[Any] = []
        incoming_edges: list[Any] = []

        for node_key, node in graph.nodes.items():
            if node.node_type.value in ("object", "custom_object") and (
                node.api_name.lower() == obj_lower
            ):
                obj_node = node
                outgoing_edges = graph.get_outgoing_edges(node_key)
                incoming_edges = graph.get_incoming_edges(node_key)
                break

        if not obj_node:
            return await self._analyze_object_from_search(object_name)

        for edge in outgoing_edges:
            target_node = graph.get_node(edge.target_id)
            if target_node and target_node.node_type.value == "field":
                fields.append({
                    "name": target_node.api_name,
                    "type": edge.metadata.get("field_type", "unknown"),
                    "is_required": edge.metadata.get("required", False),
                    "is_unique": edge.metadata.get("unique", False),
                })

        for edge in incoming_edges:
            source_node = graph.get_node(edge.source_id)
            if source_node and source_node.node_type.value in ("field", "custom_field"):
                fields.append({
                    "name": source_node.api_name,
                    "type": "lookup",
                    "is_required": False,
                    "relationship": edge.edge_type.value,
                })

        obj_metadata = obj_node.metadata or {}
        return {
            "api_name": object_name,
            "label": obj_node.label or obj_node.api_name,
            "description": obj_node.description or "",
            "field_count": len(fields),
            "fields_sample": fields[:30],
            "total_outgoing_edges": len(outgoing_edges),
            "total_incoming_edges": len(incoming_edges),
            "referenced_by_objects": [
                graph.get_node(e.source_id).api_name
                for e in incoming_edges
                if graph.get_node(e.source_id) and graph.get_node(e.source_id).node_type.value in ("object", "custom_object")
            ][:20],
            "references_objects": [
                graph.get_node(e.target_id).api_name
                for e in outgoing_edges
                if graph.get_node(e.target_id) and graph.get_node(e.target_id).node_type.value in ("object", "custom_object")
            ][:20],
            "trigger_on": [
                graph.get_node(e.source_id).api_name
                for e in incoming_edges
                if graph.get_node(e.source_id) and graph.get_node(e.source_id).node_type.value in ("trigger", "apex_trigger")
            ],
            "has_apex_triggers": any(
                e.edge_type == EdgeType.TRIGGER_ON
                for e in incoming_edges
            ),
            "layout_count": sum(
                1 for e in incoming_edges
                if graph.get_node(e.source_id) and graph.get_node(e.source_id).node_type.value == "layout"
            ),
            "validation_rule_count": sum(
                1 for e in incoming_edges
                if graph.get_node(e.source_id) and graph.get_node(e.source_id).node_type.value == "validation_rule"
            ),
        }

    async def _analyze_object_from_search(
        self,
        object_name: str,
    ) -> dict[str, Any]:
        if not self._search_engine:
            return {"error": f"Object '{object_name}' not found"}
        try:
            search = self._search_engine.search_metadata(
                query=object_name,
                metadata_types=["CustomObject"],
                limit=5,
            )
            docs = search.documents
            if docs:
                doc = docs[0]
                return {
                    "api_name": object_name,
                    "label": doc.label or object_name,
                    "description": doc.description or "",
                    "field_count": len(doc.metadata_properties or {}),
                    "from_search": True,
                }
        except Exception:
            pass
        return {"error": f"Object '{object_name}' not found"}

    async def analyze_field(
        self,
        organization_id: uuid.UUID,
        object_name: str,
        field_name: str,
    ) -> dict[str, Any]:
        graph = await self._graph_service.build_graph(organization_id)
        if not graph:
            return {"error": "Graph not available"}

        obj_lower = object_name.lower()
        field_lower = field_name.lower()
        qualified = f"{object_name}.{field_name}"

        result: dict[str, Any] = {
            "field": qualified,
            "api_name": field_name,
            "object_name": object_name,
            "field_type": "unknown",
            "is_required": False,
            "is_unique": False,
            "picklist_values": [],
            "referenced_by": [],
            "formula_refs": [],
        }

        for node_key, node in graph.nodes.items():
            if node.node_type.value not in ("field", "custom_field"):
                continue
            if field_lower not in node.api_name.lower():
                continue
            if obj_lower in node_key.lower():
                meta = node.metadata or {}
                result["field_type"] = meta.get("type", meta.get("field_type", "unknown"))
                result["is_required"] = meta.get("required", False)
                result["is_unique"] = meta.get("unique", False)
                result["label"] = node.label or field_name
                result["description"] = node.description or ""
                picklist = meta.get("picklist", meta.get("values", []))
                if isinstance(picklist, list):
                    result["picklist_values"] = picklist[:20]
                if isinstance(picklist, str):
                    result["picklist_string"] = picklist

        outgoing_edges = graph.get_outgoing_edges(f"CustomField:{qualified}")
        outgoing_edges.extend(graph.get_outgoing_edges(f"field:{qualified}"))

        for edge in outgoing_edges:
            source_node = graph.get_node(edge.source_id)
            if source_node:
                result["referenced_by"].append({
                    "component": f"{source_node.node_type.value}:{source_node.api_name}",
                    "edge_type": edge.edge_type.value,
                })

        return result

    async def analyze_flow(
        self,
        organization_id: uuid.UUID,
        flow_name: str,
    ) -> dict[str, Any]:
        graph = await self._graph_service.build_graph(organization_id)
        if not graph:
            return {"error": "Graph not available"}

        flow_node: Any = None
        for nkey, node in graph.nodes.items():
            if node.node_type.value in ("flow", "flow_version") and (
                node.api_name.lower() == flow_name.lower()
            ):
                flow_node = node
                break

        if not flow_node:
            return {"error": f"Flow '{flow_name}' not found"}

        node_key = f"{flow_node.node_type.value}:{flow_node.api_name}"
        outgoing = graph.get_outgoing_edges(node_key)
        incoming = graph.get_incoming_edges(node_key)

        metadata = flow_node.metadata or {}
        body = metadata.get("body", "") if isinstance(metadata, dict) else ""

        return {
            "api_name": flow_name,
            "label": flow_node.label or flow_name,
            "description": flow_node.description or "",
            "objects_used": [
                graph.get_node(e.target_id).api_name
                for e in outgoing
                if graph.get_node(e.target_id) and graph.get_node(e.target_id).node_type.value in ("object", "custom_object")
            ],
            "subflows": [
                graph.get_node(e.target_id).api_name
                for e in outgoing
                if graph.get_node(e.target_id) and graph.get_node(e.target_id).node_type.value in ("flow", "flow_version")
            ],
            "apex_actions": [
                graph.get_node(e.target_id).api_name
                for e in outgoing
                if graph.get_node(e.target_id) and e.edge_type == EdgeType.INVOKES
            ],
            "trigger_type": metadata.get("trigger_type", metadata.get("process_type", "unknown")),
            "elements_estimated": max(1, body.count("FlowElement")),
            "decisions_estimated": body.count("Decision"),
            "record_creates": body.count("RecordCreate"),
            "record_updates": body.count("RecordUpdate"),
            "record_deletes": body.count("RecordDelete"),
            "is_active": metadata.get("active", metadata.get("status", "")) in ("true", "Active", "Draft"),
            "referenced_by_flows": [
                graph.get_node(e.source_id).api_name
                for e in incoming
                if graph.get_node(e.source_id) and graph.get_node(e.source_id).node_type.value in ("flow", "flow_version")
            ],
        }

    async def analyze_apex_class(
        self,
        organization_id: uuid.UUID,
        class_name: str,
    ) -> dict[str, Any]:
        graph = await self._graph_service.build_graph(organization_id)
        if not graph:
            return {"error": "Graph not available"}

        apex_node: Any = None
        for nkey, node in graph.nodes.items():
            if node.node_type.value in ("apex_class", "trigger") and (
                node.api_name.lower() == class_name.lower()
            ):
                apex_node = node
                break

        if not apex_node:
            return {"error": f"Apex class '{class_name}' not found"}

        node_key = f"{apex_node.node_type.value}:{apex_node.api_name}"
        outgoing = graph.get_outgoing_edges(node_key)
        incoming = graph.get_incoming_edges(node_key)

        body = self._get_body(apex_node)
        import re

        method_pattern = re.compile(
            r"(?:public|private|global|protected|static|virtual|override|abstract)?\s*"
            r"(?:public|private|global|protected|static|virtual|override|abstract)?\s*"
            r"(\w+(?:\[\])?)\s+(\w+)\s*\(",
        )

        methods: list[str] = []
        for m in method_pattern.finditer(body):
            methods.append(m.group(2))

        soql_count = body.upper().count("SELECT") if body else 0
        dml_count = sum(body.upper().count(kw) for kw in ("INSERT", "UPDATE", "DELETE", "UPSERT")) if body else 0
        line_count = body.count("\n") + 1 if body else 0

        return {
            "api_name": class_name,
            "label": apex_node.label or class_name,
            "description": apex_node.description or "",
            "type": apex_node.node_type.value,
            "line_count": line_count,
            "method_count": len(methods),
            "methods": methods[:30],
            "soql_count": soql_count,
            "dml_count": dml_count,
            "extends": [
                graph.get_node(e.target_id).api_name
                for e in outgoing
                if e.edge_type == EdgeType.EXTENDS and graph.get_node(e.target_id)
            ],
            "implements": [
                graph.get_node(e.target_id).api_name
                for e in outgoing
                if e.edge_type == EdgeType.IMPLEMENTS and graph.get_node(e.target_id)
            ],
            "classes_used": [
                graph.get_node(e.target_id).api_name
                for e in outgoing
                if e.edge_type in (EdgeType.APEX_REFERENCE, EdgeType.REFERENCES)
                and graph.get_node(e.target_id)
            ],
            "objects_referenced": [
                graph.get_node(e.target_id).api_name
                for e in outgoing
                if graph.get_node(e.target_id) and graph.get_node(e.target_id).node_type.value in ("object", "custom_object")
            ],
            "used_by": [
                f"{graph.get_node(e.source_id).node_type.value}:{graph.get_node(e.source_id).api_name}"
                for e in incoming
                if graph.get_node(e.source_id)
            ],
        }

    async def analyze_validation_rule(
        self,
        organization_id: uuid.UUID,
        rule_name: str,
    ) -> dict[str, Any]:
        graph = await self._graph_service.build_graph(organization_id)
        if not graph:
            return {"error": "Graph not available"}

        rule_node: Any = None
        for nkey, node in graph.nodes.items():
            if node.node_type.value == "validation_rule" and (
                rule_name.lower() in node.api_name.lower()
            ):
                rule_node = node
                break

        if not rule_node:
            return {"error": f"Validation rule '{rule_name}' not found"}

        body = self._get_body(rule_node)
        import re
        refs = re.findall(r"\b([A-Z]\w*__c)\b", body)
        obj_refs = re.findall(r"\b([A-Z]\w*)\.\w+__c\b", body)

        return {
            "api_name": rule_node.api_name,
            "description": rule_node.description or "",
            "formula_body": body[:2000],
            "field_references": list(set(refs))[:30],
            "object_references": list(set(obj_refs))[:10],
            "formula_length": len(body),
        }

    async def analyze_profile(
        self,
        organization_id: uuid.UUID,
        profile_name: str,
    ) -> dict[str, Any]:
        graph = await self._graph_service.build_graph(organization_id)
        if not graph:
            return {"error": "Graph not available"}

        profile_node: Any = None
        for nkey, node in graph.nodes.items():
            if node.node_type.value in ("profile", "permission_set") and (
                node.api_name.lower() == profile_name.lower()
            ):
                profile_node = node
                break

        if not profile_node:
            return {"error": f"Profile/permission set '{profile_name}' not found"}

        node_key = f"{profile_node.node_type.value}:{profile_node.api_name}"
        outgoing = graph.get_outgoing_edges(node_key)

        return {
            "api_name": profile_name,
            "label": profile_node.label or profile_name,
            "description": profile_node.description or "",
            "type": profile_node.node_type.value,
            "permissions_granted": [
                f"{graph.get_node(e.target_id).node_type.value}:{graph.get_node(e.target_id).api_name}"
                for e in outgoing
                if graph.get_node(e.target_id)
            ][:50],
        }

    async def analyze_layout(
        self,
        organization_id: uuid.UUID,
        layout_name: str,
    ) -> dict[str, Any]:
        graph = await self._graph_service.build_graph(organization_id)
        if not graph:
            return {"error": "Graph not available"}

        layout_node: Any = None
        for nkey, node in graph.nodes.items():
            if node.node_type.value == "layout" and (
                layout_name.lower() in node.api_name.lower()
            ):
                layout_node = node
                break

        if not layout_node:
            return {"error": f"Layout '{layout_name}' not found"}

        node_key = f"{layout_node.node_type.value}:{layout_node.api_name}"
        outgoing = graph.get_outgoing_edges(node_key)

        return {
            "api_name": layout_node.api_name,
            "description": layout_node.description or "",
            "related_objects": [
                graph.get_node(e.target_id).api_name
                for e in outgoing
                if graph.get_node(e.target_id) and graph.get_node(e.target_id).node_type.value in ("object", "custom_object", "field")
            ],
            "sections_estimated": self._estimate_layout_sections(layout_node),
        }

    async def analyze_report(
        self,
        organization_id: uuid.UUID,
        report_name: str,
    ) -> dict[str, Any]:
        graph = await self._graph_service.build_graph(organization_id)
        if not graph:
            return {"error": "Graph not available"}

        report_node: Any = None
        for nkey, node in graph.nodes.items():
            if node.node_type.value == "report" and (
                report_name.lower() in node.api_name.lower()
            ):
                report_node = node
                break

        if not report_node:
            return {"error": f"Report '{report_name}' not found"}

        node_key = f"{report_node.node_type.value}:{report_node.api_name}"
        outgoing = graph.get_outgoing_edges(node_key)

        return {
            "api_name": report_node.api_name,
            "description": report_node.description or "",
            "referenced_objects": [
                f"{graph.get_node(e.target_id).node_type.value}:{graph.get_node(e.target_id).api_name}"
                for e in outgoing
                if graph.get_node(e.target_id)
            ],
        }

    def _get_body(self, node: Any) -> str:
        metadata = node.metadata or {}
        body = metadata.get("body", "") if isinstance(metadata, dict) else ""
        if not body:
            body = node.description or ""
        if isinstance(body, dict):
            body = ""
        return str(body)

    def _estimate_layout_sections(self, node: Any) -> int:
        body = self._get_body(node)
        import re
        sections = re.findall(r"<sections>|<layoutSection", body)
        return len(sections) if sections else 1
