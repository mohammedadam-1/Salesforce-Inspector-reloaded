from __future__ import annotations

import time
from collections import Counter

from sfir_backend.domain.documentation.models import GenerationMetricsSnapshot


class GenerationMetrics:
    def __init__(self) -> None:
        self._start_time: float = time.time()
        self._total_pages: int = 0
        self._total_reports: int = 0
        self._total_exports: int = 0
        self._total_errors: int = 0
        self._total_generation_time_ms: float = 0.0
        self._cache_hits: int = 0
        self._cache_misses: int = 0
        self._pages_by_type: Counter[str] = Counter()
        self._reports_by_type: Counter[str] = Counter()

    def record_page(self, component_type: str, time_ms: float) -> None:
        self._total_pages += 1
        self._total_generation_time_ms += time_ms
        self._pages_by_type[component_type] += 1

    def record_report(self, report_type: str) -> None:
        self._total_reports += 1
        self._reports_by_type[report_type] += 1

    def record_export(self) -> None:
        self._total_exports += 1

    def record_error(self) -> None:
        self._total_errors += 1

    def record_cache_hit(self) -> None:
        self._cache_hits += 1

    def record_cache_miss(self) -> None:
        self._cache_misses += 1

    def snapshot(self) -> GenerationMetricsSnapshot:
        uptime = time.time() - self._start_time
        avg_time = (
            self._total_generation_time_ms / self._total_pages
            if self._total_pages > 0 else 0.0
        )
        return GenerationMetricsSnapshot(
            total_pages_generated=self._total_pages,
            total_reports_generated=self._total_reports,
            total_exports=self._total_exports,
            total_errors=self._total_errors,
            avg_generation_time_ms=round(avg_time, 2),
            cache_hits=self._cache_hits,
            cache_misses=self._cache_misses,
            uptime_seconds=round(uptime, 2),
            pages_by_type=dict(self._pages_by_type),
            reports_by_type=dict(self._reports_by_type),
        )
