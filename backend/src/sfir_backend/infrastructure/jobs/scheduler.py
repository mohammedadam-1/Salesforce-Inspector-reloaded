from __future__ import annotations

from datetime import datetime
from typing import Any

from sfir_backend.domain.jobs.models import (
    Job,
    JobStatus,
    QueueType,
)
from sfir_backend.infrastructure.jobs.dispatcher import JobDispatcher
from sfir_backend.infrastructure.jobs.queue import QueueManager


class JobScheduler:
    def __init__(
        self,
        queue_manager: QueueManager,
        dispatcher: JobDispatcher,
        poll_interval: float = 1.0,
    ) -> None:
        self._queue_manager = queue_manager
        self._dispatcher = dispatcher
        self._poll_interval = poll_interval
        self._running: bool = False
        self._scheduled_jobs: list[dict[str, Any]] = []

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def schedule_job(
        self,
        job: Job,
        at: datetime | None = None,
        delay_seconds: int | None = None,
    ) -> None:
        if at is not None:
            job.queue = QueueType.SCHEDULED
            job.scheduled_at = at
            job.status = JobStatus.QUEUED
            schedule_ts = at.timestamp()
            self._queue_manager.get_queue(QueueType.SCHEDULED).enqueue(
                job, schedule_ts
            )
        elif delay_seconds is not None and delay_seconds > 0:
            job.queue = QueueType.DELAYED
            job.status = JobStatus.QUEUED
            self._queue_manager.get_queue(QueueType.DELAYED).enqueue(
                job, delay_seconds
            )
        else:
            self._queue_manager.enqueue(job)

    def schedule_recurring(
        self,
        job: Job,
        interval_seconds: int,
        max_executions: int | None = None,
    ) -> None:
        job.queue = QueueType.RECURRING
        job.status = JobStatus.QUEUED
        self._queue_manager.get_queue(QueueType.RECURRING).enqueue(
            job, interval_seconds, max_executions
        )

    def cancel_job(self, job: Job) -> Job:
        job.status = JobStatus.CANCELLED
        for qt in QueueType:
            queue = self._queue_manager.get_queue(qt)
            if hasattr(queue, "remove"):
                queue.remove(job.id)
        return job

    def pause_job(self, job: Job) -> Job:
        if job.status in (JobStatus.RUNNING, JobStatus.QUEUED):
            job.status = JobStatus.PAUSED
            for qt in QueueType:
                queue = self._queue_manager.get_queue(qt)
                if hasattr(queue, "remove"):
                    queue.remove(job.id)
        return job

    def resume_job(self, job: Job) -> Job:
        if job.status == JobStatus.PAUSED:
            job.status = JobStatus.QUEUED
            self._queue_manager.enqueue(job)
        return job

    def tick(self) -> list[Job]:
        if not self._running:
            return []
        dispatched: list[Job] = []
        dispatched.extend(self._dispatcher.dispatch_scheduled())
        dispatched.extend(self._dispatcher.dispatch_delayed())
        dispatched.extend(self._dispatcher.dispatch_recurring())
        job = self._dispatcher.dispatch_next()
        if job:
            dispatched.append(job)
        return dispatched
