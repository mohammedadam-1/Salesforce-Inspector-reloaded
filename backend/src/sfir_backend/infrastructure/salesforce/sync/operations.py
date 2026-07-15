"""RetryManager, SyncProgressTracker, SyncStatusManager, SyncRecovery."""

import uuid
from datetime import UTC, datetime

import structlog

from sfir_backend.domain.entities.metadata_sync import (
    SyncJob,
    SyncRetryQueueItem,
)
from sfir_backend.domain.repositories.sync_repos import (
    ISyncRetryQueueRepository,
)
from sfir_backend.domain.value_objects.metadata import SyncJobStatus

logger = structlog.get_logger(__name__)


class RetryManager:
    """Manages retry logic for failed metadata downloads."""

    def __init__(
        self,
        retry_repo: ISyncRetryQueueRepository,
        max_attempts: int = 3,
        base_delay_seconds: int = 60,
    ) -> None:
        self._retry_repo = retry_repo
        self._max_attempts = max_attempts
        self._base_delay = base_delay_seconds

    async def enqueue(
        self,
        organization_id: uuid.UUID,
        sync_job_id: uuid.UUID,
        component_type: str,
        component_name: str,
        error: str = "",
    ) -> SyncRetryQueueItem:
        item = SyncRetryQueueItem.create(
            organization_id=organization_id,
            sync_job_id=sync_job_id,
            component_type=component_type,
            component_name=component_name,
            error=error,
            max_attempts=self._max_attempts,
        )
        return await self._retry_repo.save(item)

    async def get_pending_items(
        self, organization_id: uuid.UUID, limit: int = 50,
    ) -> list[SyncRetryQueueItem]:
        return await self._retry_repo.list_pending_by_organization(
            organization_id, limit=limit,
        )

    async def process_retry(
        self, item: SyncRetryQueueItem,
    ) -> bool:
        item.mark_processing()
        await self._retry_repo.update(item)
        has_remaining = item.increment_attempt()
        await self._retry_repo.update(item)
        return has_remaining

    async def mark_completed(self, item: SyncRetryQueueItem) -> None:
        item.mark_completed()
        await self._retry_repo.update(item)

    async def mark_exhausted(self, item: SyncRetryQueueItem) -> None:
        item.mark_exhausted()
        await self._retry_repo.update(item)

    async def count_pending(self, organization_id: uuid.UUID) -> int:
        return await self._retry_repo.count_pending(organization_id)

    @staticmethod
    def compute_backoff(attempt: int, base_delay: int = 60) -> int:
        delay = base_delay * (2 ** (attempt - 1))
        return min(delay, 3600)


class SyncProgressTracker:
    """Tracks synchronization progress in real time."""

    def __init__(self, job: SyncJob, update_callback=None) -> None:
        self._job = job
        self._update_callback = update_callback

    async def start(self, total_items: int) -> None:
        self._job.total_items = total_items
        self._job.processed_items = 0
        self._job.failed_items = 0
        self._job.progress = 0.0
        await self._update_progress()

    async def increment_processed(self, count: int = 1) -> None:
        self._job.processed_items += count
        await self._update_progress()

    async def increment_failed(self, count: int = 1) -> None:
        self._job.failed_items += count
        await self._update_progress()

    async def set_processed(self, count: int) -> None:
        self._job.processed_items = count
        await self._update_progress()

    async def set_failed(self, count: int) -> None:
        self._job.failed_items = count
        await self._update_progress()

    async def _update_progress(self) -> None:
        total = self._job.total_items
        if total > 0:
            self._job.progress = min(
                (self._job.processed_items + self._job.failed_items) / total, 1.0,
            )
        self._job.updated_at = datetime.now(UTC)
        if self._update_callback:
            await self._update_callback(self._job)

    @property
    def progress_percentage(self) -> float:
        return round(self._job.progress * 100, 1)

    @property
    def is_complete(self) -> bool:
        return (
            self._job.processed_items + self._job.failed_items >= self._job.total_items
        )


class SyncStatusManager:
    """Manages sync job status transitions."""

    @staticmethod
    def can_transition(current: SyncJobStatus, target: SyncJobStatus) -> bool:
        valid_transitions: dict[SyncJobStatus, set[SyncJobStatus]] = {
            SyncJobStatus.PENDING: {
                SyncJobStatus.RUNNING, SyncJobStatus.CANCELLED, SyncJobStatus.FAILED,
            },
            SyncJobStatus.RUNNING: {
                SyncJobStatus.COMPLETED, SyncJobStatus.FAILED,
                SyncJobStatus.CANCELLED, SyncJobStatus.PAUSED,
            },
            SyncJobStatus.PAUSED: {
                SyncJobStatus.RUNNING, SyncJobStatus.CANCELLED, SyncJobStatus.FAILED,
            },
            SyncJobStatus.COMPLETED: set(),
            SyncJobStatus.FAILED: set(),
            SyncJobStatus.CANCELLED: set(),
        }
        return target in valid_transitions.get(current, set())

    @staticmethod
    def apply_transition(job: SyncJob, target: SyncJobStatus, error: str = "") -> bool:
        if not SyncStatusManager.can_transition(job.status, target):
            logger.warning(
                "invalid_sync_status_transition",
                current=job.status.value,
                target=target.value,
                job_id=str(job.id),
            )
            return False

        if target == SyncJobStatus.RUNNING:
            job.start()
        elif target == SyncJobStatus.COMPLETED:
            job.complete()
        elif target == SyncJobStatus.FAILED:
            job.fail(error)
        elif target == SyncJobStatus.CANCELLED:
            job.cancel()
        elif target == SyncJobStatus.PAUSED:
            job.status = SyncJobStatus.PAUSED
            job.updated_at = datetime.now(UTC)

        return True


class SyncRecovery:
    """Handles recovery from failed or interrupted syncs."""

    def __init__(
        self,
        retry_manager: RetryManager,
        progress_tracker: SyncProgressTracker | None = None,
    ) -> None:
        self._retry_manager = retry_manager
        self._progress_tracker = progress_tracker

    async def recover_failed_job(self, job: SyncJob) -> SyncJob:
        logger.info(
            "recovering_failed_sync_job",
            job_id=str(job.id),
            processed=job.processed_items,
            total=job.total_items,
        )
        job.status = SyncJobStatus.RUNNING
        job.error_message = ""
        job.updated_at = datetime.now(UTC)
        return job

    async def recover_interrupted_sync(
        self, job: SyncJob, retry_items: list[SyncRetryQueueItem],
    ) -> tuple[SyncJob, list[SyncRetryQueueItem]]:
        pending_retries = [
            item for item in retry_items
            if item.status.value in ("pending", "processing")
        ]
        logger.info(
            "recovering_interrupted_sync",
            job_id=str(job.id),
            pending_retries=len(pending_retries),
        )
        if pending_retries:
            job.status = SyncJobStatus.PAUSED
            job.updated_at = datetime.now(UTC)
        else:
            if job.failed_items == 0 and job.processed_items > 0:
                job.status = SyncJobStatus.COMPLETED
                job.progress = 1.0
            else:
                job.status = SyncJobStatus.PAUSED
            job.updated_at = datetime.now(UTC)

        return job, pending_retries

    async def can_resume(self, job: SyncJob) -> bool:
        return job.status in (
            SyncJobStatus.PAUSED, SyncJobStatus.FAILED,
        ) and job.total_items > 0
