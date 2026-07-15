from __future__ import annotations

from typing import Any

from sfir_backend.domain.impact.models import ChangeType
from sfir_backend.infrastructure.impact.analyzer import DependencyImpactAnalyzer


class ChangeAnalyzer:
    def __init__(self, impact_analyzer: DependencyImpactAnalyzer) -> None:
        self._impact = impact_analyzer

    def analyze_modify(self, component_key: str) -> dict[str, Any]:
        affected, paths = self._impact.find_impacted(
            component_key, change_type=ChangeType.MODIFY, max_depth=10,
        )
        return {
            "affected": affected,
            "paths": paths,
        }

    def analyze_create(self, component_key: str) -> dict[str, Any]:
        affected, paths = self._impact.find_impacted(
            component_key, change_type=ChangeType.CREATE, max_depth=5,
        )
        return {
            "affected": affected,
            "paths": paths,
        }

    def analyze_version_upgrade(self, component_key: str) -> dict[str, Any]:
        affected, paths = self._impact.find_impacted(
            component_key, change_type=ChangeType.VERSION_UPGRADE, max_depth=5,
        )
        return {
            "affected": affected,
            "paths": paths,
        }

    def analyze_bulk_change(
        self,
        component_keys: list[str],
    ) -> dict[str, Any]:
        all_affected: list[Any] = []
        all_paths: list[Any] = []
        seen_keys: set[str] = set()

        for key in component_keys:
            affected, paths = self._impact.find_impacted(
                key, change_type=ChangeType.MODIFY, max_depth=5,
            )
            for comp in affected:
                if comp.component_key not in seen_keys:
                    seen_keys.add(comp.component_key)
                    all_affected.append(comp)
            all_paths.extend(paths)

        return {
            "affected": all_affected,
            "paths": all_paths,
            "total_keys_analyzed": len(component_keys),
        }
