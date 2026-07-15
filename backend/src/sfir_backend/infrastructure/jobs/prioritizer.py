from __future__ import annotations

from datetime import UTC, datetime

from sfir_backend.domain.jobs.models import Job, JobPriority


class JobPrioritizer:
    def __init__(self) -> None:
        self._priority_map: dict[str, JobPriority] = {}

    def set_priority(self, job: Job, priority: JobPriority) -> Job:
        old_priority = job.priority
        job.priority = priority
        if old_priority != priority:
            self._priority_map[job.id] = priority
        return job

    def escalate(self, job: Job) -> Job:
        priority_order = [
            JobPriority.LOW,
            JobPriority.MEDIUM,
            JobPriority.HIGH,
            JobPriority.CRITICAL,
        ]
        current_idx = priority_order.index(job.priority)
        if current_idx < len(priority_order) - 1:
            job.priority = priority_order[current_idx + 1]
            self._priority_map[job.id] = job.priority
        return job

    def deescalate(self, job: Job) -> Job:
        priority_order = [
            JobPriority.LOW,
            JobPriority.MEDIUM,
            JobPriority.HIGH,
            JobPriority.CRITICAL,
        ]
        current_idx = priority_order.index(job.priority)
        if current_idx > 0:
            job.priority = priority_order[current_idx - 1]
            self._priority_map[job.id] = job.priority
        return job

    def prioritize_for_tenant(
        self,
        jobs: list[Job],
        tenant_id: str,
        priority: JobPriority,
    ) -> list[Job]:
        result: list[Job] = []
        for job in jobs:
            if job.tenant_id == tenant_id:
                job.priority = priority
            result.append(job)
        return result

    def aging_factor(
        self,
        job: Job,
        max_age_hours: float = 24.0,
        max_boost: int = 2,
    ) -> int:
        age = (datetime.now(tz=UTC) - job.created_at).total_seconds() / 3600.0
        if age <= 0 or max_age_hours <= 0:
            return 0
        factor = min(age / max_age_hours, 1.0)
        return int(factor * max_boost)

    def get_effective_priority(
        self,
        job: Job,
        apply_aging: bool = True,
    ) -> int:
        base_map = {
            JobPriority.CRITICAL: 100,
            JobPriority.HIGH: 75,
            JobPriority.MEDIUM: 50,
            JobPriority.LOW: 25,
        }
        base = base_map.get(job.priority, 50)
        if apply_aging:
            base += self.aging_factor(job)
        return base
