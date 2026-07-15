from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sfir_backend.domain.jobs.models import (
    Job,
    JobMetricsSnapshot,
    JobPriority,
    JobStatus,
    JobType,
    QueueType,
    Worker,
    WorkerStatus,
)
from sfir_backend.infrastructure.jobs.dead_letter import DeadLetterQueue
from sfir_backend.infrastructure.jobs.dispatcher import JobDispatcher
from sfir_backend.infrastructure.jobs.heartbeat import WorkerHeartbeat
from sfir_backend.infrastructure.jobs.lock import DistributedLockManager
from sfir_backend.infrastructure.jobs.manager import WorkerManager
from sfir_backend.infrastructure.jobs.metrics import (
    FailureMetrics,
    LatencyMetrics,
    QueueMetrics,
    RetryMetrics,
    WorkerMetrics,
)
from sfir_backend.infrastructure.jobs.monitor import JobMonitor
from sfir_backend.infrastructure.jobs.pool import WorkerPool
from sfir_backend.infrastructure.jobs.prioritizer import JobPrioritizer
from sfir_backend.infrastructure.jobs.progress import ProgressTracker
from sfir_backend.infrastructure.jobs.queue import QueueManager
from sfir_backend.infrastructure.jobs.recovery import JobRecoveryManager
from sfir_backend.infrastructure.jobs.retry import RetryManager
from sfir_backend.infrastructure.jobs.scheduler import JobScheduler


