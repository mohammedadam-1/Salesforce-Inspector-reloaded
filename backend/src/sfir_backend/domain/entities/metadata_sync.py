import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sfir_backend.domain.value_objects.metadata import (
    BatchStatus,
    MetadataAction,
    RetryStatus,
    SyncJobStatus,
    SyncType,
)


@dataclass
class SyncJob:
    id: uuid.UUID
    organization_id: uuid.UUID
    connection_id: uuid.UUID
    sync_type: SyncType
    status: SyncJobStatus = SyncJobStatus.PENDING
    metadata_type: str | None = None
    progress: float = 0.0
    total_items: int = 0
    processed_items: int = 0
    failed_items: int = 0
    error_message: str = ""
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @staticmethod
    def create(
        organization_id: uuid.UUID,
        connection_id: uuid.UUID,
        sync_type: SyncType,
        metadata_type: str | None = None,
    ) -> "SyncJob":
        return SyncJob(
            id=uuid.uuid4(),
            organization_id=organization_id,
            connection_id=connection_id,
            sync_type=sync_type,
            metadata_type=metadata_type,
        )

    def start(self) -> None:
        self.status = SyncJobStatus.RUNNING
        self.started_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

    def complete(self) -> None:
        self.status = SyncJobStatus.COMPLETED
        self.progress = 1.0
        self.completed_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

    def fail(self, error_message: str) -> None:
        self.status = SyncJobStatus.FAILED
        self.error_message = error_message
        self.completed_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

    def cancel(self) -> None:
        self.status = SyncJobStatus.CANCELLED
        self.completed_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

    def update_progress(
        self, processed: int, failed: int = 0, total: int | None = None,
    ) -> None:
        self.processed_items = processed
        self.failed_items = failed
        if total is not None:
            self.total_items = total
        if self.total_items > 0:
            self.progress = min(self.processed_items / self.total_items, 1.0)
        self.updated_at = datetime.now(UTC)


@dataclass
class MetadataVersion:
    id: uuid.UUID
    organization_id: uuid.UUID
    sync_job_id: uuid.UUID
    component_type: str
    component_name: str
    component_id: str | None
    hash: str
    version_number: int
    action: MetadataAction
    payload: dict | None = None
    salesforce_last_modified: datetime | None = None
    sync_timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    change_source: str = "manual"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @staticmethod
    def create(
        organization_id: uuid.UUID,
        sync_job_id: uuid.UUID,
        component_type: str,
        component_name: str,
        component_id: str | None,
        hash: str,
        version_number: int,
        action: MetadataAction,
        payload: dict | None = None,
        salesforce_last_modified: datetime | None = None,
        change_source: str = "sync",
    ) -> "MetadataVersion":
        return MetadataVersion(
            id=uuid.uuid4(),
            organization_id=organization_id,
            sync_job_id=sync_job_id,
            component_type=component_type,
            component_name=component_name,
            component_id=component_id,
            hash=hash,
            version_number=version_number,
            action=action,
            payload=payload,
            salesforce_last_modified=salesforce_last_modified,
            change_source=change_source,
        )


@dataclass
class SyncHistory:
    id: uuid.UUID
    organization_id: uuid.UUID
    connection_id: uuid.UUID
    sync_job_id: uuid.UUID | None
    sync_type: SyncType
    status: SyncJobStatus
    total_items: int = 0
    processed_items: int = 0
    failed_items: int = 0
    error_message: str = ""
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @staticmethod
    def from_job(job: SyncJob) -> "SyncHistory":
        return SyncHistory(
            id=uuid.uuid4(),
            organization_id=job.organization_id,
            connection_id=job.connection_id,
            sync_job_id=job.id,
            sync_type=job.sync_type,
            status=job.status,
            total_items=job.total_items,
            processed_items=job.processed_items,
            failed_items=job.failed_items,
            error_message=job.error_message,
            started_at=job.started_at or datetime.now(UTC),
            completed_at=job.completed_at,
        )


