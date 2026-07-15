from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from sfir_backend.domain.graph.models import Graph
from sfir_backend.domain.impact.models import (
    AffectedComponent,
    AnalysisType,
    BlastRadius,
    ChangeType,
    DeploymentReadiness,
    ImpactAnalysis,
    ImpactReport,
    ImpactSeverity,
    ImpactSummary,
    RecommendedAction,
    RiskAssessment,
    SimulationRequest,
    SimulationResult,
)
from sfir_backend.infrastructure.graph.engine import DependencyGraphEngine
from sfir_backend.infrastructure.impact.analyzer import DependencyImpactAnalyzer
from sfir_backend.infrastructure.impact.blast_radius import BlastRadiusCalculator
from sfir_backend.infrastructure.impact.change import ChangeAnalyzer
from sfir_backend.infrastructure.impact.delete import DeleteAnalyzer
from sfir_backend.infrastructure.impact.deployment import DeploymentAnalyzer
from sfir_backend.infrastructure.impact.relationship import RelationshipAnalyzer
from sfir_backend.infrastructure.impact.rename import RenameAnalyzer
from sfir_backend.infrastructure.impact.report import ImpactReportGenerator
from sfir_backend.infrastructure.impact.risk import RiskCalculator
from sfir_backend.infrastructure.impact.simulation import SimulationEngine
from sfir_backend.infrastructure.impact.statistics import ImpactStatistics


