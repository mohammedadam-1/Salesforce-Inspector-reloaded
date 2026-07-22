from __future__ import annotations

import time
from collections import Counter

from sfir_backend.domain.jobs.models import (
    Job,
    JobMetricsSnapshot,
    JobStatus,
    QueueType,
)
from sfir_backend.infrastructure.jobs.pool import WorkerPool
from sfir_backend.infrastructure.jobs.queue import QueueManager


class JobMonitor:
    def __init__(
        self,
        queue_manager: QueueManager,
        worker_pool: WorkerPool,
    ) -> None:
        self._queue_manager = queue_manager
        self._worker_pool = worker_pool
        self._snapshots: list[JobMetricsSnapshot] = []
        self._execution_times: dict[str, float] = {}
        self._queue_wait_times: dict[str, float] = {}
        self._started_at: float = time.monotonic()

    def record_execution_time(self, job_id: str, seconds: float) -> None:
        self._execution_times[job_id] = seconds

    def record_queue_wait_time(self, job_id: str, seconds: float) -> None:
        self._queue_wait_times[job_id] = seconds

    def snapshot(self) -> JobMetricsSnapshot:
        all_jobs = self._collect_all_jobs()

        jobs_by_status: dict[str, int] = Counter()
        jobs_by_type: dict[str, int] = Counter()
        jobs_by_queue: dict[str, int] = Counter()

        for job in all_jobs:
            jobs_by_status[job.status.value] += 1
            jobs_by_type[job.type.value] += 1
            jobs_by_queue[job.queue.value] += 1

        workers = self._worker_pool.list_workers()

        workers_by_status: dict[str, int] = Counter()
        for w in workers:
            workers_by_status[w.status.value] += 1

        queue_depths = self._queue_manager.queue_depths()

        avg_wait = (
            sum(self._queue_wait_times.values()) / len(self._queue_wait_times)
            if self._queue_wait_times
            else 0.0
        )
        avg_exec = (
            sum(self._execution_times.values()) / len(self._execution_times)
            if self._execution_times
            else 0.0
        )

        uptime = time.monotonic() - self._started_at
        throughput = (
            (len(self._execution_times) / (uptime / 60.0)) if uptime > 0 else 0.0
        )

        snapshot = JobMetricsSnapshot(
            total_jobs=len(all_jobs),
            jobs_by_status=dict(jobs_by_status),
            jobs_by_type=dict(jobs_by_type),
            jobs_by_queue=dict(jobs_by_queue),
            total_workers=len(workers),
            workers_by_status=dict(workers_by_status),
            queue_depths=queue_depths,
            avg_queue_wait_ms=avg_wait * 1000,
            avg_execution_time_ms=avg_exec * 1000,
            retry_count=jobs_by_status.get(JobStatus.RETRYING.value, 0),
            dead_letter_count=queue_depths.get(QueueType.DEAD_LETTER.value, 0),
            throughput_per_minute=throughput,
        )
        self._snapshots.append(snapshot)
        return snapshot

    def _collect_all_jobs(self) -> list[Job]:
        all_jobs: list[Job] = []
        for qt in QueueType:
            queue = self._queue_manager.get_queue(qt)
            if hasattr(queue, "iter_jobs"):
                all_jobs.extend(queue.iter_jobs())
        return all_jobs

    def get_recent_snapshots(
        self,
        count: int = 10,
    ) -> list[JobMetricsSnapshot]:
        return self._snapshots[-count:]

    def uptime_seconds(self) -> float:
        return time.monotonic() - self._started_at
