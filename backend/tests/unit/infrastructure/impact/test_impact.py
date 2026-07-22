"""Comprehensive tests for the Impact Analysis Engine."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from sfir_backend.domain.graph.models import EdgeType, Graph, GraphEdge, GraphNode, NodeType
from sfir_backend.domain.impact.models import (
    BlastRadius,
    DeploymentReadiness,
    ImpactAnalysis,
    ImpactPath,
    ImpactSeverity,
    ImpactStatus,
    RecommendedAction,
    RiskAssessment,
)
from sfir_backend.domain.impact.models import (
    AnalysisType,
    ChangeType,
    ImpactSeverity,
    ImpactStatus,
    SimulationRequest,
)
from sfir_backend.infrastructure.graph.engine import DependencyGraphEngine
from sfir_backend.infrastructure.impact.analyzer import DependencyImpactAnalyzer
from sfir_backend.infrastructure.impact.blast_radius import BlastRadiusCalculator
from sfir_backend.infrastructure.impact.change import ChangeAnalyzer
from sfir_backend.infrastructure.impact.delete import DeleteAnalyzer
from sfir_backend.infrastructure.impact.deployment import DeploymentAnalyzer
from sfir_backend.infrastructure.impact.engine import ImpactAnalysisEngine
from sfir_backend.infrastructure.impact.relationship import RelationshipAnalyzer
from sfir_backend.infrastructure.impact.rename import RenameAnalyzer
from sfir_backend.infrastructure.impact.report import ImpactReportGenerator
from sfir_backend.infrastructure.impact.risk import RiskCalculator
from sfir_backend.infrastructure.impact.simulation import SimulationEngine
from sfir_backend.infrastructure.impact.statistics import ImpactStatistics


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_graph() -> Graph:
    g = Graph()

    object_acc = GraphNode(node_type=NodeType.OBJECT, api_name="Account")
    object_opp = GraphNode(node_type=NodeType.OBJECT, api_name="Opportunity")
    field_name = GraphNode(node_type=NodeType.FIELD, api_name="Account.Name")
    field_phone = GraphNode(node_type=NodeType.FIELD, api_name="Account.Phone")
    field_amount = GraphNode(node_type=NodeType.FIELD, api_name="Opportunity.Amount")
    apex_cls = GraphNode(node_type=NodeType.APEX_CLASS, api_name="AccountService")
    layout = GraphNode(node_type=NodeType.LAYOUT, api_name="Account-Account Layout")
    validation = GraphNode(node_type=NodeType.VALIDATION_RULE, api_name="Account.ValidName")
    flow = GraphNode(node_type=NodeType.FLOW, api_name="AccountFlow")
    report = GraphNode(node_type=NodeType.REPORT, api_name="AccountReport")
    dashboard = GraphNode(node_type=NodeType.DASHBOARD, api_name="AccountDashboard")
    perm_set = GraphNode(node_type=NodeType.PERMISSION_SET, api_name="AccountAdmin")

    g.add_node(object_acc)
    g.add_node(object_opp)
    g.add_node(field_name)
    g.add_node(field_phone)
    g.add_node(field_amount)
    g.add_node(apex_cls)
    g.add_node(layout)
    g.add_node(validation)
    g.add_node(flow)
    g.add_node(report)
    g.add_node(dashboard)
    g.add_node(perm_set)

    g.add_edge(GraphEdge(source_id="object:Account", target_id="field:Account.Name", edge_type=EdgeType.CONTAINS))
    g.add_edge(GraphEdge(source_id="object:Account", target_id="field:Account.Phone", edge_type=EdgeType.CONTAINS))
    g.add_edge(GraphEdge(source_id="object:Opportunity", target_id="field:Opportunity.Amount", edge_type=EdgeType.CONTAINS))
    g.add_edge(GraphEdge(source_id="apex_class:AccountService", target_id="object:Account", edge_type=EdgeType.REFERENCES))
    g.add_edge(GraphEdge(source_id="layout:Account-Account Layout", target_id="object:Account", edge_type=EdgeType.REFERENCES))
    g.add_edge(GraphEdge(source_id="validation_rule:Account.ValidName", target_id="field:Account.Name", edge_type=EdgeType.REFERENCES))
    g.add_edge(GraphEdge(source_id="flow:AccountFlow", target_id="object:Account", edge_type=EdgeType.REFERENCES))
    g.add_edge(GraphEdge(source_id="report:AccountReport", target_id="object:Account", edge_type=EdgeType.REFERENCES))
    g.add_edge(GraphEdge(source_id="dashboard:AccountDashboard", target_id="report:AccountReport", edge_type=EdgeType.REFERENCES))
    g.add_edge(GraphEdge(source_id="permission_set:AccountAdmin", target_id="object:Account", edge_type=EdgeType.REFERENCES))

    return g


@pytest.fixture
def engine(sample_graph: Graph) -> DependencyGraphEngine:
    eng = DependencyGraphEngine()
    eng._graph = sample_graph
    return eng


@pytest.fixture
def impact_engine(engine: DependencyGraphEngine) -> ImpactAnalysisEngine:
    return ImpactAnalysisEngine(graph_engine=engine)


# ---------------------------------------------------------------------------
# RiskCalculator
# ---------------------------------------------------------------------------

class TestRiskCalculator:
    def test_calculate_minimal(self) -> None:
        calc = RiskCalculator()
        blast = MagicMock()
        blast.total_count = 0
        blast.max_depth = 0
        blast.has_circular_dependency = False
        blast.by_type = {}
        risk = calc.calculate(blast, "field")
        assert risk.risk_score == 0.0
        assert risk.severity == ImpactSeverity.INFO

    def test_calculate_maximal(self) -> None:
        calc = RiskCalculator()
        blast = MagicMock()
        blast.total_count = 20
        blast.max_depth = 10
        blast.has_circular_dependency = True
        blast.by_type = {"object": 5, "apex_class": 5, "flow": 5, "layout": 5}
        risk = calc.calculate(blast, "object")
        assert risk.risk_score > 0
        assert risk.severity in (ImpactSeverity.CRITICAL, ImpactSeverity.HIGH)
        assert len(risk.reasons) > 0

    def test_calculate_uses_type_weight(self) -> None:
        calc = RiskCalculator()
        blast = MagicMock()
        blast.total_count = 5
        blast.max_depth = 3
        blast.has_circular_dependency = False
        blast.by_type = {"flow": 5}

        risk_object = calc.calculate(blast, "object")
        risk_flow = calc.calculate(blast, "flow")
        risk_info = calc.calculate(blast, "report")
        risk_field = calc.calculate(blast, "field")
        assert risk_flow.risk_score > risk_info.risk_score
        assert risk_object.risk_score > risk_field.risk_score

    def test_calculate_critical_threshold(self) -> None:
        calc = RiskCalculator()
        blast = MagicMock()
        blast.total_count = 50
        blast.max_depth = 15
        blast.has_circular_dependency = True
        blast.by_type = {"object": 20, "apex_class": 15, "flow": 10, "layout": 5}
        risk = calc.calculate(blast, "object")
        assert risk.risk_score >= 90
        assert risk.severity == ImpactSeverity.CRITICAL


# ---------------------------------------------------------------------------
# BlastRadiusCalculator
# ---------------------------------------------------------------------------

class TestBlastRadiusCalculator:
    def test_calculate_returns_blast_radius(self, sample_graph: Graph) -> None:
        calc = BlastRadiusCalculator()
        result = calc.calculate(sample_graph, "object:Account", max_depth=3)
        assert result is not None
        assert result.total_count > 0
        assert result.direct_count > 0
        assert result.by_type is not None

    def test_calculate_finds_direct_and_indirect(self, sample_graph: Graph) -> None:
        calc = BlastRadiusCalculator()
        result = calc.calculate(sample_graph, "object:Account", max_depth=5)
        # Direct: field:Account.Name, field:Account.Phone
        # Indirect: validation_rule:Account.ValidName (depth 2 via field:Account.Name)
        # Also: apex_class:AccountService, layout, flow, report, perm_set reference object:Account
        assert result.direct_count > 0
        assert result.total_count >= result.direct_count
        assert "field" in result.by_type or "validation_rule" in result.by_type

    def test_calculate_unknown_node(self, sample_graph: Graph) -> None:
        calc = BlastRadiusCalculator()
        result = calc.calculate(sample_graph, "object:NonExistent", max_depth=3)
        assert result.total_count == 0
        assert result.direct_count == 0

    def test_calculate_respects_max_depth(self, sample_graph: Graph) -> None:
        calc = BlastRadiusCalculator()
        result_shallow = calc.calculate(sample_graph, "object:Account", max_depth=1)
        result_deep = calc.calculate(sample_graph, "object:Account", max_depth=10)
        assert result_deep.total_count >= result_shallow.total_count

    def test_calculate_with_dashboard_indirect(self, sample_graph: Graph) -> None:
        calc = BlastRadiusCalculator()
        result = calc.calculate(sample_graph, "object:Account", max_depth=5)
        # dashboard:AccountDashboard references report:AccountReport which references
        # object:Account — should be found at depth 2+
        assert result.total_count >= 1


# ---------------------------------------------------------------------------
# DependencyImpactAnalyzer
# ---------------------------------------------------------------------------

class TestDependencyImpactAnalyzer:
    def test_find_impacted_returns_components_and_paths(
        self, engine: DependencyGraphEngine,
    ) -> None:
        analyzer = DependencyImpactAnalyzer(engine)
        affected, paths = analyzer.find_impacted(
            "object:Account",
            change_type=ChangeType.DELETE,
            max_depth=5,
        )
        assert len(affected) > 0
        assert len(paths) > 0

    def test_find_impacted_unknown_key(
        self, engine: DependencyGraphEngine,
    ) -> None:
        analyzer = DependencyImpactAnalyzer(engine)
        affected, paths = analyzer.find_impacted(
            "object:NonExistent",
            change_type=ChangeType.DELETE,
            max_depth=5,
        )
        assert affected == []
        assert paths == []

    def test_find_impacted_respects_max_depth(
        self, engine: DependencyGraphEngine,
    ) -> None:
        analyzer = DependencyImpactAnalyzer(engine)
        shallow, _ = analyzer.find_impacted(
            "object:Account", change_type=ChangeType.DELETE, max_depth=0,
        )
        deep, _ = analyzer.find_impacted(
            "object:Account", change_type=ChangeType.DELETE, max_depth=10,
        )
        assert len(deep) >= len(shallow)

    def test_find_impacted_handles_rename(
        self, engine: DependencyGraphEngine,
    ) -> None:
        analyzer = DependencyImpactAnalyzer(engine)
        affected, paths = analyzer.find_impacted(
            "field:Account.Name",
            change_type=ChangeType.RENAME,
            max_depth=5,
        )
        assert len(affected) >= 1
        assert any("validation_rule" in c.component_type for c in affected)

    def test_find_impacted_filters_node_types(
        self, engine: DependencyGraphEngine,
    ) -> None:
        analyzer = DependencyImpactAnalyzer(engine)
        affected, _ = analyzer.find_impacted(
            "object:Account",
            change_type=ChangeType.DELETE,
            max_depth=5,
            include_types=["apex_class", "flow"],
        )
        assert all(
            c.component_type in ("apex_class", "flow") for c in affected
        )

    def test_find_impacted_excludes_node_types(
        self, engine: DependencyGraphEngine,
    ) -> None:
        analyzer = DependencyImpactAnalyzer(engine)
        affected, _ = analyzer.find_impacted(
            "object:Account",
            change_type=ChangeType.DELETE,
            max_depth=5,
            exclude_types=["apex_class", "flow"],
        )
        assert all(
            c.component_type not in ("apex_class", "flow") for c in affected
        )


# ---------------------------------------------------------------------------
# DeleteAnalyzer
# ---------------------------------------------------------------------------

class TestDeleteAnalyzer:
    def test_analyze_field_delete(self, engine: DependencyGraphEngine) -> None:
        impact = DependencyImpactAnalyzer(engine)
        blast = BlastRadiusCalculator()
        risk = RiskCalculator()
        analyzer = DeleteAnalyzer(impact, blast, risk)
        result = analyzer.analyze_field_delete("Name", "Account")
        assert "affected" in result
        assert "blast_radius" in result
        assert "risk" in result
        assert len(result["warnings"]) > 0

    def test_analyze_object_delete(self, engine: DependencyGraphEngine) -> None:
        impact = DependencyImpactAnalyzer(engine)
        blast = BlastRadiusCalculator()
        risk = RiskCalculator()
        analyzer = DeleteAnalyzer(impact, blast, risk)
        result = analyzer.analyze_object_delete("Account")
        assert "affected" in result
        assert "blast_radius" in result
        assert result["blast_radius"].total_count > 0

    def test_analyze_flow_delete(self, engine: DependencyGraphEngine) -> None:
        impact = DependencyImpactAnalyzer(engine)
        blast = BlastRadiusCalculator()
        risk = RiskCalculator()
        analyzer = DeleteAnalyzer(impact, blast, risk)
        result = analyzer.analyze_flow_delete("AccountFlow")
        assert "affected" in result
        assert "blast_radius" in result

    def test_analyze_validation_rule_delete(self, engine: DependencyGraphEngine) -> None:
        impact = DependencyImpactAnalyzer(engine)
        blast = BlastRadiusCalculator()
        risk = RiskCalculator()
        analyzer = DeleteAnalyzer(impact, blast, risk)
        result = analyzer.analyze_validation_rule_delete("ValidName", "Account")
        assert "affected" in result
        assert "blast_radius" in result


# ---------------------------------------------------------------------------
# RenameAnalyzer
# ---------------------------------------------------------------------------

class TestRenameAnalyzer:
    def test_analyze_field_rename(self, engine: DependencyGraphEngine) -> None:
        impact = DependencyImpactAnalyzer(engine)
        blast = BlastRadiusCalculator()
        risk = RiskCalculator()
        analyzer = RenameAnalyzer(impact, blast, risk)
        result = analyzer.analyze_field_rename("Account", "Name", "FullName")
        assert "affected" in result
        assert len(result["affected"]) > 0

    def test_analyze_object_rename(self, engine: DependencyGraphEngine) -> None:
        impact = DependencyImpactAnalyzer(engine)
        blast = BlastRadiusCalculator()
        risk = RiskCalculator()
        analyzer = RenameAnalyzer(impact, blast, risk)
        result = analyzer.analyze_object_rename("Account", "Client")
        assert "affected" in result
        assert len(result["affected"]) > 0
        assert len(result["warnings"]) > 0


# ---------------------------------------------------------------------------
# RelationshipAnalyzer
# ---------------------------------------------------------------------------

class TestRelationshipAnalyzer:
    def test_analyze_relationships(self, sample_graph: Graph) -> None:
        analyzer = RelationshipAnalyzer()
        result = analyzer.analyze_relationships(sample_graph, "object:Account")
        assert isinstance(result, list)
        for rel in result:
            assert "relation" in rel
            assert "key" in rel

    def test_find_permission_impact(self, sample_graph: Graph) -> None:
        analyzer = RelationshipAnalyzer()
        result = analyzer.find_permission_impact(sample_graph, "object:Account")
        # permission_set:AccountAdmin references object:Account
        assert len(result) > 0
        assert any(
            c.component_type == "permission_set" for c in result
        )

    def test_find_permission_impact_none(self, sample_graph: Graph) -> None:
        analyzer = RelationshipAnalyzer()
        result = analyzer.find_permission_impact(sample_graph, "field:Opportunity.Amount")
        assert len(result) == 0

    def test_find_layout_impact(self, sample_graph: Graph) -> None:
        analyzer = RelationshipAnalyzer()
        result = analyzer.find_layout_impact(sample_graph, "object:Account")
        assert len(result) > 0
        assert any(c.component_type == "layout" for c in result)

    def test_find_report_dashboard_impact(self, sample_graph: Graph) -> None:
        analyzer = RelationshipAnalyzer()
        result = analyzer.find_report_dashboard_impact(sample_graph, "object:Account")
        assert len(result) > 0
        assert any(c.component_type == "dashboard" for c in result)


# ---------------------------------------------------------------------------
# ChangeAnalyzer
# ---------------------------------------------------------------------------

class TestChangeAnalyzer:
    def test_analyze_modify(self, engine: DependencyGraphEngine) -> None:
        impact = DependencyImpactAnalyzer(engine)
        analyzer = ChangeAnalyzer(impact)
        result = analyzer.analyze_modify("object:Account")
        assert "affected" in result
        assert "paths" in result


# ---------------------------------------------------------------------------
# DeploymentAnalyzer
# ---------------------------------------------------------------------------

class TestDeploymentAnalyzer:
    def test_analyze_deployment(self, sample_graph: Graph) -> None:
        blast = BlastRadiusCalculator()
        risk = RiskCalculator()
        analyzer = DeploymentAnalyzer(blast, risk)
        result = analyzer.analyze_deployment(
            sample_graph,
            ["object:Account", "flow:AccountFlow"],
        )
        assert result.is_ready is not None
        assert result.safe_deployment_order is not None
        assert result.risk_assessment is not None
        assert result.blocking_issues is not None

    def test_analyze_deployment_no_components(self, sample_graph: Graph) -> None:
        blast = BlastRadiusCalculator()
        risk = RiskCalculator()
        analyzer = DeploymentAnalyzer(blast, risk)
        result = analyzer.analyze_deployment(sample_graph, [])
        assert result.safe_deployment_order == []

    def test_analyze_deployment_unknown_component(self, sample_graph: Graph) -> None:
        blast = BlastRadiusCalculator()
        risk = RiskCalculator()
        analyzer = DeploymentAnalyzer(blast, risk)
        result = analyzer.analyze_deployment(
            sample_graph,
            ["object:DoesNotExist"],
        )
        assert result.is_ready is not None
        assert result.safe_deployment_order is not None


# ---------------------------------------------------------------------------
# SimulationEngine
# ---------------------------------------------------------------------------

class TestSimulationEngine:
    def test_simulate_delete(self, sample_graph: Graph, engine: DependencyGraphEngine) -> None:
        impact = DependencyImpactAnalyzer(engine)
        blast = BlastRadiusCalculator()
        risk = RiskCalculator()
        delete_analyzer = DeleteAnalyzer(impact, blast, risk)
        rename_analyzer = RenameAnalyzer(impact, blast, risk)
        change_analyzer = ChangeAnalyzer(impact)
        deploy_analyzer = DeploymentAnalyzer(blast, risk)
        sim = SimulationEngine(impact, delete_analyzer, rename_analyzer,
                               change_analyzer, blast, risk, deploy_analyzer)

        request = SimulationRequest(
            component_key="object:Account",
            change_type=ChangeType.DELETE,
            simulate_delete=True,
        )
        result = sim.simulate(request, sample_graph)
        assert result.analysis is not None
        assert result.analysis.summary.total_affected > 0

    def test_simulate_rename(self, sample_graph: Graph, engine: DependencyGraphEngine) -> None:
        impact = DependencyImpactAnalyzer(engine)
        blast = BlastRadiusCalculator()
        risk = RiskCalculator()
        delete_analyzer = DeleteAnalyzer(impact, blast, risk)
        rename_analyzer = RenameAnalyzer(impact, blast, risk)
        change_analyzer = ChangeAnalyzer(impact)
        deploy_analyzer = DeploymentAnalyzer(blast, risk)
        sim = SimulationEngine(impact, delete_analyzer, rename_analyzer,
                               change_analyzer, blast, risk, deploy_analyzer)

        request = SimulationRequest(
            component_key="field:Account.Name",
            change_type=ChangeType.RENAME,
            simulate_rename="FullName",
        )
        result = sim.simulate(request, sample_graph)
        assert result.analysis is not None
        assert result.analysis.summary.total_affected > 0

    def test_simulate_generic(self, sample_graph: Graph, engine: DependencyGraphEngine) -> None:
        impact = DependencyImpactAnalyzer(engine)
        blast = BlastRadiusCalculator()
        risk = RiskCalculator()
        delete_analyzer = DeleteAnalyzer(impact, blast, risk)
        rename_analyzer = RenameAnalyzer(impact, blast, risk)
        change_analyzer = ChangeAnalyzer(impact)
        deploy_analyzer = DeploymentAnalyzer(blast, risk)
        sim = SimulationEngine(impact, delete_analyzer, rename_analyzer,
                               change_analyzer, blast, risk, deploy_analyzer)

        request = SimulationRequest(
            component_key="field:Account.Phone",
            change_type=ChangeType.MODIFY,
            simulate_modify=True,
        )
        result = sim.simulate(request, sample_graph)
        assert result.analysis is not None


# ---------------------------------------------------------------------------
# ImpactReportGenerator
# ---------------------------------------------------------------------------

class TestImpactReportGenerator:
    def test_generate_empty(self) -> None:
        gen = ImpactReportGenerator()
        analysis = ImpactAnalysis(component_key="test")
        report = gen.generate(analysis, "Test Report")
        assert report.title == "Test Report"
        assert report.affected_by_type == {}
        assert report.critical_components == []

    def test_generate_with_components(self) -> None:
        gen = ImpactReportGenerator()
        from sfir_backend.domain.impact.models import AffectedComponent
        affected = [
            AffectedComponent(component_key="f1", component_type="field", severity=ImpactSeverity.CRITICAL),
            AffectedComponent(component_key="a1", component_type="apex_class", severity=ImpactSeverity.HIGH),
            AffectedComponent(component_key="fl1", component_type="flow", severity=ImpactSeverity.INFO),
        ]
        dr = DeploymentReadiness(safe_deployment_order=[], rollback_steps=[])
        analysis = ImpactAnalysis(
            component_key="test",
            affected_components=affected,
            deployment_readiness=dr,
        )
        report = gen.generate(analysis)
        assert "field" in report.affected_by_type
        assert "apex_class" in report.affected_by_type
        assert len(report.critical_components) > 0


# ---------------------------------------------------------------------------
# ImpactStatistics
# ---------------------------------------------------------------------------

class TestImpactStatistics:
    def test_snapshot_empty(self) -> None:
        stats = ImpactStatistics()
        snap = stats.snapshot()
        assert snap["total_analyses"] == 0
        assert snap["total_simulations"] == 0
        assert snap["total_failures"] == 0

    def test_record_and_snapshot(self) -> None:
        stats = ImpactStatistics()
        stats.record_analysis("delete", "critical", 10, 50.0, True)
        stats.record_analysis("simulation", "high", 5, 30.0, True)
        stats.record_analysis("modify", "info", 0, 10.0, False)
        snap = stats.snapshot()
        assert snap["total_analyses"] == 3
        assert snap["total_simulations"] == 1
        assert snap["total_failures"] == 1
        assert snap["total_affected_components"] == 15
        assert 0 < snap["avg_latency_ms"] <= 100

    def test_reset(self) -> None:
        stats = ImpactStatistics()
        stats.record_analysis("delete", "critical", 10, 50.0, True)
        stats.reset()
        snap = stats.snapshot()
        assert snap["total_analyses"] == 0


# ---------------------------------------------------------------------------
# ImpactAnalysisEngine (integration)
# ---------------------------------------------------------------------------

class TestImpactAnalysisEngine:
    def test_engine_initialization(self, impact_engine: ImpactAnalysisEngine) -> None:
        assert impact_engine.graph_engine is not None
        assert impact_engine.statistics is not None

    def test_analyze_delete(self, impact_engine: ImpactAnalysisEngine) -> None:
        result = impact_engine.analyze_delete("object:Account")
        assert result is not None
        assert result.analysis_type == AnalysisType.DELETE
        assert result.summary.total_affected > 0
        assert result.summary.risk_severity is not None

    def test_analyze_rename(self, impact_engine: ImpactAnalysisEngine) -> None:
        result = impact_engine.analyze_rename(
            "field:Account.Name", "FullName",
        )
        assert result.analysis_type == AnalysisType.RENAME
        assert result.summary.total_affected > 0

    def test_analyze_modify(self, impact_engine: ImpactAnalysisEngine) -> None:
        result = impact_engine.analyze_modify("apex_class:AccountService")
        assert result.analysis_type == AnalysisType.MODIFY

    def test_simulate(self, impact_engine: ImpactAnalysisEngine) -> None:
        request = SimulationRequest(
            component_key="object:Account",
            change_type=ChangeType.DELETE,
            simulate_delete=True,
        )
        result = impact_engine.simulate(request)
        assert result.is_safe is False
        assert result.analysis.summary.total_affected > 0

    def test_analyze_deployment(self, impact_engine: ImpactAnalysisEngine) -> None:
        result = impact_engine.analyze_deployment([
            "object:Account", "flow:AccountFlow",
        ])
        assert result.analysis_type == AnalysisType.DEPLOYMENT
        assert result.deployment_readiness is not None

    def test_generate_report(self, impact_engine: ImpactAnalysisEngine) -> None:
        analysis = impact_engine.analyze_delete("object:Account")
        report = impact_engine.generate_report(analysis, "Account Delete Report")
        assert report.title == "Account Delete Report"
        assert report.analysis is not None

    def test_get_relationships(self, impact_engine: ImpactAnalysisEngine) -> None:
        result = impact_engine.get_relationships("object:Account")
        assert isinstance(result, list)
        assert len(result) > 0

    def test_get_permission_impact(self, impact_engine: ImpactAnalysisEngine) -> None:
        result = impact_engine.get_permission_impact("object:Account")
        assert len(result) > 0
        assert result[0].component_type == "permission_set"

    def test_get_layout_impact(self, impact_engine: ImpactAnalysisEngine) -> None:
        result = impact_engine.get_layout_impact("object:Account")
        assert len(result) > 0
        assert result[0].component_type == "layout"

    def test_get_report_dashboard_impact(self, impact_engine: ImpactAnalysisEngine) -> None:
        result = impact_engine.get_report_dashboard_impact("object:Account")
        assert len(result) > 0

    def test_statistics(self, impact_engine: ImpactAnalysisEngine) -> None:
        impact_engine.analyze_delete("object:Account")
        impact_engine.analyze_modify("apex_class:AccountService")
        stats = impact_engine.impact_statistics()
        assert stats["total_analyses"] >= 2
        assert stats["avg_latency_ms"] > 0

    def test_analyze_delete_unknown(self, impact_engine: ImpactAnalysisEngine) -> None:
        result = impact_engine.analyze_delete("object:DoesNotExist")
        assert result.summary.total_affected == 0

    def test_analyze_rename_unknown(self, impact_engine: ImpactAnalysisEngine) -> None:
        result = impact_engine.analyze_rename(
            "object:DoesNotExist", "NewName",
        )
        assert result is not None
        assert result.summary.total_affected == 0
