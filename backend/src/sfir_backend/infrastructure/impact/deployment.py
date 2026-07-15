from __future__ import annotations

from collections import deque
from typing import Any

from sfir_backend.domain.graph.models import Graph
from sfir_backend.domain.impact.models import (
    BlastRadius,
    DeploymentReadiness,
    ImpactSeverity,
    RiskAssessment,
)
from sfir_backend.infrastructure.impact.blast_radius import BlastRadiusCalculator
from sfir_backend.infrastructure.impact.risk import RiskCalculator


class DeploymentAnalyzer:
    def __init__(
        self,
        blast_calculator: BlastRadiusCalculator,
        risk_calculator: RiskCalculator,
    ) -> None:
        self._blast = blast_calculator
        self._risk = risk_calculator

    def analyze_deployment(
        self,
        graph: Graph,
        component_keys: list[str],
    ) -> DeploymentReadiness:
        if not component_keys:
            return DeploymentReadiness(
                is_ready=True,
                safe_deployment_order=[],
                risk_assessment=RiskAssessment(
                    risk_score=0.0,
                    severity=ImpactSeverity.INFO,
                    reasons=["No components to deploy"],
                ),
                blocking_issues=[],
                rollback_steps=[],
            )

        safe_order = self._topological_sort(graph, component_keys)
        total_affected = 0
        blocking: list[str] = []
        for key in component_keys:
            br = self._blast.calculate(graph, key, max_depth=5)
            total_affected += br.total_count
            if br.has_circular_dependency:
                blocking.append(key)

        total = max(total_affected, 1)
        risk = self._risk.calculate(
            BlastRadius(total_count=total, direct_count=len(component_keys)),
            "unknown",
            has_cycles=len(blocking) > 0,
            max_depth=5,
        )

        is_ready = len(blocking) == 0
        rollback = self._generate_rollback_steps(safe_order)

        return DeploymentReadiness(
            is_ready=is_ready,
            safe_deployment_order=safe_order,
            risk_assessment=risk,
            blocking_issues=[f"Circular dependency involving '{k}'" for k in blocking],
            rollback_steps=rollback,
        )

    def _topological_sort(
        self,
        graph: Graph,
        component_keys: list[str],
    ) -> list[str]:
        in_degree: dict[str, int] = {}
        adj: dict[str, list[str]] = {}

        for key in component_keys:
            if key not in in_degree:
                in_degree[key] = 0
                adj[key] = []

        for key in component_keys:
            for edge in graph.get_outgoing_edges(key):
                target = edge.target_id
                if target in component_keys:
                    adj.setdefault(key, []).append(target)
                    in_degree.setdefault(target, 0)
                    in_degree[target] += 1

            for edge in graph.get_incoming_edges(key):
                source = edge.source_id
                if source in component_keys:
                    adj.setdefault(source, []).append(key)
                    in_degree.setdefault(key, 0)
                    in_degree[key] += 1
                    in_degree.setdefault(source, 0)

        queue: deque[str] = deque()
        for key in component_keys:
            if in_degree.get(key, 0) == 0:
                queue.append(key)

        result: list[str] = []
        while queue:
            node = queue.popleft()
            result.append(node)
            for neighbor in adj.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        remaining = set(component_keys) - set(result)
        result.extend(remaining)
        return result

    def _generate_rollback_steps(
        self,
        deployment_order: list[str],
    ) -> list[str]:
        if not deployment_order:
            return ["No components to roll back"]
        reversed_order = list(reversed(deployment_order))
        steps = [
            f"Step {i + 1}: Roll back '{component}'"
            for i, component in enumerate(reversed_order)
        ]
        steps.append("Step final: Verify rollback integrity")
        return steps
