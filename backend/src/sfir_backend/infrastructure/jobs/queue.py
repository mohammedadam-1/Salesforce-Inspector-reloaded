from __future__ import annotations

import heapq
import time
from collections import deque
from typing import Any
from uuid import uuid4

from sfir_backend.domain.jobs.models import (
    Job,
    JobPriority,
    JobStatus,
    QueueType,
)


class PriorityQueue:
    def __init__(self) -> None:
        self._heap: list[tuple[int, float, Job]] = []
        self._job_map: dict[str, Job] = {}
        self._counter: int = 0

    def enqueue(self, job: Job, priority: int = 0) -> None:
        self._counter += 1
        entry = (-priority, time.monotonic(), job)
        heapq.heappush(self._heap, entry)
        self._job_map[job.id] = job

    def dequeue(self) -> Job | None:
        while self._heap:
            _neg_priority, _ts, job = heapq.heappop(self._heap)
            if job.id in self._job_map:
                del self._job_map[job.id]
                return job
        return None

    def peek(self) -> Job | None:
        if not self._heap:
            return None
        return self._heap[0][2]

    def remove(self, job_id: str) -> bool:
        if job_id in self._job_map:
            del self._job_map[job_id]
            return True
        return False

    def size(self) -> int:
        return len(self._job_map)

    def is_empty(self) -> bool:
        return self.size() == 0

    def clear(self) -> None:
        self._heap.clear()
        self._job_map.clear()

    def iter_jobs(self) -> list[Job]:
        return list(self._job_map.values())


class FIFOQueue:
    def __init__(self) -> None:
        self._queue: deque[Job] = deque()
        self._job_map: dict[str, Job] = {}

    def enqueue(self, job: Job) -> None:
        self._queue.append(job)
        self._job_map[job.id] = job

    def dequeue(self) -> Job | None:
        while self._queue:
            job = self._queue.popleft()
            if job.id in self._job_map:
                del self._job_map[job.id]
                return job
        return None

    def peek(self) -> Job | None:
        if not self._queue:
            return None
        return self._queue[0]

    def remove(self, job_id: str) -> bool:
        if job_id in self._job_map:
            self._queue = deque(j for j in self._queue if j.id != job_id)
            del self._job_map[job_id]
            return True
        return False

    def size(self) -> int:
        return len(self._job_map)

    def is_empty(self) -> bool:
        return self.size() == 0

    def clear(self) -> None:
        self._queue.clear()
        self._job_map.clear()

    def iter_jobs(self) -> list[Job]:
        return list(self._job_map.values())


class DelayedQueue:
    def __init__(self) -> None:
        self._delayed: dict[str, tuple[Job, float]] = {}

    def enqueue(self, job: Job, delay_seconds: int = 0) -> None:
        ready_at = time.monotonic() + delay_seconds
        self._delayed[job.id] = (job, ready_at)

    def dequeue_ready(self) -> list[Job]:
        now = time.monotonic()
        ready: list[Job] = []
        ready_ids: list[str] = []
        for job_id, (job, ready_at) in self._delayed.items():
            if now >= ready_at:
                ready.append(job)
                ready_ids.append(job_id)
        for rid in ready_ids:
            del self._delayed[rid]
        return ready

    def remove(self, job_id: str) -> bool:
        if job_id in self._delayed:
            del self._delayed[job_id]
            return True
        return False

    def size(self) -> int:
        return len(self._delayed)

    def is_empty(self) -> bool:
        return self.size() == 0

    def clear(self) -> None:
        self._delayed.clear()

    def iter_jobs(self) -> list[Job]:
        return [j for j, _ in self._delayed.values()]


class ScheduledQueue:
    def __init__(self) -> None:
        self._scheduled: dict[str, tuple[Job, float]] = {}

    def enqueue(self, job: Job, schedule_at: float | None = None) -> None:
        scheduled_time = schedule_at if schedule_at is not None else time.monotonic()
        self._scheduled[job.id] = (job, scheduled_time)

    def dequeue_due(self) -> list[Job]:
        now = time.monotonic()
        due: list[Job] = []
        due_ids: list[str] = []
        for job_id, (job, scheduled_at) in self._scheduled.items():
            if now >= scheduled_at:
                due.append(job)
                due_ids.append(job_id)
        for did in due_ids:
            del self._scheduled[did]
        return due

    def remove(self, job_id: str) -> bool:
        if job_id in self._scheduled:
            del self._scheduled[job_id]
            return True
        return False

    def size(self) -> int:
        return len(self._scheduled)

    def is_empty(self) -> bool:
        return self.size() == 0

    def clear(self) -> None:
        self._scheduled.clear()

    def iter_jobs(self) -> list[Job]:
        return [j for j, _ in self._scheduled.values()]


