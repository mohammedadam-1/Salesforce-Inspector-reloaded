"""Celery tasks for metadata synchronization.

These tasks connect to the metadata sync service to perform
the actual synchronization in the background.
"""

import uuid

import structlog
from celery import Task
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.infrastructure.database.session import AsyncSessionFactory
from sfir_backend.infrastructure.queue.celery_app import celery_app
from sfir_backend.services.metadata.sync_service import MetadataSyncService

logger = structlog.get_logger(__name__)


class DatabaseTask(Task):
    _session: AsyncSession | None = None

    async def get_session(self) -> AsyncSession:
        if self._session is None:
            self._session = await AsyncSessionFactory().__anext__()
        return self._session

    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        if self._session is not None:
            import asyncio
            asyncio.run(self._session.aclose())
            self._session = None


@celery_app.task(
    bind=True,
    base=DatabaseTask,
    name="metadata_sync.full_sync",
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
    track_started=True,
    queue="metadata",
)
def full_metadata_sync(self, organization_id: str, requested_by_user_id: str | None = None) -> dict:
    """Perform a full metadata synchronization for an organization."""
    import asyncio

    async def _run():
        session = await self.get_session()
        service = MetadataSyncService(session)
        sync_run = await service.sync_organization(
            organization_id=uuid.UUID(organization_id),
            requested_by_user_id=uuid.UUID(requested_by_user_id) if requested_by_user_id else None,
        )
        return {
            "sync_run_id": str(sync_run.id),
            "status": sync_run.status,
            "stats": sync_run.stats,
        }

    try:
        result = asyncio.run(_run())
        logger.info("full_metadata_sync_completed", result=result)
        return result
    except Exception as exc:
        logger.error("full_metadata_sync_failed", error=str(exc))
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    base=DatabaseTask,
    name="metadata_sync.incremental_sync",
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
    track_started=True,
    queue="metadata",
)
def incremental_metadata_sync(self, organization_id: str) -> dict:
    """Perform an incremental metadata sync.

    Uses Tooling API getUpdated/getDeleted to sync only changes.
    """
    import asyncio

    async def _run():
        session = await self.get_session()
        service = MetadataSyncService(session)
        sync_run = await service.sync_organization(
            organization_id=uuid.UUID(organization_id),
            sync_type="incremental",
        )
        return {"sync_run_id": str(sync_run.id), "status": sync_run.status}

    try:
        result = asyncio.run(_run())
        return result
    except Exception as exc:
        logger.error("incremental_sync_failed", error=str(exc))
        raise self.retry(exc=exc)
