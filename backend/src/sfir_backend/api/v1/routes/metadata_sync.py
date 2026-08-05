import uuid

from fastapi import APIRouter, Depends, Query

from sfir_backend.api.deps import (
    get_current_org_id,
    get_current_user_id,
    get_sync_coordinator,
)
from sfir_backend.application.dto.metadata_sync import (
    RetryQueueItemResponse,
    StartSyncRequest,
    SyncHistoryResponse,
    SyncJobResponse,
    SyncStatisticsResponse,
)
from sfir_backend.application.use_cases.metadata_sync import SyncCoordinator
from sfir_backend.workers.tasks.metadata_sync import (
    full_sync as full_sync_task,
)
from sfir_backend.workers.tasks.metadata_sync import (
    incremental_sync as incremental_sync_task,
)
from sfir_backend.workers.tasks.metadata_sync import (
    resume_sync as resume_sync_task,
)

router = APIRouter(prefix="/sync", tags=["Metadata Sync"])

_FULL_SYNC_TYPES = {"full", "force", "manual"}


@router.post("/start")
async def start_sync(
    request: StartSyncRequest,
    org_id: str = Depends(get_current_org_id),
    user_id: str = Depends(get_current_user_id),
    coordinator: SyncCoordinator = Depends(get_sync_coordinator),
) -> SyncJobResponse:
    response = await coordinator.start_sync(request, org_id, user_id)
    task = (
        full_sync_task
        if request.sync_type in _FULL_SYNC_TYPES
        else incremental_sync_task
    )
    task.apply_async(
        args=[str(org_id), str(request.connection_id)],
        queue="metadata",
    )
    return response


@router.get("/jobs")
async def list_sync_jobs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    org_id: str = Depends(get_current_org_id),
    coordinator: SyncCoordinator = Depends(get_sync_coordinator),
) -> list[SyncJobResponse]:
    return await coordinator.list_sync_jobs(org_id, limit=limit, offset=offset)


@router.get("/jobs/{job_id}")
async def get_sync_job(
    job_id: str,
    org_id: str = Depends(get_current_org_id),
    coordinator: SyncCoordinator = Depends(get_sync_coordinator),
) -> SyncJobResponse | None:
    return await coordinator.get_sync_job(uuid.UUID(job_id), org_id)


@router.post("/jobs/{job_id}/cancel")
async def cancel_sync(
    job_id: str,
    org_id: str = Depends(get_current_org_id),
    coordinator: SyncCoordinator = Depends(get_sync_coordinator),
) -> SyncJobResponse:
    return await coordinator.cancel_sync(uuid.UUID(job_id), org_id)


@router.post("/jobs/{job_id}/pause")
async def pause_sync(
    job_id: str,
    org_id: str = Depends(get_current_org_id),
    coordinator: SyncCoordinator = Depends(get_sync_coordinator),
) -> SyncJobResponse:
    return await coordinator.pause_sync(uuid.UUID(job_id), org_id)


@router.post("/jobs/{job_id}/resume")
async def resume_sync(
    job_id: str,
    org_id: str = Depends(get_current_org_id),
    coordinator: SyncCoordinator = Depends(get_sync_coordinator),
) -> SyncJobResponse:
    response = await coordinator.resume_sync(uuid.UUID(job_id), org_id)
    resume_sync_task.apply_async(
        args=[org_id, str(response.id)],
        queue="metadata",
    )
    return response


@router.get("/history")
async def get_sync_history(
    connection_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    org_id: str = Depends(get_current_org_id),
    coordinator: SyncCoordinator = Depends(get_sync_coordinator),
) -> list[SyncHistoryResponse]:
    conn_uuid = uuid.UUID(connection_id) if connection_id else None
    return await coordinator.get_sync_history(org_id, conn_uuid, limit=limit, offset=offset)


@router.get("/statistics")
async def get_sync_statistics(
    connection_id: str,
    org_id: str = Depends(get_current_org_id),
    coordinator: SyncCoordinator = Depends(get_sync_coordinator),
) -> SyncStatisticsResponse:
    return await coordinator.get_sync_statistics(org_id, uuid.UUID(connection_id))


@router.get("/retry-queue")
async def get_retry_queue(
    limit: int = Query(50, ge=1, le=200),
    org_id: str = Depends(get_current_org_id),
    coordinator: SyncCoordinator = Depends(get_sync_coordinator),
) -> list[RetryQueueItemResponse]:
    return await coordinator.get_retry_queue(org_id, limit=limit)