class RecurringQueue:
    def __init__(self) -> None:
        self._recurring: dict[str, dict[str, Any]] = {}

    def enqueue(
        self,
        job: Job,
        interval_seconds: int,
        max_executions: int | None = None,
    ) -> None:
        self._recurring[job.id] = {
            "job": job,
            "interval": interval_seconds,
            "max_executions": max_executions,
            "execution_count": 0,
            "next_run": time.monotonic(),
        }

    def dequeue_due(self) -> list[Job]:
        now = time.monotonic()
        due: list[Job] = []
        due_ids: list[str] = []
        for job_id, info in self._recurring.items():
            if now >= info["next_run"]:
                if (
                    info["max_executions"] is not None
                    and info["execution_count"] >= info["max_executions"]
                ):
                    due_ids.append(job_id)
                    continue
                job = info["job"].model_copy()
                job.id = str(uuid4())
                job.status = JobStatus.QUEUED
                due.append(job)
                info["execution_count"] += 1
                info["next_run"] = now + info["interval"]
        for did in due_ids:
            del self._recurring[did]
        return due

    def remove(self, job_id: str) -> bool:
        if job_id in self._recurring:
            del self._recurring[job_id]
            return True
        return False

    def size(self) -> int:
        return len(self._recurring)

    def is_empty(self) -> bool:
        return self.size() == 0

    def clear(self) -> None:
        self._recurring.clear()

    def iter_jobs(self) -> list[Job]:
        return [info["job"] for info in self._recurring.values()]


class JobChainer:
    def __init__(self) -> None:
        self._chains: dict[str, list[str]] = {}

    def add_chain(self, parent_id: str, child_id: str) -> None:
        self._chains.setdefault(parent_id, []).append(child_id)

    def get_children(self, job_id: str) -> list[str]:
        return self._chains.get(job_id, [])

    def has_dependents(self, job_id: str) -> bool:
        return job_id in self._chains

    def remove_chain(self, job_id: str) -> None:
        self._chains.pop(job_id, None)

    def clear(self) -> None:
        self._chains.clear()


class QueueManager:
    def __init__(self) -> None:
        self._queues: dict[QueueType, Any] = {
            QueueType.PRIORITY: PriorityQueue(),
            QueueType.FIFO: FIFOQueue(),
            QueueType.DELAYED: DelayedQueue(),
            QueueType.SCHEDULED: ScheduledQueue(),
            QueueType.RECURRING: RecurringQueue(),
            QueueType.RETRY: PriorityQueue(),
            QueueType.DEAD_LETTER: FIFOQueue(),
        }
        self._chainer = JobChainer()

    def enqueue(self, job: Job) -> None:
        queue_type = job.queue
        if queue_type == QueueType.PRIORITY:
            priority_map = {
                JobPriority.CRITICAL: 100,
                JobPriority.HIGH: 75,
                JobPriority.MEDIUM: 50,
                JobPriority.LOW: 25,
            }
            self._queues[queue_type].enqueue(
                job, priority_map.get(job.priority, 50)
            )
        elif queue_type in (QueueType.DELAYED,):
            delay = job.metadata.get("delay_seconds", 0)
            self._queues[queue_type].enqueue(job, delay)
        elif queue_type in (QueueType.RECURRING,):
            interval = job.metadata.get("interval_seconds", 3600)
            max_exec = job.metadata.get("max_executions")
            self._queues[queue_type].enqueue(job, interval, max_exec)
        else:
            self._queues[queue_type].enqueue(job)

    def dequeue(self, queue_type: QueueType) -> Job | None:
        queue = self._queues.get(queue_type)
        if not queue:
            return None
        if hasattr(queue, "dequeue_ready"):
            items = queue.dequeue_ready()
            return items[0] if items else None
        if hasattr(queue, "dequeue_due"):
            items = queue.dequeue_due()
            return items[0] if items else None
        return queue.dequeue()

    def get_queue(self, queue_type: QueueType) -> Any:
        return self._queues.get(queue_type)

    def queue_size(self, queue_type: QueueType) -> int:
        queue = self._queues.get(queue_type)
        return queue.size() if queue else 0

    def queue_depths(self) -> dict[str, int]:
        return {qt.value: self.queue_size(qt) for qt in QueueType}

    def process_recurring(self) -> list[Job]:
        queue = self._queues[QueueType.RECURRING]
        return queue.dequeue_due()

    def process_scheduled(self) -> list[Job]:
        queue = self._queues[QueueType.SCHEDULED]
        return queue.dequeue_due()

    def process_delayed(self) -> list[Job]:
        queue = self._queues[QueueType.DELAYED]
        return queue.dequeue_ready()

    def add_chain(self, parent_id: str, child_id: str) -> None:
        self._chainer.add_chain(parent_id, child_id)

    def get_children(self, job_id: str) -> list[str]:
        return self._chainer.get_children(job_id)

    def get_chainer(self) -> JobChainer:
        return self._chainer