class ImpactAnalysisEngine:
    def __init__(
        self,
        graph_engine: DependencyGraphEngine,
        search_engine: Any = None,
    ) -> None:
        self._graph_engine = graph_engine
        self._search_engine = search_engine

        self._blast = BlastRadiusCalculator()
        self._risk = RiskCalculator()
        self._impact = DependencyImpactAnalyzer(graph_engine)
        self._delete = DeleteAnalyzer(self._impact, self._blast, self._risk)
        self._rename = RenameAnalyzer(self._impact, self._blast, self._risk)
        self._change = ChangeAnalyzer(self._impact)
        self._relationship = RelationshipAnalyzer()
        self._deployment = DeploymentAnalyzer(self._blast, self._risk)
        self._simulation = SimulationEngine(
            self._impact, self._delete, self._rename, self._change,
            self._blast, self._risk, self._deployment,
        )
        self._report = ImpactReportGenerator()
        self._statistics = ImpactStatistics()

    @property
    def graph_engine(self) -> DependencyGraphEngine:
        return self._graph_engine

    @property
    def statistics(self) -> ImpactStatistics:
        return self._statistics

    def analyze_delete(
        self,
        component_key: str,
    ) -> ImpactAnalysis:
        start = time.time()
        try:
            result = self._run_delete_analysis(component_key)
            self._statistics.record_analysis(
                "delete", str(result.summary.risk_severity),
                result.summary.total_affected, (time.time() - start) * 1000, True,
            )
            return result
        except Exception:
            self._statistics.record_analysis(
                "delete", "error", 0, (time.time() - start) * 1000, False,
            )
            raise

    def analyze_rename(
        self,
        component_key: str,
        new_name: str,
    ) -> ImpactAnalysis:
        start = time.time()
        try:
            result = self._run_rename_analysis(component_key, new_name)
            self._statistics.record_analysis(
                "rename", str(result.summary.risk_severity),
                result.summary.total_affected, (time.time() - start) * 1000, True,
            )
            return result
        except Exception:
            self._statistics.record_analysis(
                "rename", "error", 0, (time.time() - start) * 1000, False,
            )
            raise

    def analyze_modify(
        self,
        component_key: str,
    ) -> ImpactAnalysis:
        start = time.time()
        try:
            result = self._run_modify_analysis(component_key)
            self._statistics.record_analysis(
                "modify", str(result.summary.risk_severity),
                result.summary.total_affected, (time.time() - start) * 1000, True,
            )
            return result
        except Exception:
            self._statistics.record_analysis(
                "modify", "error", 0, (time.time() - start) * 1000, False,
            )
            raise

    def simulate(self, request: SimulationRequest) -> SimulationResult:
        start = time.time()
        try:
            graph = self._graph_engine.graph
            result = self._simulation.simulate(request, graph)
            self._statistics.record_analysis(
                "simulation", str(result.analysis.summary.risk_severity),
                result.analysis.summary.total_affected,
                (time.time() - start) * 1000, True,
            )
            return result
        except Exception:
            self._statistics.record_analysis(
                "simulation", "error", 0, (time.time() - start) * 1000, False,
            )
            raise

    def analyze_deployment(
        self,
        component_keys: list[str],
    ) -> ImpactAnalysis:
        start = time.time()
        try:
            graph = self._graph_engine.graph
            readiness = self._deployment.analyze_deployment(graph, component_keys)
            affected: list[AffectedComponent] = []
            paths: list[Any] = []
            for key in component_keys:
                comps, pths = self._impact.find_impacted(key, max_depth=10)
                affected.extend(comps)
                paths.extend(pths)

            blast = BlastRadius(total_count=len(affected))
            risk = readiness.risk_assessment
            summary = ImpactSummary(
                analysis_type=AnalysisType.DEPLOYMENT,
                component_key=",".join(component_keys),
                total_affected=len(affected),
                critical_count=sum(
                    1 for c in affected if c.severity == ImpactSeverity.CRITICAL
                ),
                risk_score=risk.risk_score,
                risk_severity=risk.severity,
            )
            analysis = ImpactAnalysis(
                analysis_type=AnalysisType.DEPLOYMENT,
                component_key=",".join(component_keys),
                affected_components=affected,
                paths=paths,
                blast_radius=blast,
                risk_assessment=risk,
                deployment_readiness=readiness,
                summary=summary,
                created_at=datetime.now(tz=UTC),
                took_ms=(time.time() - start) * 1000,
            )
            self._statistics.record_analysis(
                "deployment", str(risk.severity),
                len(affected), (time.time() - start) * 1000, True,
            )
            return analysis
        except Exception:
            self._statistics.record_analysis(
                "deployment", "error", 0, (time.time() - start) * 1000, False,
            )
            raise

    def generate_report(self, analysis: ImpactAnalysis, title: str = "") -> ImpactReport:
        return self._report.generate(analysis, title)

    def get_relationships(self, component_key: str) -> list[dict[str, Any]]:
        graph = self._graph_engine.graph
        return self._relationship.analyze_relationships(graph, component_key)

    def get_permission_impact(self, component_key: str) -> list[AffectedComponent]:
        graph = self._graph_engine.graph
        return self._relationship.find_permission_impact(graph, component_key)

    def get_layout_impact(self, component_key: str) -> list[AffectedComponent]:
        graph = self._graph_engine.graph
        return self._relationship.find_layout_impact(graph, component_key)

    def get_report_dashboard_impact(self, component_key: str) -> list[AffectedComponent]:
        graph = self._graph_engine.graph
        return self._relationship.find_report_dashboard_impact(graph, component_key)

    def impact_statistics(self) -> dict[str, Any]:
        return self._statistics.snapshot()

    def _run_delete_analysis(self, component_key: str) -> ImpactAnalysis:
        graph = self._graph_engine.graph
        node = graph.get_node(component_key)
        node_type = node.node_type.value if node else "unknown"

        affected, paths = self._impact.find_impacted(
            component_key, change_type=ChangeType.DELETE, max_depth=10,
        )
        blast = self._blast.calculate(graph, component_key, max_depth=10)
        risk = self._risk.calculate(
            blast, node_type,
            has_cycles=blast.has_circular_dependency,
            max_depth=blast.max_depth,
        )
        summary = ImpactSummary(
            analysis_type=AnalysisType.DELETE,
            component_key=component_key,
            component_name=node.api_name if node else "",
            component_type=node_type,
            total_affected=blast.total_count,
            critical_count=sum(1 for c in affected if c.severity == ImpactSeverity.CRITICAL),
            high_count=sum(1 for c in affected if c.severity == ImpactSeverity.HIGH),
            max_depth=blast.max_depth,
            has_cycles=blast.has_circular_dependency,
            risk_score=risk.risk_score,
            risk_severity=risk.severity,
        )
        return ImpactAnalysis(
            analysis_type=AnalysisType.DELETE,
            component_key=component_key,
            component_name=node.api_name if node else "",
            component_type=node_type,
            affected_components=affected,
            paths=paths,
            blast_radius=blast,
            risk_assessment=risk,
            summary=summary,
            created_at=datetime.now(tz=UTC),
        )

    def _run_rename_analysis(
        self,
        component_key: str,
        new_name: str,
    ) -> ImpactAnalysis:
        graph = self._graph_engine.graph
        node = graph.get_node(component_key)
        node_type = node.node_type.value if node else "unknown"

        affected, paths = self._impact.find_impacted(
            component_key, change_type=ChangeType.RENAME, max_depth=10,
        )
        blast = self._blast.calculate(graph, component_key, max_depth=10)
        risk = self._risk.calculate(blast, node_type, max_depth=blast.max_depth)
        summary = ImpactSummary(
            analysis_type=AnalysisType.RENAME,
            component_key=component_key,
            component_name=node.api_name if node else "",
            component_type=node_type,
            total_affected=blast.total_count,
            critical_count=sum(1 for c in affected if c.severity == ImpactSeverity.CRITICAL),
            high_count=sum(1 for c in affected if c.severity == ImpactSeverity.HIGH),
            max_depth=blast.max_depth,
            risk_score=risk.risk_score,
            risk_severity=risk.severity,
        )
        return ImpactAnalysis(
            analysis_type=AnalysisType.RENAME,
            component_key=component_key,
            component_name=node.api_name if node else "",
            component_type=node_type,
            affected_components=affected,
            paths=paths,
            blast_radius=blast,
            risk_assessment=risk,
            summary=summary,
            created_at=datetime.now(tz=UTC),
        )

    def _run_modify_analysis(self, component_key: str) -> ImpactAnalysis:
        graph = self._graph_engine.graph
        node = graph.get_node(component_key)
        node_type = node.node_type.value if node else "unknown"

        affected, paths = self._impact.find_impacted(
            component_key, change_type=ChangeType.MODIFY, max_depth=10,
        )
        blast = self._blast.calculate(graph, component_key, max_depth=10)
        risk = self._risk.calculate(blast, node_type, max_depth=blast.max_depth)
        summary = ImpactSummary(
            analysis_type=AnalysisType.MODIFY,
            component_key=component_key,
            component_name=node.api_name if node else "",
            component_type=node_type,
            total_affected=blast.total_count,
            critical_count=sum(1 for c in affected if c.severity == ImpactSeverity.CRITICAL),
            high_count=sum(1 for c in affected if c.severity == ImpactSeverity.HIGH),
            max_depth=blast.max_depth,
            risk_score=risk.risk_score,
            risk_severity=risk.severity,
        )
        return ImpactAnalysis(
            analysis_type=AnalysisType.MODIFY,
            component_key=component_key,
            component_name=node.api_name if node else "",
            component_type=node_type,
            affected_components=affected,
            paths=paths,
            blast_radius=blast,
            risk_assessment=risk,
            summary=summary,
            created_at=datetime.now(tz=UTC),
        )
