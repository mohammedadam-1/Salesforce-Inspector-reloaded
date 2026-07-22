from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sfir_backend.domain.jobs.models import Job, JobType, Worker, WorkerStatus
from sfir_backend.infrastructure.jobs.heartbeat import WorkerHeartbeat


class WorkerPool:
    def __init__(self, heartbeat: WorkerHeartbeat | None = None) -> None:
        self._workers: dict[str, Worker] = {}
        self._heartbeat = heartbeat or WorkerHeartbeat()

    def register_worker(self, worker: Worker) -> Worker:
        self._workers[worker.id] = worker
        return worker

    def unregister_worker(self, worker_id: str) -> bool:
        if worker_id in self._workers:
            del self._workers[worker_id]
            return True
        return False

    def get_worker(self, worker_id: str) -> Worker | None:
        return self._workers.get(worker_id)

    def get_idle_worker(
        self,
        job_type: JobType | None = None,
    ) -> Worker | None:
        for worker in self._workers.values():
            if worker.status != WorkerStatus.IDLE:
                continue
            if job_type and job_type not in worker.supported_job_types:
                continue
            return worker
        return None

    def assign_job(self, worker_id: str, job: Job) -> Worker | None:
        worker = self._workers.get(worker_id)
        if not worker:
            return None
        worker = self._heartbeat.mark_busy(worker)
        worker.current_job_id = job.id
        return worker

    def release_worker(self, worker_id: str) -> Worker | None:
        worker = self._workers.get(worker_id)
        if not worker:
            return None
        worker = self._heartbeat.mark_idle(worker)
        return worker

    def list_workers(
        self,
        status: WorkerStatus | None = None,
    ) -> list[Worker]:
        if status is None:
            return list(self._workers.values())
        return [w for w in self._workers.values() if w.status == status]

    def worker_count(self, status: WorkerStatus | None = None) -> int:
        if status is None:
            return len(self._workers)
        return sum(1 for w in self._workers.values() if w.status == status)

    def recover_workers(self) -> list[Worker]:
        workers = list(self._workers.values())
        return self._heartbeat.recover_stale_workers(workers)

    def update_heartbeat(self, worker_id: str) -> Worker | None:
        worker = self._workers.get(worker_id)
        if not worker:
            return None
        worker = self._heartbeat.send_heartbeat(worker)
        return worker

    def scale_to(self, target_count: int, worker_template: Worker) -> int:
        current = len(self._workers)
        if target_count > current:
            for _ in range(target_count - current):
                w = worker_template.model_copy()
                w.id = str(uuid4())
                w.status = WorkerStatus.IDLE
                w.registered_at = datetime.now(tz=UTC)
                self._workers[w.id] = w
        elif target_count < current:
            idle = self.list_workers(WorkerStatus.IDLE)
            to_remove = idle[: current - target_count]
            for w in to_remove:
                del self._workers[w.id]
        return len(self._workers)

    def shutdown_all(self) -> list[Worker]:
        affected: list[Worker] = []
        for worker in self._workers.values():
            if worker.status == WorkerStatus.BUSY:
                worker.status = WorkerStatus.SHUTTING_DOWN
                affected.append(worker)
            else:
                worker.status = WorkerStatus.OFFLINE
        return affected

    def clear(self) -> None:
        self._workers.clear()
