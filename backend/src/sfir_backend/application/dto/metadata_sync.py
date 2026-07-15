import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass
class StartSyncRequest:
    connection_id: uuid.UUID
    sync_type: str = "full"
    metadata_type: str | None = None


@dataclass
class SyncJobResponse:
    id: uuid.UUID
    organization_id: uuid.UUID
    connection_id: uuid.UUID
    sync_type: str
    status: str
    metadata_type: str | None
    progress: float
    total_items: int
    processed_items: int
    failed_items: int
    error_message: str
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass
class SyncHistoryResponse:
    id: uuid.UUID
    organization_id: uuid.UUID
    connection_id: uuid.UUID
    sync_type: str
    status: str
    total_items: int
    processed_items: int
    failed_items: int
    error_message: str
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime


@dataclass
class SyncStatisticsResponse:
    id: uuid.UUID
    organization_id: uuid.UUID
    connection_id: uuid.UUID
    total_syncs: int
    successful_syncs: int
    failed_syncs: int
    total_components_synced: int
    total_components_created: int
    total_components_updated: int
    total_components_deleted: int
    last_sync_at: datetime | None
    last_successful_sync_at: datetime | None


@dataclass
class MetadataVersionResponse:
    id: uuid.UUID
    component_type: str
    component_name: str
    component_id: str | None
    hash: str
    version_number: int
    action: str
    salesforce_last_modified: datetime | None
    sync_timestamp: datetime
    created_at: datetime


@dataclass
class RetryQueueItemResponse:
    id: uuid.UUID
    component_type: str
    component_name: str
    attempt_count: int
    max_attempts: int
    last_error: str
    next_retry_at: datetime
    status: str
