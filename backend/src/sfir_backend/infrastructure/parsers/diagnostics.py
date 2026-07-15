from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ParseDiagnostic(BaseModel):
    metadata_type: str = ""
    component_api_name: str = ""
    duration_ms: float = 0.0
    success: bool = True
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    reference_count: int = 0
    relationship_count: int = 0


class ParserMetrics:
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._durations: dict[str, list[float]] = {}
        self._failures: dict[str, int] = {}
        self._warnings: dict[str, int] = {}

    def record_parse(
        self,
        metadata_type: str,
        duration_ms: float,
        success: bool,
        warnings_count: int = 0,
    ) -> None:
        self._counts[metadata_type] = self._counts.get(metadata_type, 0) + 1
        if metadata_type not in self._durations:
            self._durations[metadata_type] = []
        self._durations[metadata_type].append(duration_ms)
        if not success:
            self._failures[metadata_type] = self._failures.get(metadata_type, 0) + 1
        if warnings_count:
            self._warnings[metadata_type] = self._warnings.get(metadata_type, 0) + warnings_count

    def total_parses(self) -> int:
        return sum(self._counts.values())

    def total_failures(self) -> int:
        return sum(self._failures.values())

    def get_stats(self, metadata_type: str) -> dict[str, Any]:
        durations = self._durations.get(metadata_type, [])
        avg_duration = sum(durations) / len(durations) if durations else 0.0
        return {
            "type": metadata_type,
            "count": self._counts.get(metadata_type, 0),
            "failures": self._failures.get(metadata_type, 0),
            "warnings": self._warnings.get(metadata_type, 0),
            "avg_duration_ms": avg_duration,
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "total_parses": self.total_parses(),
            "total_failures": self.total_failures(),
            "by_type": {
                t: self.get_stats(t) for t in self._counts
            },
        }
