from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from sfir_backend.api.deps import (
    get_current_org_id,
    get_job_engine,
)
from sfir_backend.application.dto.jobs import (
    JobMetricsResponse,
    JobResponse,
    WorkerResponse,
)
from sfir_backend.infrastructure.jobs.engine import JobEngine

router = APIRouter(prefix="/jobs", tags=["Jobs"])


def _job_to_response(job: Any) -> JobResponse:
    return JobResponse(
        id=job.id,
        type=job.type.value if hasattr(job.type, "value") else str(job.type),
        status=job.status.value if hasattr(job.status, "value") else str(job.status),
        priority=job.priority.value if hasattr(job.priority, "value") else str(job.priority),
        queue=job.queue.value if hasattr(job.queue, "value") else str(job.queue),
        tenant_id=job.tenant_id,
        progress_percentage=job.progress.percentage,
        current_step=job.progress.current_step,
        elapsed_seconds=job.progress.elapsed_seconds,
        remaining_seconds=job.progress.remaining_seconds,
        attempt=job.retry.attempt,
        max_retries=job.retry.max_retries,
        last_error=job.retry.last_error,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        warnings=job.progress.warnings,
        errors=job.progress.errors,
    )


def _worker_to_response(worker: Any) -> WorkerResponse:
    return WorkerResponse(
        id=worker.id,
        name=worker.name,
        status=worker.status.value if hasattr(worker.status, "value") else str(worker.status),
        current_job_id=worker.current_job_id,
        supported_job_types=[
            t.value if hasattr(t, "value") else str(t)
            for t in worker.supported_job_types
        ],
        last_heartbeat=worker.last_heartbeat,
        registered_at=worker.registered_at,
    )


@router.get("")
async def list_jobs(
    _status: str | None = Query(None),
    _job_type: str | None = Query(None),
    tenant_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    org_id: str | None = Depends(get_current_org_id),
    engine: JobEngine = Depends(get_job_engine),
) -> list[JobResponse]:
    all_jobs = engine.list_jobs(
        tenant_id=tenant_id or org_id,
    )
    all_jobs.sort(key=lambda j: j.created_at, reverse=True)
    sliced = all_jobs[offset: offset + limit]
    return [_job_to_response(j) for j in sliced]


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    engine: JobEngine = Depends(get_job_engine),
) -> JobResponse | None:
    job = engine.get_job(job_id)
    if not job:
        return None
    return _job_to_response(job)


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    engine: JobEngine = Depends(get_job_engine),
) -> dict[str, Any]:
    success = engine.cancel_job(job_id)
    return {"success": success, "job_id": job_id}


@router.post("/{job_id}/retry")
async def retry_job(
    job_id: str,
    engine: JobEngine = Depends(get_job_engine),
) -> dict[str, Any]:
    success = engine.retry_job(job_id)
    return {"success": success, "job_id": job_id}


@router.get("/{job_id}/progress")
async def get_job_progress(
    job_id: str,
    engine: JobEngine = Depends(get_job_engine),
) -> dict[str, Any] | None:
    return engine.get_job_progress(job_id)


@router.get("/metrics")
async def get_job_metrics(
    engine: JobEngine = Depends(get_job_engine),
) -> JobMetricsResponse:
    snapshot = engine.snapshot_metrics()
    return JobMetricsResponse(
        total_jobs=snapshot.total_jobs,
        jobs_by_status=snapshot.jobs_by_status,
        jobs_by_type=snapshot.jobs_by_type,
        total_workers=snapshot.total_workers,
        workers_by_status=snapshot.workers_by_status,
        queue_depths=snapshot.queue_depths,
        avg_queue_wait_ms=snapshot.avg_queue_wait_ms,
        avg_execution_time_ms=snapshot.avg_execution_time_ms,
        retry_count=snapshot.retry_count,
        dead_letter_count=snapshot.dead_letter_count,
        throughput_per_minute=snapshot.throughput_per_minute,
    )


@router.get("/workers")
async def list_workers(
    status: str | None = Query(None),
    engine: JobEngine = Depends(get_job_engine),
) -> list[WorkerResponse]:
    from sfir_backend.domain.jobs.models import WorkerStatus
    worker_status = WorkerStatus(status) if status else None
    workers = engine.list_workers(worker_status)
    return [_worker_to_response(w) for w in workers]
