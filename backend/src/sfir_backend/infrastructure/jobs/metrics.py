from __future__ import annotations

from collections import Counter, deque
from typing import Any


class WorkerMetrics:
    def __init__(self) -> None:
        self._total_assigned: int = 0
        self._total_completed: int = 0
        self._total_failed: int = 0
        self._total_recovered: int = 0

    def record_assigned(self) -> None:
        self._total_assigned += 1

    def record_completed(self) -> None:
        self._total_completed += 1

    def record_failed(self) -> None:
        self._total_failed += 1

    def record_recovered(self) -> None:
        self._total_recovered += 1

    def snapshot(self) -> dict[str, int]:
        return {
            "assigned": self._total_assigned,
            "completed": self._total_completed,
            "failed": self._total_failed,
            "recovered": self._total_recovered,
        }


class QueueMetrics:
    def __init__(self) -> None:
        self._enqueued: Counter[str] = Counter()
        self._dequeued: Counter[str] = Counter()
        self._wait_times: deque[float] = deque(maxlen=1000)

    def record_enqueue(self, queue_type: str) -> None:
        self._enqueued[queue_type] += 1

    def record_dequeue(self, queue_type: str, wait_seconds: float = 0.0) -> None:
        self._dequeued[queue_type] += 1
        if wait_seconds > 0:
            self._wait_times.append(wait_seconds)

    def average_wait_time(self) -> float:
        if not self._wait_times:
            return 0.0
        return sum(self._wait_times) / len(self._wait_times)

    def snapshot(self) -> dict[str, Any]:
        return {
            "enqueued": dict(self._enqueued),
            "dequeued": dict(self._dequeued),
            "avg_wait_ms": self.average_wait_time() * 1000,
        }


class RetryMetrics:
    def __init__(self) -> None:
        self._total_retries: int = 0
        self._total_poison: int = 0
        self._retries_by_type: Counter[str] = Counter()
        self._retry_success: int = 0
        self._retry_failure: int = 0

    def record_retry(self, job_type: str) -> None:
        self._total_retries += 1
        self._retries_by_type[job_type] += 1

    def record_poison(self) -> None:
        self._total_poison += 1

    def record_success(self) -> None:
        self._retry_success += 1

    def record_failure(self) -> None:
        self._retry_failure += 1

    def snapshot(self) -> dict[str, Any]:
        return {
            "total_retries": self._total_retries,
            "total_poison": self._total_poison,
            "retries_by_type": dict(self._retries_by_type),
            "retry_success": self._retry_success,
            "retry_failure": self._retry_failure,
        }


class FailureMetrics:
    def __init__(self) -> None:
        self._failures_by_type: Counter[str] = Counter()
        self._failures_by_reason: Counter[str] = Counter()
        self._total_failures: int = 0

    def record_failure(self, job_type: str, reason: str = "") -> None:
        self._total_failures += 1
        self._failures_by_type[job_type] += 1
        if reason:
            self._failures_by_reason[reason] += 1

    def snapshot(self) -> dict[str, Any]:
        return {
            "total_failures": self._total_failures,
            "failures_by_type": dict(self._failures_by_type),
            "failures_by_reason": dict(self._failures_by_reason),
        }


class LatencyMetrics:
    def __init__(self, window_size: int = 1000) -> None:
        self._execution_times: deque[float] = deque(maxlen=window_size)
        self._queue_wait_times: deque[float] = deque(maxlen=window_size)

    def record_execution(self, seconds: float) -> None:
        self._execution_times.append(seconds)

    def record_queue_wait(self, seconds: float) -> None:
        self._queue_wait_times.append(seconds)

    def avg_execution_time(self) -> float:
        if not self._execution_times:
            return 0.0
        return sum(self._execution_times) / len(self._execution_times)

    def avg_queue_wait_time(self) -> float:
        if not self._queue_wait_times:
            return 0.0
        return sum(self._queue_wait_times) / len(self._queue_wait_times)

    def p95_execution_time(self) -> float:
        if not self._execution_times:
            return 0.0
        sorted_times = sorted(self._execution_times)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[idx]

    def snapshot(self) -> dict[str, float]:
        return {
            "avg_execution_time_ms": self.avg_execution_time() * 1000,
            "avg_queue_wait_ms": self.avg_queue_wait_time() * 1000,
            "p95_execution_time_ms": self.p95_execution_time() * 1000,
        }
