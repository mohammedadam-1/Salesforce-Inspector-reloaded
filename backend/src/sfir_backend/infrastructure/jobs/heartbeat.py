from __future__ import annotations

from datetime import UTC, datetime

from sfir_backend.domain.jobs.models import Worker, WorkerStatus


class WorkerHeartbeat:
    def __init__(self, timeout_seconds: int = 90) -> None:
        self._timeout_seconds = timeout_seconds

    def send_heartbeat(self, worker: Worker) -> Worker:
        worker.last_heartbeat = datetime.now(tz=UTC)
        if worker.status in (WorkerStatus.OFFLINE, WorkerStatus.SHUTTING_DOWN, WorkerStatus.BUSY):
            worker.status = WorkerStatus.IDLE
        return worker

    def mark_busy(self, worker: Worker) -> Worker:
        worker.status = WorkerStatus.BUSY
        worker.last_heartbeat = datetime.now(tz=UTC)
        return worker

    def mark_idle(self, worker: Worker) -> Worker:
        worker.status = WorkerStatus.IDLE
        worker.last_heartbeat = datetime.now(tz=UTC)
        worker.current_job_id = None
        return worker

    def mark_degraded(self, worker: Worker, reason: str = "") -> Worker:
        worker.status = WorkerStatus.DEGRADED
        worker.last_heartbeat = datetime.now(tz=UTC)
        if reason:
            worker.metadata["degraded_reason"] = reason
        return worker

    def mark_offline(self, worker: Worker) -> Worker:
        worker.status = WorkerStatus.OFFLINE
        worker.current_job_id = None
        return worker

    def is_alive(self, worker: Worker) -> bool:
        if worker.last_heartbeat is None:
            return False
        now = datetime.now(tz=UTC)
        elapsed = (now - worker.last_heartbeat).total_seconds()
        return elapsed < self._timeout_seconds

    def is_stale(self, worker: Worker) -> bool:
        return not self.is_alive(worker)

    def seconds_since_heartbeat(self, worker: Worker) -> float:
        if worker.last_heartbeat is None:
            return float("inf")
        now = datetime.now(tz=UTC)
        return (now - worker.last_heartbeat).total_seconds()

    def check_health(self, worker: Worker) -> WorkerStatus:
        if self.is_stale(worker):
            return WorkerStatus.OFFLINE
        return worker.status

    def recover_stale_workers(
        self,
        workers: list[Worker],
    ) -> list[Worker]:
        recovered: list[Worker] = []
        for worker in workers:
            if worker.status == WorkerStatus.OFFLINE:
                continue
            if self.is_stale(worker):
                worker = self.mark_offline(worker)
                recovered.append(worker)
        return recovered
