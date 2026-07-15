from __future__ import annotations

from collections import defaultdict

from sfir_backend.domain.impact.models import (
    AffectedComponent,
    ImpactAnalysis,
    ImpactReport,
    ImpactSeverity,
)


class ImpactReportGenerator:
    def generate(self, analysis: ImpactAnalysis, title: str = "") -> ImpactReport:
        title = title or f"Impact Analysis Report: {analysis.component_key}"

        by_type: dict[str, list[AffectedComponent]] = defaultdict(list)
        for comp in analysis.affected_components:
            by_type[comp.component_type].append(comp)

        critical = [c for c in analysis.affected_components
                    if c.severity == ImpactSeverity.CRITICAL]

        return ImpactReport(
            title=title,
            analysis=analysis,
            affected_by_type=dict(by_type),
            critical_components=critical,
            dependency_tree=analysis.paths,
            recommendations=analysis.recommended_actions,
            deployment_order=analysis.deployment_readiness.safe_deployment_order,
            rollback_plan=analysis.deployment_readiness.rollback_steps,
        )
