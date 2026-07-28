from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PipelineResult:
    success: bool
    component_type: str
    total_count: int = 0
    parsed_count: int = 0
    saved_count: int = 0
    indexed_count: int = 0
    errors: list[str] = field(default_factory=list)
    timing: dict[str, float] = field(default_factory=dict)
    stage_errors: dict[str, list[str]] = field(default_factory=dict)