class JobEngine:
    def __init__(self) -> None:
        self._queue_manager = QueueManager()
        self._job_registry: dict[str, Job] = {}
        self._worker_pool = WorkerPool()
        self._heartbeat = WorkerHeartbeat()
        self._progress_tracker = ProgressTracker()
        self._retry_manager = RetryManager()
        self._lock_manager = DistributedLockManager()
        self._prioritizer = JobPrioritizer()
        self._dead_letter_queue = DeadLetterQueue()

        self._dispatcher = JobDispatcher(
            self._queue_manager,
            self._worker_pool,
            self._progress_tracker,
        )
        self._scheduler = JobScheduler(
            self._queue_manager,
            self._dispatcher,
        )
        self._monitor = JobMonitor(
            self._queue_manager,
            self._worker_pool,
        )
        self._recovery = JobRecoveryManager(
            self._queue_manager,
            self._worker_pool,
        )
        self._worker_manager = WorkerManager(
            self._worker_pool,
            self._heartbeat,
            self._progress_tracker,
            self._dispatcher,
            self._retry_manager,
        )

        self._worker_metrics = WorkerMetrics()
        self._queue_metrics = QueueMetrics()
        self._retry_metrics = RetryMetrics()
        self._failure_metrics = FailureMetrics()
        self._latency_metrics = LatencyMetrics()

    # --- Job Lifecycle ---

    def create_job(
        self,
        job_type: JobType,
        payload: dict[str, Any] | None = None,
        priority: JobPriority = JobPriority.MEDIUM,
        queue: QueueType = QueueType.FIFO,
        tenant_id: str = "",
        depends_on: list[str] | None = None,
        timeout_seconds: int = 3600,
    ) -> Job:
        job = Job(
            id=str(uuid4()),
            type=job_type,
            priority=priority,
            queue=queue,
            tenant_id=tenant_id,
            payload=payload or {},
            depends_on=depends_on or [],
            timeout_seconds=timeout_seconds,
            created_at=datetime.now(tz=UTC),
            status=JobStatus.QUEUED,
        )
        self._queue_manager.enqueue(job)
        self._queue_metrics.record_enqueue(queue.value)
        self._job_registry[job.id] = job
        return job

    def get_job_status(self, job_id: str) -> JobStatus | None:
        job = self._find_job(job_id)
        return job.status if job else None

    def get_job(self, job_id: str) -> Job | None:
        return self._find_job(job_id)

    def cancel_job(self, job_id: str) -> bool:
        job = self._find_job(job_id)
        if not job:
            return False
        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.EXPIRED):
            return False
        self._scheduler.cancel_job(job)
        return True

    def retry_job(self, job_id: str) -> bool:
        job = self._find_job(job_id)
        if not job:
            return False
        if job.status != JobStatus.FAILED:
            return False
        self._retry_metrics.record_retry(job.type.value)
        self._worker_manager.retry_job(job)
        self._queue_manager.enqueue(job)
        return True

    def pause_job(self, job_id: str) -> bool:
        job = self._find_job(job_id)
        if not job:
            return False
        if job.status not in (JobStatus.RUNNING, JobStatus.QUEUED):
            return False
        self._scheduler.pause_job(job)
        return True

    def resume_job(self, job_id: str) -> bool:
        job = self._find_job(job_id)
        if not job:
            return False
        if job.status != JobStatus.PAUSED:
            return False
        self._scheduler.resume_job(job)
        return True

    def get_job_progress(self, job_id: str) -> dict[str, Any] | None:
        job = self._find_job(job_id)
        if not job:
            return None
        progress = self._progress_tracker.get_progress(job)
        return progress.model_dump()

    # --- Worker Management ---

    def register_worker(
        self,
        name: str = "",
        supported_types: list[JobType] | None = None,
    ) -> Worker:
        return self._worker_manager.register_worker(name, supported_types)

    def unregister_worker(self, worker_id: str) -> bool:
        return self._worker_manager.unregister_worker(worker_id)

    def get_worker(self, worker_id: str) -> Worker | None:
        return self._worker_manager.get_worker(worker_id)

    def list_workers(
        self,
        status: WorkerStatus | None = None,
    ) -> list[Worker]:
        return self._worker_manager.list_workers(status)

    def send_heartbeat(self, worker_id: str) -> Worker | None:
        return self._worker_manager.send_heartbeat(worker_id)

    def scale_workers(self, target_count: int) -> int:
        return self._worker_manager.scale_workers(target_count)

    # --- Scheduling ---

    def schedule_job(
        self,
        job: Job,
        at: datetime | None = None,
        delay_seconds: int | None = None,
    ) -> None:
        self._scheduler.schedule_job(job, at, delay_seconds)

    def schedule_recurring(
        self,
        job: Job,
        interval_seconds: int,
        max_executions: int | None = None,
    ) -> None:
        self._scheduler.schedule_recurring(job, interval_seconds, max_executions)

    def start_scheduler(self) -> None:
        self._scheduler.start()

    def stop_scheduler(self) -> None:
        self._scheduler.stop()

    def tick(self) -> list[Job]:
        return self._scheduler.tick()

    # --- Job Chaining ---

    def add_chain(self, parent_id: str, child_id: str) -> None:
        self._queue_manager.add_chain(parent_id, child_id)

    # --- Distributed Locks ---

    def acquire_lock(
        self,
        key: str,
        holder_id: str,
        ttl_seconds: int = 60,
        timeout: float | None = None,
    ) -> bool:
        return self._lock_manager.acquire(key, holder_id, ttl_seconds, timeout=timeout)

    def release_lock(self, key: str, holder_id: str) -> bool:
        return self._lock_manager.release(key, holder_id)

    def is_locked(self, key: str) -> bool:
        return self._lock_manager.is_locked(key)

    def force_release_lock(self, key: str) -> bool:
        return self._lock_manager.force_release(key)

    # --- Recovery ---

    def recovery_all(self) -> dict[str, int]:
        return self._recovery.recover_all()

    # --- Dead Letter Queue ---

    def send_to_dead_letter(
        self,
        job: Job,
        reason: str = "",
    ) -> None:
        self._dead_letter_queue.send(job, reason)
        self._retry_metrics.record_poison()

    def list_dead_letter_jobs(self) -> list[Job]:
        return self._dead_letter_queue.iter_jobs()

    def requeue_from_dead_letter(self, job_id: str) -> bool:
        job = self._find_job_in_dlq(job_id)
        if not job:
            return False
        if job.retry.classification.value == "poison":
            return False
        job.status = JobStatus.QUEUED
        job.queue = QueueType.RETRY
        self._dead_letter_queue.requeue(job, QueueType.RETRY)
        self._queue_manager.enqueue(job)
        return True

    # --- Metrics ---

    def snapshot_metrics(self) -> JobMetricsSnapshot:
        return self._monitor.snapshot()

    def worker_metrics(self) -> dict[str, int]:
        return self._worker_metrics.snapshot()

    def queue_metrics(self) -> dict[str, Any]:
        return self._queue_metrics.snapshot()

    def retry_metrics(self) -> dict[str, Any]:
        return self._retry_metrics.snapshot()

    def failure_metrics(self) -> dict[str, Any]:
        return self._failure_metrics.snapshot()

    def latency_metrics(self) -> dict[str, float]:
        return self._latency_metrics.snapshot()

    # --- Recovery ---

    def recover(self) -> dict[str, int]:
        results = self._recovery.recover_all()
        stale_workers = self._worker_pool.recover_workers()
        results["workers_recovered"] = len(stale_workers)
        return results

    # --- Query ---

    def list_jobs(
        self,
        status: JobStatus | None = None,
        job_type: JobType | None = None,
        _queue: QueueType | None = None,
        tenant_id: str | None = None,
    ) -> list[Job]:
        seen: set[str] = set()
        results: list[Job] = []
        for qt in QueueType:
            queue_inst = self._queue_manager.get_queue(qt)
            if not hasattr(queue_inst, "iter_jobs"):
                continue
            for job in queue_inst.iter_jobs():
                if job.id in seen:
                    continue
                seen.add(job.id)
                if status is not None and job.status != status:
                    continue
                if job_type is not None and job.type != job_type:
                    continue
                if tenant_id and job.tenant_id != tenant_id:
                    continue
                results.append(job)
        for job in self._job_registry.values():
            if job.id in seen:
                continue
            if status is not None and job.status != status:
                continue
            if job_type is not None and job.type != job_type:
                continue
            if tenant_id and job.tenant_id != tenant_id:
                continue
            results.append(job)
        return results

    # --- Internal ---

    def _find_job(self, job_id: str) -> Job | None:
        for qt in QueueType:
            queue = self._queue_manager.get_queue(qt)
            if hasattr(queue, "iter_jobs"):
                for job in queue.iter_jobs():
                    if job.id == job_id:
                        return job
        return self._job_registry.get(job_id)

    def _find_job_in_dlq(self, job_id: str) -> Job | None:
        for job in self._dead_letter_queue.iter_jobs():
            if job.id == job_id:
                return job
        return None
