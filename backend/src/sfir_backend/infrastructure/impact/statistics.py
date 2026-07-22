from __future__ import annotations

import time
from collections import Counter
from typing import Any


class ImpactStatistics:
    def __init__(self) -> None:
        self._analysis_count: int = 0
        self._simulation_count: int = 0
        self._total_latency_ms: float = 0.0
        self._analysis_types: Counter[str] = Counter()
        self._severity_counts: Counter[str] = Counter()
        self._failure_count: int = 0
        self._total_affected: int = 0
        self._start_time: float = time.time()

    def record_analysis(
        self,
        analysis_type: str,
        severity: str,
        affected_count: int,
        latency_ms: float,
        success: bool = True,
    ) -> None:
        self._analysis_count += 1
        if analysis_type == "simulation":
            self._simulation_count += 1
        self._total_latency_ms += latency_ms
        self._analysis_types[analysis_type] += 1
        self._severity_counts[severity] += 1
        self._total_affected += affected_count
        if not success:
            self._failure_count += 1

    def snapshot(self) -> dict[str, Any]:
        uptime = time.time() - self._start_time
        avg_latency = (
            self._total_latency_ms / self._analysis_count
            if self._analysis_count > 0 else 0.0
        )
        return {
            "total_analyses": self._analysis_count,
            "total_simulations": self._simulation_count,
            "total_failures": self._failure_count,
            "avg_latency_ms": round(avg_latency, 2),
            "total_latency_ms": round(self._total_latency_ms, 2),
            "analysis_types": dict(self._analysis_types),
            "severity_counts": dict(self._severity_counts),
            "total_affected_components": self._total_affected,
            "avg_affected_per_analysis": round(
                self._total_affected / self._analysis_count, 1,
            ) if self._analysis_count > 0 else 0.0,
            "uptime_seconds": round(uptime, 2),
        }

    def reset(self) -> None:
        self._analysis_count = 0
        self._simulation_count = 0
        self._total_latency_ms = 0.0
        self._analysis_types.clear()
        self._severity_counts.clear()
        self._failure_count = 0
        self._total_affected = 0
        self._start_time = time.time()
