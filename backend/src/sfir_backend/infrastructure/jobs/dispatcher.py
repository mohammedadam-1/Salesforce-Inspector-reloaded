from __future__ import annotations

from datetime import UTC, datetime

from sfir_backend.domain.jobs.models import (
    Job,
    JobStatus,
    QueueType,
    Worker,
)
from sfir_backend.infrastructure.jobs.pool import WorkerPool
from sfir_backend.infrastructure.jobs.progress import ProgressTracker
from sfir_backend.infrastructure.jobs.queue import QueueManager


class JobDispatcher:
    def __init__(
        self,
        queue_manager: QueueManager,
        worker_pool: WorkerPool,
        progress_tracker: ProgressTracker,
    ) -> None:
        self._queue_manager = queue_manager
        self._worker_pool = worker_pool
        self._progress_tracker = progress_tracker

    def dispatch_next(self) -> Job | None:
        for qt in (QueueType.PRIORITY, QueueType.FIFO, QueueType.RETRY):
            job = self._queue_manager.dequeue(qt)
            if job is not None:
                worker = self._worker_pool.get_idle_worker(job.type)
                if worker:
                    return self._assign(job, worker)
                self._queue_manager.enqueue(job)
                return None
        return None

    def dispatch_scheduled(self) -> list[Job]:
        scheduled = self._queue_manager.process_scheduled()
        dispatched: list[Job] = []
        for job in scheduled:
            worker = self._worker_pool.get_idle_worker(job.type)
            if worker:
                dispatched.append(self._assign(job, worker))
            else:
                self._queue_manager.enqueue(job)
        return dispatched

    def dispatch_delayed(self) -> list[Job]:
        delayed = self._queue_manager.process_delayed()
        dispatched: list[Job] = []
        for job in delayed:
            worker = self._worker_pool.get_idle_worker(job.type)
            if worker:
                dispatched.append(self._assign(job, worker))
            else:
                self._queue_manager.enqueue(job)
        return dispatched

    def dispatch_recurring(self) -> list[Job]:
        recurring = self._queue_manager.process_recurring()
        dispatched: list[Job] = []
        for job in recurring:
            self._queue_manager.enqueue(job)
            worker = self._worker_pool.get_idle_worker(job.type)
            if worker:
                dispatched.append(self._assign(job, worker))
        return dispatched

    def dispatch_chained(self, parent_job: Job) -> list[Job]:
        children = self._queue_manager.get_children(parent_job.id)
        dispatched: list[Job] = []
        for child_id in children:
            job = self._find_job_by_id(child_id)
            if job and job.status == JobStatus.QUEUED:
                worker = self._worker_pool.get_idle_worker(job.type)
                if worker:
                    dispatched.append(self._assign(job, worker))
        return dispatched

    def _assign(self, job: Job, worker: Worker) -> Job:
        job = self._progress_tracker.start_job(job)
        job.started_at = datetime.now(tz=UTC)
        worker = self._worker_pool.assign_job(worker.id, job)
        return job

    def complete_job(self, job: Job, result: dict | None = None) -> Job:
        job = self._progress_tracker.complete_job(job, result)
        if job.chain_next:
            self.dispatch_chained(job)
        if worker := self._find_worker_for_job(job.id):
            self._worker_pool.release_worker(worker.id)
        return job

    def fail_job(self, job: Job, error: str) -> Job:
        job = self._progress_tracker.fail_job(job, error)
        if worker := self._find_worker_for_job(job.id):
            self._worker_pool.release_worker(worker.id)
        return job

    def _find_job_by_id(self, job_id: str) -> Job | None:
        for qt in QueueType:
            queue = self._queue_manager.get_queue(qt)
            if hasattr(queue, "iter_jobs"):
                for j in queue.iter_jobs():
                    if j.id == job_id:
                        return j
        return None

    def _find_worker_for_job(self, job_id: str) -> Worker | None:
        for worker in self._worker_pool.list_workers():
            if worker.current_job_id == job_id:
                return worker
        return None