@dataclass
class SyncRetryQueueItem:
    id: uuid.UUID
    organization_id: uuid.UUID
    sync_job_id: uuid.UUID
    component_type: str
    component_name: str
    attempt_count: int = 0
    max_attempts: int = 3
    last_error: str = ""
    next_retry_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: RetryStatus = RetryStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @staticmethod
    def create(
        organization_id: uuid.UUID,
        sync_job_id: uuid.UUID,
        component_type: str,
        component_name: str,
        error: str = "",
        max_attempts: int = 3,
    ) -> "SyncRetryQueueItem":
        return SyncRetryQueueItem(
            id=uuid.uuid4(),
            organization_id=organization_id,
            sync_job_id=sync_job_id,
            component_type=component_type,
            component_name=component_name,
            last_error=error,
            max_attempts=max_attempts,
        )

    def mark_processing(self) -> None:
        self.status = RetryStatus.PROCESSING
        self.updated_at = datetime.now(UTC)

    def mark_completed(self) -> None:
        self.status = RetryStatus.COMPLETED
        self.updated_at = datetime.now(UTC)

    def mark_exhausted(self) -> None:
        self.status = RetryStatus.EXHAUSTED
        self.updated_at = datetime.now(UTC)

    def increment_attempt(self, error: str = "") -> bool:
        self.attempt_count += 1
        if error:
            self.last_error = error
        if self.attempt_count >= self.max_attempts:
            self.mark_exhausted()
            return False
        from datetime import timedelta
        delay = 60 * (2 ** (self.attempt_count - 1))
        self.next_retry_at = datetime.now(UTC) + timedelta(seconds=min(delay, 3600))
        self.updated_at = datetime.now(UTC)
        return True


@dataclass
class SyncStatistics:
    id: uuid.UUID
    organization_id: uuid.UUID
    connection_id: uuid.UUID
    total_syncs: int = 0
    successful_syncs: int = 0
    failed_syncs: int = 0
    total_components_synced: int = 0
    total_components_created: int = 0
    total_components_updated: int = 0
    total_components_deleted: int = 0
    last_sync_at: datetime | None = None
    last_successful_sync_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @staticmethod
    def create(
        organization_id: uuid.UUID, connection_id: uuid.UUID,
    ) -> "SyncStatistics":
        return SyncStatistics(
            id=uuid.uuid4(),
            organization_id=organization_id,
            connection_id=connection_id,
        )

    def record_sync(self, success: bool, components_processed: int = 0) -> None:
        self.total_syncs += 1
        if success:
            self.successful_syncs += 1
            self.last_successful_sync_at = datetime.now(UTC)
        else:
            self.failed_syncs += 1
        self.last_sync_at = datetime.now(UTC)
        self.total_components_synced += components_processed
        self.updated_at = datetime.now(UTC)

    def record_components(
        self, created: int = 0, updated: int = 0, deleted: int = 0,
    ) -> None:
        self.total_components_created += created
        self.total_components_updated += updated
        self.total_components_deleted += deleted
        self.updated_at = datetime.now(UTC)


@dataclass
class SyncCheckpoint:
    """Durable retrieval checkpoint for one batch of one metadata type.

    Checkpoints make metadata retrieval resumable after worker crashes,
    container restarts or deployment windows: a sync never restarts from
    batch 1, it resumes from the last successful checkpoint's cursor.
    """

    id: uuid.UUID
    sync_job_id: uuid.UUID
    organization_id: uuid.UUID
    metadata_type: str
    batch_id: int
    cursor: str | None
    status: BatchStatus
    retry_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @staticmethod
    def create(
        sync_job_id: uuid.UUID,
        organization_id: uuid.UUID,
        metadata_type: str,
        batch_id: int,
        cursor: str | None,
    ) -> "SyncCheckpoint":
        return SyncCheckpoint(
            id=uuid.uuid4(),
            sync_job_id=sync_job_id,
            organization_id=organization_id,
            metadata_type=metadata_type,
            batch_id=batch_id,
            cursor=cursor,
            status=BatchStatus.COMPLETED,
        )

    def mark_failed(self) -> None:
        self.status = BatchStatus.FAILED
        self.retry_count += 1
        self.updated_at = datetime.now(UTC)

    def mark_completed(self) -> None:
        self.status = BatchStatus.COMPLETED
        self.updated_at = datetime.now(UTC)
