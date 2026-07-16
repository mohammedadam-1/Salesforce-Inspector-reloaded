from __future__ import annotations

from typing import Any

from sfir_backend.domain.graph.models import Graph, NodeType
from sfir_backend.domain.impact.models import (
    AffectedComponent,
    ImpactSeverity,
    ImpactStatus,
)


class RelationshipAnalyzer:
    def analyze_relationships(
        self,
        graph: Graph,
        component_key: str,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        node = graph.get_node(component_key)
        if not node:
            return results

        for edge in graph.get_outgoing_edges(component_key):
            target = graph.get_node(edge.target_id)
            if target:
                results.append({
                    "relation": "depends_on",
                    "key": edge.target_id,
                    "type": target.node_type.value if target.node_type else "unknown",
                    "edge_type": edge.edge_type.value if edge.edge_type else "unknown",
                    "name": target.api_name,
                })

        for edge in graph.get_incoming_edges(component_key):
            source = graph.get_node(edge.source_id)
            if source:
                results.append({
                    "relation": "depended_by",
                    "key": edge.source_id,
                    "type": source.node_type.value if source.node_type else "unknown",
                    "edge_type": edge.edge_type.value if edge.edge_type else "unknown",
                    "name": source.api_name,
                })

        return results

    def find_permission_impact(
        self,
        graph: Graph,
        component_key: str,
    ) -> list[AffectedComponent]:
        affected: list[AffectedComponent] = []
        for edge in graph.get_incoming_edges(component_key):
            source = graph.get_node(edge.source_id)
            if source and source.node_type in (
                NodeType.PERMISSION_SET,
                NodeType.PROFILE,
            ):
                affected.append(AffectedComponent(
                    component_key=edge.source_id,
                    name=source.api_name,
                    component_type=source.node_type.value if source.node_type else "unknown",
                    severity=ImpactSeverity.HIGH,
                    status=ImpactStatus.WARNING,
                    dependency_depth=1,
                ))
        return affected

    def find_layout_impact(
        self,
        graph: Graph,
        component_key: str,
    ) -> list[AffectedComponent]:
        affected: list[AffectedComponent] = []
        for edge in graph.get_incoming_edges(component_key):
            source = graph.get_node(edge.source_id)
            if source and source.node_type == NodeType.LAYOUT:
                affected.append(AffectedComponent(
                    component_key=edge.source_id,
                    name=source.api_name,
                    component_type="layout",
                    severity=ImpactSeverity.MEDIUM,
                    status=ImpactStatus.SAFE,
                    dependency_depth=1,
                ))
        return affected

    def find_report_dashboard_impact(
        self,
        graph: Graph,
        component_key: str,
    ) -> list[AffectedComponent]:
        affected: list[AffectedComponent] = []
        visited: set[str] = set()

        def collect(nk: str, depth: int) -> None:
            if nk in visited or depth > 3:
                return
            visited.add(nk)
            for edge in graph.get_incoming_edges(nk):
                source = graph.get_node(edge.source_id)
                if not source:
                    continue
                st = source.node_type.value if source.node_type else ""
                if st in ("report", "dashboard"):
                    sev = ImpactSeverity.MEDIUM if st == "report" else ImpactSeverity.LOW
                    affected.append(AffectedComponent(
                        component_key=edge.source_id,
                        name=source.api_name,
                        component_type=st,
                        severity=sev,
                        status=ImpactStatus.SAFE,
                        dependency_depth=depth,
                    ))
                collect(edge.source_id, depth + 1)

        collect(component_key, 1)
        return affected
