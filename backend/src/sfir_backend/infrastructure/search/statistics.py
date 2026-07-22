from __future__ import annotations

import time
from collections import Counter
from typing import Any

from sfir_backend.infrastructure.search.index import SearchIndex


class SearchStatistics:
    def __init__(self, search_index: SearchIndex) -> None:
        self._index = search_index
        self._query_count: int = 0
        self._total_latency_ms: float = 0.0
        self._query_type_counts: Counter[str] = Counter()
        self._failure_count: int = 0
        self._latency_buckets: Counter[str] = Counter()
        self._last_query_time: float = 0.0
        self._start_time: float = time.time()

    def record_query(
        self,
        query_type: str,
        latency_ms: float,
        success: bool = True,
    ) -> None:
        self._query_count += 1
        self._total_latency_ms += latency_ms
        self._query_type_counts[query_type] += 1
        self._last_query_time = time.time()
        if not success:
            self._failure_count += 1
        if latency_ms < 10:
            self._latency_buckets["<10ms"] += 1
        elif latency_ms < 50:
            self._latency_buckets["10-50ms"] += 1
        elif latency_ms < 100:
            self._latency_buckets["50-100ms"] += 1
        elif latency_ms < 500:
            self._latency_buckets["100-500ms"] += 1
        elif latency_ms < 1000:
            self._latency_buckets["500ms-1s"] += 1
        else:
            self._latency_buckets[">1s"] += 1

    def snapshot(self) -> dict[str, Any]:
        uptime = time.time() - self._start_time
        avg_latency = (
            self._total_latency_ms / self._query_count if self._query_count > 0 else 0.0
        )
        return {
            "total_queries": self._query_count,
            "total_failures": self._failure_count,
            "avg_latency_ms": round(avg_latency, 2),
            "total_latency_ms": round(self._total_latency_ms, 2),
            "query_type_counts": dict(self._query_type_counts),
            "latency_buckets": dict(self._latency_buckets),
            "indexed_documents": self._index.total_documents,
            "indexed_terms": self._index._inverted.total_terms
            if hasattr(self._index, '_inverted') else 0,
            "uptime_seconds": round(uptime, 2),
            "queries_per_second": round(self._query_count / uptime, 2) if uptime > 0 else 0.0,
        }

    def reset(self) -> None:
        self._query_count = 0
        self._total_latency_ms = 0.0
        self._query_type_counts.clear()
        self._failure_count = 0
        self._latency_buckets.clear()
        self._start_time = time.time()
