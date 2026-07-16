from __future__ import annotations

from typing import Any

from sfir_backend.domain.graph.models import Graph
from sfir_backend.domain.impact.models import (
    AnalysisType,
    ChangeType,
    ImpactAnalysis,
    ImpactSeverity,
    ImpactSummary,
    RecommendedAction,
    SimulationRequest,
    SimulationResult,
)
from sfir_backend.infrastructure.impact.analyzer import DependencyImpactAnalyzer
from sfir_backend.infrastructure.impact.blast_radius import BlastRadiusCalculator
from sfir_backend.infrastructure.impact.change import ChangeAnalyzer
from sfir_backend.infrastructure.impact.delete import DeleteAnalyzer
from sfir_backend.infrastructure.impact.deployment import DeploymentAnalyzer
from sfir_backend.infrastructure.impact.rename import RenameAnalyzer
from sfir_backend.infrastructure.impact.risk import RiskCalculator


class SimulationEngine:
    def __init__(
        self,
        impact_analyzer: DependencyImpactAnalyzer,
        delete_analyzer: DeleteAnalyzer,
        rename_analyzer: RenameAnalyzer,
        change_analyzer: ChangeAnalyzer,
        blast_calculator: BlastRadiusCalculator,
        risk_calculator: RiskCalculator,
        deployment_analyzer: DeploymentAnalyzer,
    ) -> None:
        self._impact = impact_analyzer
        self._delete = delete_analyzer
        self._rename = rename_analyzer
        self._change = change_analyzer
        self._blast = blast_calculator
        self._risk = risk_calculator
        self._deployment = deployment_analyzer

    def simulate(
        self,
        request: SimulationRequest,
        graph: Graph,
    ) -> SimulationResult:
        result_map: dict[str, Any] = {}

        if request.change_type == ChangeType.DELETE or request.simulate_delete:
            result_map = self._simulate_delete(request, graph)
        elif request.change_type == ChangeType.RENAME or request.simulate_rename:
            result_map = self._simulate_rename(request, graph)
        elif request.change_type in (ChangeType.MODIFY, ChangeType.VERSION_UPGRADE) \
                or request.simulate_modify:
            result_map = self._simulate_modify(request, graph)
        else:
            result_map = self._simulate_generic(request, graph)

        affected = result_map.get("affected", [])
        blast = result_map.get("blast_radius", self._blast.calculate(graph, request.component_key))
        risk = result_map.get("risk", self._risk.calculate(blast, "unknown"))
        warnings = result_map.get("warnings", [])
        actions = result_map.get("recommended_actions", [])
        blocking_count = sum(1 for c in affected if hasattr(c, 'status') and c.status == "blocking")

        summary = ImpactSummary(
            analysis_type=AnalysisType.SIMULATION,
            component_key=request.component_key,
            total_affected=blast.total_count,
            critical_count=sum(1 for c in affected if hasattr(c, 'severity') and c.severity == ImpactSeverity.CRITICAL),
            high_count=sum(1 for c in affected if hasattr(c, 'severity') and c.severity == ImpactSeverity.HIGH),
            blocking_count=blocking_count,
            max_depth=blast.max_depth,
            has_cycles=blast.has_circular_dependency,
            risk_score=risk.risk_score,
            risk_severity=risk.severity,
        )

        analysis = ImpactAnalysis(
            analysis_type=AnalysisType.SIMULATION,
            component_key=request.component_key,
            affected_components=affected,
            blast_radius=blast,
            risk_assessment=risk,
            summary=summary,
            warnings=warnings,
            recommended_actions=actions,
        )

        blocking = any(getattr(c, 'status', None) == "blocking" for c in affected)
        return SimulationResult(
            request=request,
            analysis=analysis,
            is_safe=not blocking and blast.total_count == 0,
            blocking_issues=[w for w in warnings if "blocking" in w.lower() or "critical" in w.lower()],
            warnings=warnings,
        )

    def _simulate_delete(
        self,
        request: SimulationRequest,
        graph: Graph,
    ) -> dict[str, Any]:
        key = request.component_key
        if not key or key not in graph.nodes:
            return {"affected": [], "blast_radius": self._blast.calculate(graph, key)}

        node = graph.nodes[key]
        node_type = node.node_type.value if node.node_type else ""

        if node_type == "field":
            parts = node.api_name.split(".")
            obj = parts[0] if len(parts) > 1 else ""
            field = parts[-1] if parts else ""
            return self._delete.analyze_field_delete(field, obj)
        if node_type == "object":
            return self._delete.analyze_object_delete(node.api_name)
        if node_type == "flow":
            return self._delete.analyze_flow_delete(node.api_name)
        if node_type == "apex_class":
            return self._delete.analyze_apex_delete(node.api_name)
        if node_type == "validation_rule":
            parts = node.api_name.split(".")
            obj = parts[0] if len(parts) > 1 else ""
            rule = parts[-1] if parts else ""
            return self._delete.analyze_validation_rule_delete(rule, obj)

        affected, paths = self._impact.find_impacted(
            key, change_type=ChangeType.DELETE, max_depth=10,
        )
        blast = self._blast.calculate(graph, key, max_depth=10)
        risk = self._risk.calculate(blast, node_type)
        return {
            "affected": affected,
            "paths": paths,
            "blast_radius": blast,
            "risk": risk,
            "warnings": [],
            "recommended_actions": [],
        }

    def _simulate_rename(
        self,
        request: SimulationRequest,
        graph: Graph,
    ) -> dict[str, Any]:
        key = request.component_key
        new_name = request.simulate_rename
        if not key or not new_name:
            return {"affected": [], "warnings": ["No rename target specified"]}

        node = graph.nodes.get(key)
        if not node:
            return {"affected": [], "warnings": [f"Component '{key}' not found"]}

        node_type = node.node_type.value if node.node_type else ""
        if node_type == "object":
            return self._rename.analyze_object_rename(node.api_name, new_name)
        if node_type == "field":
            parts = node.api_name.split(".")
            obj = parts[0] if len(parts) > 1 else ""
            return self._rename.analyze_field_rename(obj, parts[-1] if parts else "", new_name)

        affected, paths = self._impact.find_impacted(
            key, change_type=ChangeType.RENAME, max_depth=10,
        )
        blast = self._blast.calculate(graph, key, max_depth=10)
        risk = self._risk.calculate(blast, node_type)
        return {
            "affected": affected,
            "paths": paths,
            "blast_radius": blast,
            "risk": risk,
            "warnings": [f"Simulated rename of '{key}' to '{new_name}'"],
            "recommended_actions": [
                RecommendedAction(
                    action="update_references",
                    description=f"Update all references from '{key}' to '{new_name}'",
                    priority="high",
                ),
            ],
        }

    def _simulate_modify(
        self,
        request: SimulationRequest,
        graph: Graph,
    ) -> dict[str, Any]:
        return self._change.analyze_modify(request.component_key)

    def _simulate_generic(
        self,
        request: SimulationRequest,
        graph: Graph,
    ) -> dict[str, Any]:
        key = request.component_key
        affected, paths = self._impact.find_impacted(
            key, change_type=request.change_type, max_depth=10,
        )
        blast = self._blast.calculate(graph, key, max_depth=10)
        return {
            "affected": affected,
            "paths": paths,
            "blast_radius": blast,
            "risk": self._risk.calculate(blast, "unknown"),
            "warnings": [],
            "recommended_actions": [],
        }
