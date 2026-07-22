from __future__ import annotations

from datetime import UTC, datetime

from sfir_backend.domain.jobs.models import (
    Job,
    JobStatus,
    QueueType,
    WorkerStatus,
)
from sfir_backend.infrastructure.jobs.pool import WorkerPool
from sfir_backend.infrastructure.jobs.queue import QueueManager


class JobRecoveryManager:
    def __init__(
        self,
        queue_manager: QueueManager,
        worker_pool: WorkerPool,
        stale_timeout_seconds: int = 300,
    ) -> None:
        self._queue_manager = queue_manager
        self._worker_pool = worker_pool
        self._stale_timeout = stale_timeout_seconds

    def recover_stale_running_jobs(self) -> list[Job]:
        recovered: list[Job] = []
        for qt in QueueType:
            queue = self._queue_manager.get_queue(qt)
            if not hasattr(queue, "iter_jobs"):
                continue
            for job in queue.iter_jobs():
                if job.status != JobStatus.RUNNING:
                    continue
                if self._is_stale(job):
                    job.retry.attempt += 1
                    job.status = JobStatus.QUEUED
                    recovered.append(job)
        return recovered

    def recover_orphaned_jobs(self) -> list[Job]:
        busy_workers = self._worker_pool.list_workers(WorkerStatus.BUSY)
        busy_job_ids = {
            w.current_job_id for w in busy_workers if w.current_job_id
        }

        orphaned: list[Job] = []
        for qt in QueueType:
            queue = self._queue_manager.get_queue(qt)
            if not hasattr(queue, "iter_jobs"):
                continue
            for job in queue.iter_jobs():
                if job.status == JobStatus.RUNNING and job.id not in busy_job_ids:
                    job.status = JobStatus.QUEUED
                    orphaned.append(job)

        return orphaned

    def recover_expired_jobs(self) -> list[Job]:
        expired: list[Job] = []
        now = datetime.now(tz=UTC)
        for qt in QueueType:
            queue = self._queue_manager.get_queue(qt)
            if not hasattr(queue, "iter_jobs"):
                continue
            for job in queue.iter_jobs():
                if job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
                    continue
                if job.timeout_seconds <= 0:
                    continue
                started = job.started_at or job.created_at
                if (now - started).total_seconds() > job.timeout_seconds:
                    job.status = JobStatus.EXPIRED
                    expired.append(job)
        return expired

    def recover_dead_letter_jobs(self) -> list[Job]:
        recovered: list[Job] = []
        dlq = self._queue_manager.get_queue(QueueType.DEAD_LETTER)
        if not hasattr(dlq, "iter_jobs"):
            return recovered
        for job in dlq.iter_jobs():
            if job.retry.classification.value != "poison":
                job.status = JobStatus.QUEUED
                recovered.append(job)
        return recovered

    def _is_stale(self, job: Job) -> bool:
        if job.started_at is None:
            return False
        now = datetime.now(tz=UTC)
        elapsed = (now - job.started_at).total_seconds()
        return elapsed > self._stale_timeout

    def recover_all(self) -> dict[str, int]:
        return {
            "running": len(self.recover_stale_running_jobs()),
            "orphaned": len(self.recover_orphaned_jobs()),
            "expired": len(self.recover_expired_jobs()),
            "dead_letter": len(self.recover_dead_letter_jobs()),
        }
