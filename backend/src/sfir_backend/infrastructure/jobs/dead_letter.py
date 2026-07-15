from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sfir_backend.domain.jobs.models import Job, JobStatus, QueueType
from sfir_backend.infrastructure.jobs.queue import FIFOQueue


class DeadLetterQueue:
    def __init__(self, max_entries: int = 1000) -> None:
        self._queue = FIFOQueue()
        self._max_entries = max_entries
        self._dead_letter_count: int = 0
        self._poison_count: int = 0

    def send(
        self,
        job: Job,
        reason: str = "",
        error_details: dict[str, Any] | None = None,
    ) -> None:
        job.status = JobStatus.FAILED
        job.metadata["dead_letter_reason"] = reason
        job.metadata["dead_letter_at"] = datetime.now(tz=UTC).isoformat()
        if error_details:
            job.metadata["dead_letter_details"] = error_details
        if self._queue.size() < self._max_entries:
            self._queue.enqueue(job)
        self._dead_letter_count += 1
        if job.retry.classification.value == "poison":
            self._poison_count += 1

    def receive(self) -> Job | None:
        return self._queue.dequeue()

    def peek(self) -> Job | None:
        return self._queue.peek()

    def size(self) -> int:
        return self._queue.size()

    def is_empty(self) -> bool:
        return self._queue.is_empty()

    def clear(self) -> None:
        self._queue.clear()
        self._dead_letter_count = 0
        self._poison_count = 0

    def requeue(self, job: Job, target_queue: QueueType) -> None:
        job.status = JobStatus.QUEUED
        job.queue = target_queue
        self._queue.remove(job.id)

    def iter_jobs(self) -> list[Job]:
        return self._queue.iter_jobs()

    @property
    def dead_letter_count(self) -> int:
        return self._dead_letter_count

    @property
    def poison_count(self) -> int:
        return self._poison_count
