from __future__ import annotations

from sfir_backend.domain.impact.models import BlastRadius, ImpactSeverity, RiskAssessment

_TYPE_WEIGHTS: dict[str, float] = {
    "object": 1.0,
    "field": 0.5,
    "apex_class": 0.9,
    "flow": 0.8,
    "validation_rule": 0.4,
    "layout": 0.6,
    "permission_set": 0.7,
    "report": 0.4,
    "dashboard": 0.5,
    "queue": 0.5,
    "unknown": 0.6,
}
_DEFAULT_WEIGHT: float = 0.6


class RiskCalculator:
    def calculate(
        self,
        blast_radius: BlastRadius,
        component_type: str,
        has_cycles: bool = False,
        max_depth: int = 0,
    ) -> RiskAssessment:
        if blast_radius.total_count == 0:
            return RiskAssessment(
                risk_score=0.0,
                severity=ImpactSeverity.INFO,
                reasons=["No impacted components found"],
            )

        base_weight = _TYPE_WEIGHTS.get(component_type, _DEFAULT_WEIGHT)
        total = blast_radius.total_count
        depth = max_depth or blast_radius.max_depth
        circular = has_cycles or blast_radius.has_circular_dependency

        depth_factor = min(depth / 10.0, 1.0)
        count_factor = min(total / 20.0, 1.0)
        critical_factor = 1.2 if circular else 1.0

        raw_score = base_weight * (0.4 + 0.3 * depth_factor + 0.3 * count_factor) * critical_factor
        risk_score = min(round(raw_score * 100, 1), 100.0)

        reasons: list[str] = []
        if total > 0:
            reasons.append(f"{total} component(s) affected")
        if depth > 0:
            reasons.append(f"Max impact depth: {depth}")
        if circular:
            reasons.append("Circular dependency detected")

        if risk_score >= 90:
            severity = ImpactSeverity.CRITICAL
            reasons.append("CRITICAL risk score threshold exceeded")
        elif risk_score >= 70:
            severity = ImpactSeverity.HIGH
        elif risk_score >= 40:
            severity = ImpactSeverity.MEDIUM
        elif risk_score >= 10:
            severity = ImpactSeverity.LOW
        else:
            severity = ImpactSeverity.INFO

        return RiskAssessment(
            risk_score=risk_score,
            severity=severity,
            reasons=reasons,
            depth_factor=depth_factor,
            count_factor=count_factor,
            critical_factor=critical_factor,
        )
