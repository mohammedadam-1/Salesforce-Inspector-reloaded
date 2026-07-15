from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sfir_backend.domain.jobs.models import (
    Job,
    JobStatus,
    JobType,
    QueueType,
    Worker,
    WorkerStatus,
)
from sfir_backend.infrastructure.jobs.dispatcher import JobDispatcher
from sfir_backend.infrastructure.jobs.heartbeat import WorkerHeartbeat
from sfir_backend.infrastructure.jobs.pool import WorkerPool
from sfir_backend.infrastructure.jobs.progress import ProgressTracker
from sfir_backend.infrastructure.jobs.retry import RetryManager


class WorkerManager:
    def __init__(
        self,
        pool: WorkerPool,
        heartbeat: WorkerHeartbeat,
        progress: ProgressTracker,
        dispatcher: JobDispatcher,
        retry: RetryManager,
    ) -> None:
        self._pool = pool
        self._heartbeat = heartbeat
        self._progress = progress
        self._dispatcher = dispatcher
        self._retry = retry

    def register_worker(
        self, name: str = "", supported_types: list[JobType] | None = None
    ) -> Worker:
        worker = Worker(
            id=str(uuid4()),
            name=name or f"worker-{str(uuid4())[:8]}",
            status=WorkerStatus.IDLE,
            supported_job_types=supported_types or list(JobType),
            registered_at=datetime.now(tz=UTC),
        )
        self._pool.register_worker(worker)
        return worker

    def unregister_worker(self, worker_id: str) -> bool:
        return self._pool.unregister_worker(worker_id)

    def get_worker(self, worker_id: str) -> Worker | None:
        return self._pool.get_worker(worker_id)

    def list_workers(self, status: WorkerStatus | None = None) -> list[Worker]:
        return self._pool.list_workers(status)

    def send_heartbeat(self, worker_id: str) -> Worker | None:
        return self._pool.update_heartbeat(worker_id)

    def scale_workers(self, target_count: int, template: Worker | None = None) -> int:
        if template is None:
            template = Worker(name="auto-scaled")
        return self._pool.scale_to(target_count, template)

    def execute_job(self, job: Job) -> Job:
        worker = self._pool.get_idle_worker(job.type)
        if not worker:
            job.status = JobStatus.QUEUED
            return job
        job = self._progress.start_job(job)
        job.started_at = datetime.now(tz=UTC)
        worker = self._pool.assign_job(worker.id, job)
        return job

    def complete_job(self, job: Job, result: dict | None = None) -> Job:
        return self._dispatcher.complete_job(job, result)

    def fail_job(self, job: Job, error: str) -> Job:
        return self._dispatcher.fail_job(job, error)

    def retry_job(self, job: Job) -> Job:
        job = self._retry.record_attempt(job, job.retry.last_error)
        if job.status == JobStatus.RETRYING:
            job.queue = QueueType.RETRY
            job.status = JobStatus.QUEUED
        return job
