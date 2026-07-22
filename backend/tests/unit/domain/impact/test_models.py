"""Tests for impact analysis domain models."""

from sfir_backend.domain.impact.models import (
    AffectedComponent,
    AnalysisType,
    BlastRadius,
    ChangeType,
    ImpactAnalysis,
    ImpactPath,
    ImpactReport,
    ImpactSeverity,
    ImpactStatus,
    RecommendedAction,
    RiskAssessment,
    SimulationRequest,
    SimulationResult,
)


class TestEnums:
    def test_analysis_type_values(self) -> None:
        assert AnalysisType.DELETE == "delete"
        assert AnalysisType.RENAME == "rename"
        assert AnalysisType.SIMULATION == "simulation"

    def test_impact_severity_values(self) -> None:
        assert ImpactSeverity.CRITICAL == "critical"
        assert ImpactSeverity.HIGH == "high"
        assert ImpactSeverity.INFO == "info"

    def test_impact_status_values(self) -> None:
        assert ImpactStatus.BLOCKING == "blocking"
        assert ImpactStatus.WARNING == "warning"
        assert ImpactStatus.SAFE == "safe"

    def test_change_type_values(self) -> None:
        assert ChangeType.DELETE == "delete"
        assert ChangeType.RENAME == "rename"
        assert ChangeType.MODIFY == "modify"


class TestAffectedComponent:
    def test_defaults(self) -> None:
        c = AffectedComponent()
        assert c.component_key == ""
        assert c.dependency_depth == 0
        assert c.severity == ImpactSeverity.INFO


class TestBlastRadius:
    def test_defaults(self) -> None:
        b = BlastRadius()
        assert b.direct_count == 0
        assert b.total_count == 0
        assert b.by_type == {}


class TestRiskAssessment:
    def test_defaults(self) -> None:
        r = RiskAssessment()
        assert r.risk_score == 0.0
        assert r.severity == ImpactSeverity.INFO
        assert r.reasons == []


class TestImpactAnalysis:
    def test_defaults(self) -> None:
        a = ImpactAnalysis()
        assert a.analysis_type == AnalysisType.SIMULATION
        assert a.affected_components == []
        assert a.took_ms == 0.0

    def test_with_data(self) -> None:
        a = ImpactAnalysis(
            id="test-1",
            analysis_type=AnalysisType.DELETE,
            component_key="object:Account",
            affected_components=[
                AffectedComponent(component_key="field:Account.Name", name="Name"),
            ],
        )
        assert a.id == "test-1"
        assert len(a.affected_components) == 1


class TestImpactReport:
    def test_defaults(self) -> None:
        r = ImpactReport()
        assert r.title == ""
        assert r.affected_by_type == {}
        assert r.critical_components == []


class TestSimulationRequest:
    def test_defaults(self) -> None:
        r = SimulationRequest()
        assert r.component_key == ""
        assert r.change_type == ChangeType.DELETE


class TestSimulationResult:
    def test_defaults(self) -> None:
        r = SimulationResult()
        assert r.is_safe is True
        assert r.blocking_issues == []


class TestImpactPath:
    def test_defaults(self) -> None:
        p = ImpactPath()
        assert p.nodes == []
        assert p.total_depth == 0


class TestRecommendedAction:
    def test_defaults(self) -> None:
        a = RecommendedAction()
        assert a.action == ""
        assert a.priority == "medium"
