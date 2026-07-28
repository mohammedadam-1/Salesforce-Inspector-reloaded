from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from sfir_backend.domain.jobs.models import Job, JobProgress, JobStatus


class ProgressTracker:
    def __init__(self) -> None:
        self._start_times: dict[str, float] = {}

    def start_job(self, job: Job) -> Job:
        now = datetime.now(tz=UTC)
        job.progress.started_at = now
        job.progress.updated_at = now
        job.progress.elapsed_seconds = 0.0
        job.status = JobStatus.RUNNING
        self._start_times[job.id] = time.monotonic()
        return job

    def update_progress(
        self,
        job: Job,
        percentage: float | None = None,
        current_step: str | None = None,
        completed_steps: int | None = None,
        total_steps: int | None = None,
        warning: str | None = None,
        error: str | None = None,
    ) -> Job:
        now = datetime.now(tz=UTC)
        start = self._start_times.get(job.id)
        elapsed = time.monotonic() - start if start else 0.0

        progress = job.progress
        if percentage is not None:
            progress.percentage = min(max(percentage, 0.0), 100.0)
        if current_step is not None:
            progress.current_step = current_step
        if completed_steps is not None:
            progress.completed_steps = completed_steps
        if total_steps is not None:
            progress.total_steps = total_steps
        if warning:
            progress.warnings.append(warning)
        if error:
            progress.errors.append(error)

        progress.elapsed_seconds = elapsed
        if progress.percentage > 0:
            estimated_total = elapsed / (progress.percentage / 100.0)
            progress.remaining_seconds = max(0.0, estimated_total - elapsed)
            progress.estimated_completion = now + timedelta(
                seconds=progress.remaining_seconds
            )

        progress.updated_at = now
        job.progress = progress
        return job

    def complete_job(self, job: Job, result: dict | None = None) -> Job:
        now = datetime.now(tz=UTC)
        start = self._start_times.get(job.id)
        elapsed = time.monotonic() - start if start else 0.0

        job.progress.percentage = 100.0
        job.progress.elapsed_seconds = elapsed
        job.progress.remaining_seconds = 0.0
        job.progress.updated_at = now
        job.progress.estimated_completion = now

        job.status = JobStatus.COMPLETED
        job.completed_at = now
        job.result = result
        self._start_times.pop(job.id, None)
        return job

    def fail_job(self, job: Job, error: str) -> Job:
        now = datetime.now(tz=UTC)
        start = self._start_times.get(job.id)
        elapsed = time.monotonic() - start if start else 0.0

        job.progress.elapsed_seconds = elapsed
        job.progress.errors.append(error)
        job.progress.updated_at = now
        job.completed_at = now
        job.status = JobStatus.FAILED
        self._start_times.pop(job.id, None)
        return job

    def get_progress(self, job: Job) -> JobProgress:
        start = self._start_times.get(job.id)
        if start:
            elapsed = time.monotonic() - start
            progress = job.progress
            progress.elapsed_seconds = elapsed
            if progress.percentage > 0:
                estimated_total = elapsed / (progress.percentage / 100.0)
                progress.remaining_seconds = max(0.0, estimated_total - elapsed)
                progress.estimated_completion = datetime.now(tz=UTC) + timedelta(
                    seconds=progress.remaining_seconds
                )
            progress.updated_at = datetime.now(tz=UTC)
            job.progress = progress
        return job.progress
