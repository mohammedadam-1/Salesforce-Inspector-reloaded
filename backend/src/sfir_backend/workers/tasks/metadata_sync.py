"""Celery tasks for metadata synchronization.

These tasks are dispatched by the Celery Beat scheduler
and delegate to the SyncCoordinator for actual execution.
"""

import asyncio
import uuid

import structlog

from sfir_backend.workers.celery import celery_app

logger = structlog.get_logger(__name__)


async def _execute_sync(
    organization_id: str, connection_id: str, sync_type: str,
) -> dict:
    from sfir_backend.application.dto.metadata_sync import StartSyncRequest
    from sfir_backend.config.container import Container
    from sfir_backend.config.settings import get_settings
    from sfir_backend.domain.value_objects.metadata import SyncType

    container = Container(get_settings())
    await container.startup()
    try:
        coordinator = container.get_use_case("sync_coordinator")
        request = StartSyncRequest(
            connection_id=uuid.UUID(connection_id),
            sync_type=sync_type,
        )
        response = await coordinator.start_sync(
            request, uuid.UUID(organization_id),
        )
        job = await coordinator.get_sync_job(
            uuid.UUID(response.id), uuid.UUID(organization_id),
        )
        if job:
            from sfir_backend.domain.entities.metadata_sync import SyncJob
            sync_job = SyncJob(
                id=uuid.UUID(job.id),
                organization_id=uuid.UUID(organization_id),
                connection_id=uuid.UUID(connection_id),
                sync_type=SyncType(sync_type),
            )
            await coordinator.execute_sync(sync_job)
        return {"job_id": str(response.id), "sync_type": sync_type}
    finally:
        await container.shutdown()


def run_async(coro) -> dict:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    name="metadata.incremental_sync",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    acks_late=True,
)
def incremental_sync(self, organization_id: str, connection_id: str) -> dict:
    try:
        return run_async(_execute_sync(organization_id, connection_id, "incremental"))
    except Exception as exc:
        logger.error("incremental_sync_failed", error=str(exc))
        raise self.retry(exc=exc) from None


@celery_app.task(
    name="metadata.full_sync",
    bind=True,
    max_retries=2,
    default_retry_delay=600,
    acks_late=True,
)
def full_sync(self, organization_id: str, connection_id: str) -> dict:
    try:
        return run_async(_execute_sync(organization_id, connection_id, "full"))
    except Exception as exc:
        logger.error("full_sync_failed", error=str(exc))
        raise self.retry(exc=exc) from None


@celery_app.task(
    name="metadata.detect_stale",
    bind=True,
    max_retries=1,
    acks_late=True,
)
def detect_stale_syncs(_self, organization_id: str) -> list[dict]:
    import asyncio

    async def _run():
        from datetime import UTC, datetime, timedelta

        from sfir_backend.config.container import Container
        from sfir_backend.config.settings import get_settings
        from sfir_backend.domain.entities.metadata_sync import SyncHistory

        container = Container(get_settings())
        await container.startup()
        try:
            sync_job_repo = container.get_repository("sync_job")
            history_repo = container.get_repository("sync_history")
            cutoff = datetime.now(UTC) - timedelta(hours=2)
            results: list[dict] = []
            org_id = uuid.UUID(organization_id)
            active_jobs = await sync_job_repo.list_active_by_organization(org_id)
            for job in active_jobs:
                if job.started_at and job.started_at < cutoff:
                    job.fail("Stale job auto-failed after 2 hours")
                    await sync_job_repo.update(job)
                    history = SyncHistory.from_job(job)
                    await history_repo.save(history)
                    results.append({
                        "job_id": str(job.id),
                        "old_status": job.status.value,
                    })
            return results
        finally:
            await container.shutdown()

    try:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(_run())
        loop.close()
        return result
    except Exception as exc:
        logger.error("stale_detection_failed", error=str(exc))
        return []
