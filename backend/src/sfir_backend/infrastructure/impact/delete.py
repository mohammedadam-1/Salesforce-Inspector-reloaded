from __future__ import annotations

from typing import Any

from sfir_backend.domain.impact.models import (
    AffectedComponent,
    ChangeType,
    ImpactStatus,
    RecommendedAction,
)
from sfir_backend.infrastructure.impact.analyzer import DependencyImpactAnalyzer
from sfir_backend.infrastructure.impact.blast_radius import BlastRadiusCalculator
from sfir_backend.infrastructure.impact.risk import RiskCalculator


class DeleteAnalyzer:
    def __init__(
        self,
        impact_analyzer: DependencyImpactAnalyzer,
        blast_calculator: BlastRadiusCalculator,
        risk_calculator: RiskCalculator,
    ) -> None:
        self._impact = impact_analyzer
        self._blast = blast_calculator
        self._risk = risk_calculator

    def analyze_field_delete(
        self,
        field_name: str,
        object_name: str,
    ) -> dict[str, Any]:
        component_key = f"field:{object_name}.{field_name}"
        graph = self._impact._graph_engine.graph
        node = graph.get_node(component_key)
        if not node:
            return {
                "affected": [],
                "blast_radius": self._blast.calculate(graph, component_key),
                "risk": self._risk.calculate(
                    self._blast.calculate(graph, component_key), "field",
                ),
                "warnings": [f"Field '{object_name}.{field_name}' not found in graph"],
                "recommended_actions": [],
            }

        affected, paths = self._impact.find_impacted(
            component_key, change_type=ChangeType.DELETE, max_depth=10,
        )
        blast = self._blast.calculate(graph, component_key, max_depth=10)
        risk = self._risk.calculate(blast, "field", max_depth=blast.max_depth)

        blocking = [
            c for c in affected
            if c.status == ImpactStatus.BLOCKING
        ]
        warnings = self._generate_field_delete_warnings(
            object_name, field_name, affected,
        )
        actions = self._generate_field_delete_actions(
            object_name, field_name, affected,
        )
        return {
            "affected": affected,
            "paths": paths,
            "blast_radius": blast,
            "risk": risk,
            "blocking_components": blocking,
            "warnings": warnings,
            "recommended_actions": actions,
        }

    def analyze_object_delete(
        self,
        object_name: str,
    ) -> dict[str, Any]:
        component_key = f"object:{object_name}"
        graph = self._impact._graph_engine.graph

        affected, paths = self._impact.find_impacted(
            component_key, change_type=ChangeType.DELETE, max_depth=10,
        )
        blast = self._blast.calculate(graph, component_key, max_depth=10)
        risk = self._risk.calculate(
            blast, "object",
            has_cycles=blast.has_circular_dependency,
            max_depth=blast.max_depth,
        )
        blocking = [
            c for c in affected
            if c.status == ImpactStatus.BLOCKING
        ]
        warnings = self._generate_object_delete_warnings(object_name, affected)
        actions = self._generate_object_delete_actions(object_name, affected)
        return {
            "affected": affected,
            "paths": paths,
            "blast_radius": blast,
            "risk": risk,
            "blocking_components": blocking,
            "warnings": warnings,
            "recommended_actions": actions,
        }

    def analyze_flow_delete(
        self,
        flow_name: str,
    ) -> dict[str, Any]:
        component_key = f"flow:{flow_name}"
        graph = self._impact._graph_engine.graph
        affected, paths = self._impact.find_impacted(
            component_key, change_type=ChangeType.DELETE, max_depth=10,
        )
        blast = self._blast.calculate(graph, component_key, max_depth=10)
        risk = self._risk.calculate(blast, "flow", max_depth=blast.max_depth)
        return {
            "affected": affected,
            "paths": paths,
            "blast_radius": blast,
            "risk": risk,
            "blocking_components": [
                c for c in affected if c.status == ImpactStatus.BLOCKING
            ],
            "warnings": self._generate_flow_delete_warnings(flow_name, affected),
            "recommended_actions": [
                RecommendedAction(
                    action="verify_no_active_processes",
                    description=f"Ensure no active processes reference flow '{flow_name}'",
                    priority="high",
                ),
                RecommendedAction(
                    action="update_references",
                    description=f"Remove or replace references to flow '{flow_name}'",
                    priority="medium",
                ),
            ],
        }

    def analyze_apex_delete(
        self,
        apex_class_name: str,
    ) -> dict[str, Any]:
        component_key = f"apex_class:{apex_class_name}"
        graph = self._impact._graph_engine.graph
        affected, paths = self._impact.find_impacted(
            component_key, change_type=ChangeType.DELETE, max_depth=10,
        )
        blast = self._blast.calculate(graph, component_key, max_depth=10)
        risk = self._risk.calculate(blast, "apex_class", max_depth=blast.max_depth)
        return {
            "affected": affected,
            "paths": paths,
            "blast_radius": blast,
            "risk": risk,
            "blocking_components": [
                c for c in affected if c.status == ImpactStatus.BLOCKING
            ],
            "warnings": self._generate_apex_delete_warnings(apex_class_name, affected),
            "recommended_actions": [
                RecommendedAction(
                    action="verify_test_coverage",
                    description=f"Check test coverage for '{apex_class_name}' before deletion",
                    priority="high",
                ),
            ],
        }

    def analyze_validation_rule_delete(
        self,
        rule_name: str,
        object_name: str,
    ) -> dict[str, Any]:
        component_key = f"validation_rule:{object_name}.{rule_name}"
        graph = self._impact._graph_engine.graph
        affected, paths = self._impact.find_impacted(
            component_key, change_type=ChangeType.DELETE, max_depth=10,
        )
        blast = self._blast.calculate(graph, component_key, max_depth=10)
        risk = self._risk.calculate(blast, "validation_rule", max_depth=blast.max_depth)
        return {
            "affected": affected,
            "paths": paths,
            "blast_radius": blast,
            "risk": risk,
            "blocking_components": [],
            "warnings": self._generate_validation_delete_warnings(
                object_name, rule_name,
            ),
            "recommended_actions": [
                RecommendedAction(
                    action="verify_data_integrity",
                    description=f"Data integrity may be affected by removing rule '{rule_name}'",
                    priority="medium",
                ),
            ],
        }

    def _generate_validation_delete_warnings(
        self,
        object_name: str,
        rule_name: str,
    ) -> list[str]:
        return [
            f"Deleting validation rule '{rule_name}' on '{object_name}' may affect data integrity",
        ]

    def _generate_field_delete_warnings(
        self,
        object_name: str,
        field_name: str,
        affected: list[AffectedComponent],
    ) -> list[str]:
        warnings = [
            f"Deleting field '{object_name}.{field_name}' will impact "
            f"{len(affected)} dependent components",
        ]
        for c in affected:
            if c.status == ImpactStatus.BLOCKING:
                warnings.append(
                    f"BLOCKING: {c.component_type} '{c.component_key}' "
                    f"will be affected ({c.severity})",
                )
        return warnings

    def _generate_object_delete_warnings(
        self,
        object_name: str,
        affected: list[AffectedComponent],
    ) -> list[str]:
        warnings = [
            f"Deleting object '{object_name}' will impact "
            f"{len(affected)} dependent components",
        ]
        for c in affected:
            if c.status == ImpactStatus.BLOCKING:
                warnings.append(
                    f"BLOCKING: {c.component_type} '{c.component_key}' "
                    f"will be affected ({c.severity})",
                )
        return warnings

    def _generate_flow_delete_warnings(
        self,
        flow_name: str,
        affected: list[AffectedComponent],
    ) -> list[str]:
        return [
            f"Deleting flow '{flow_name}' will impact {len(affected)} component(s)",
        ] + [
            f"{c.component_type} '{c.component_key}' depends on this flow"
            for c in affected
        ]

    def _generate_apex_delete_warnings(
        self,
        apex_class_name: str,
        affected: list[AffectedComponent],
    ) -> list[str]:
        return [
            f"Deleting Apex class '{apex_class_name}' will impact "
            f"{len(affected)} component(s)",
        ] + [
            f"{c.component_type} '{c.component_key}' depends on this class"
            for c in affected
        ]

    def _generate_object_delete_actions(
        self,
        object_name: str,
        affected: list[AffectedComponent],
    ) -> list[RecommendedAction]:
        return [
            RecommendedAction(
                action="backup_data",
                description=f"Backup data for '{object_name}' before deletion",
                priority="critical",
            ),
        ]

    def _generate_field_delete_actions(
        self,
        object_name: str,
        field_name: str,
        affected: list[AffectedComponent],
    ) -> list[RecommendedAction]:
        return [
            RecommendedAction(
                action="remove_field_references",
                description=(
                    f"Remove all references to '{object_name}.{field_name}' "
                    f"in {len(affected)} component(s)"
                ),
                priority="high",
            ),
        ]
