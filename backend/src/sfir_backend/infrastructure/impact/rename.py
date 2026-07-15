from __future__ import annotations

from typing import Any

from sfir_backend.domain.impact.models import (
    AffectedComponent,
    ChangeType,
    ImpactSeverity,
    ImpactStatus,
    RecommendedAction,
)
from sfir_backend.infrastructure.impact.analyzer import DependencyImpactAnalyzer
from sfir_backend.infrastructure.impact.blast_radius import BlastRadiusCalculator
from sfir_backend.infrastructure.impact.risk import RiskCalculator


class RenameAnalyzer:
    def __init__(
        self,
        impact_analyzer: DependencyImpactAnalyzer,
        blast_calculator: BlastRadiusCalculator,
        risk_calculator: RiskCalculator,
    ) -> None:
        self._impact = impact_analyzer
        self._blast = blast_calculator
        self._risk = risk_calculator

    def analyze_field_rename(
        self,
        object_name: str,
        old_field_name: str,
        new_field_name: str,
    ) -> dict[str, Any]:
        component_key = f"field:{object_name}.{old_field_name}"
        graph = self._impact._graph_engine.graph

        affected, paths = self._impact.find_impacted(
            component_key, change_type=ChangeType.RENAME, max_depth=10,
        )
        blast = self._blast.calculate(graph, component_key, max_depth=10)
        risk = self._risk.calculate(blast, "field", max_depth=blast.max_depth)

        return {
            "affected": affected,
            "paths": paths,
            "blast_radius": blast,
            "risk": risk,
            "warnings": self._generate_field_rename_warnings(
                object_name, old_field_name, new_field_name, affected,
            ),
            "recommended_actions": self._generate_field_rename_actions(
                object_name, old_field_name, new_field_name, affected,
            ),
        }

    def analyze_object_rename(
        self,
        old_name: str,
        new_name: str,
    ) -> dict[str, Any]:
        component_key = f"object:{old_name}"
        graph = self._impact._graph_engine.graph

        affected, paths = self._impact.find_impacted(
            component_key, change_type=ChangeType.RENAME, max_depth=10,
        )
        blast = self._blast.calculate(graph, component_key, max_depth=10)
        risk = self._risk.calculate(blast, "object", max_depth=blast.max_depth)

        return {
            "affected": affected,
            "paths": paths,
            "blast_radius": blast,
            "risk": risk,
            "warnings": self._generate_object_rename_warnings(
                old_name, new_name, affected,
            ),
            "recommended_actions": self._generate_object_rename_actions(
                old_name, new_name, affected,
            ),
        }

    def _generate_field_rename_warnings(
        self,
        object_name: str,
        old_field: str,
        new_field: str,
        affected: list[AffectedComponent],
    ) -> list[str]:
        warnings = [
            f"Renaming '{object_name}.{old_field}' to '{new_field}' "
            f"will impact {len(affected)} component(s)",
        ]
        for c in affected:
            warnings.append(
                f"  - {c.component_type} '{c.component_key}' "
                f"(depth {c.dependency_depth})"
            )
        return warnings

    def _generate_field_rename_actions(
        self,
        object_name: str,
        old_field: str,
        new_field: str,
        affected: list[AffectedComponent],
    ) -> list[RecommendedAction]:
        return [
            RecommendedAction(
                action="update_field_references",
                description=(
                    f"Update field references from '{old_field}' to '{new_field}' "
                    f"in {len(affected)} component(s)"
                ),
                priority="high",
            ),
            RecommendedAction(
                action="update_validation_rules",
                description=(
                    f"Update formulas/validation rules referencing "
                    f"'{object_name}.{old_field}'"
                ),
                priority="high",
            ),
        ]

    def _generate_object_rename_warnings(
        self,
        old_name: str,
        new_name: str,
        affected: list[AffectedComponent],
    ) -> list[str]:
        warnings = [
            f"Renaming object '{old_name}' to '{new_name}' "
            f"will impact {len(affected)} component(s)",
        ]
        for c in affected:
            warnings.append(
                f"  - {c.component_type} '{c.component_key}' "
                f"(depth {c.dependency_depth})"
            )
        return warnings

    def _generate_object_rename_actions(
        self,
        old_name: str,
        new_name: str,
        affected: list[AffectedComponent],
    ) -> list[RecommendedAction]:
        return [
            RecommendedAction(
                action="update_object_references",
                description=(
                    f"Update all references from '{old_name}' to '{new_name}' "
                    f"in {len(affected)} component(s)"
                ),
                priority="critical",
            ),
            RecommendedAction(
                action="update_field_definitions",
                description=(
                    f"Update custom field definitions that reference "
                    f"object '{old_name}'"
                ),
                priority="high",
            ),
        ]
