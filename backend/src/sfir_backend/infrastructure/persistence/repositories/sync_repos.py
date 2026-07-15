import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.domain.entities.metadata_sync import (
    MetadataVersion,
    SyncHistory,
    SyncJob,
    SyncRetryQueueItem,
    SyncStatistics,
)
from sfir_backend.domain.repositories.sync_repos import (
    IMetadataVersionRepository,
    ISyncHistoryRepository,
    ISyncJobRepository,
    ISyncRetryQueueRepository,
    ISyncStatisticsRepository,
)
from sfir_backend.domain.value_objects.metadata import (
    MetadataAction,
    RetryStatus,
    SyncJobStatus,
    SyncType,
)
from sfir_backend.infrastructure.persistence.models.metadata_sync import (
    MetadataVersionModel,
    SyncHistoryModel,
    SyncJobModel,
    SyncRetryQueueItemModel,
    SyncStatisticsModel,
)


class SyncJobRepository(ISyncJobRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, job_id: uuid.UUID) -> SyncJob | None:
        model = await self._session.get(SyncJobModel, job_id)
        return self._to_domain(model) if model else None

    async def list_by_organization(
        self, org_id: uuid.UUID, limit: int = 50, offset: int = 0,
    ) -> list[SyncJob]:
        result = await self._session.execute(
            select(SyncJobModel)
            .where(SyncJobModel.organization_id == org_id)
            .order_by(SyncJobModel.created_at.desc())
            .limit(limit)
            .offset(offset),
        )
        return [self._to_domain(m) for m in result.scalars().all()]

    async def list_active_by_organization(
        self, org_id: uuid.UUID,
    ) -> list[SyncJob]:
        result = await self._session.execute(
            select(SyncJobModel)
            .where(SyncJobModel.organization_id == org_id)
            .where(SyncJobModel.status.in_(["pending", "running", "paused"])),
        )
        return [self._to_domain(m) for m in result.scalars().all()]

    async def list_by_connection(
        self, connection_id: uuid.UUID, limit: int = 50, offset: int = 0,
    ) -> list[SyncJob]:
        result = await self._session.execute(
            select(SyncJobModel)
            .where(SyncJobModel.connection_id == connection_id)
            .order_by(SyncJobModel.created_at.desc())
            .limit(limit)
            .offset(offset),
        )
        return [self._to_domain(m) for m in result.scalars().all()]

    async def has_running_job(
        self, organization_id: uuid.UUID, connection_id: uuid.UUID,
    ) -> bool:
        result = await self._session.execute(
            select(func.count())
            .select_from(SyncJobModel)
            .where(SyncJobModel.organization_id == organization_id)
            .where(SyncJobModel.connection_id == connection_id)
            .where(SyncJobModel.status.in_(["pending", "running"])),
        )
        return result.scalar() > 0

    async def save(self, job: SyncJob) -> SyncJob:
        model = SyncJobModel(
            id=job.id,
            organization_id=job.organization_id,
            connection_id=job.connection_id,
            sync_type=job.sync_type.value,
            status=job.status.value,
            metadata_type=job.metadata_type,
            progress=job.progress,
            total_items=job.total_items,
            processed_items=job.processed_items,
            failed_items=job.failed_items,
            error_message=job.error_message,
            started_at=job.started_at,
            completed_at=job.completed_at,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
        self._session.add(model)
        await self._session.flush()
        return job

    async def update(self, job: SyncJob) -> SyncJob:
        model = await self._session.get(SyncJobModel, job.id)
        if not model:
            raise ValueError(f"SyncJob {job.id} not found")
        model.sync_type = job.sync_type.value
        model.status = job.status.value
        model.metadata_type = job.metadata_type
        model.progress = job.progress
        model.total_items = job.total_items
        model.processed_items = job.processed_items
        model.failed_items = job.failed_items
        model.error_message = job.error_message
        model.started_at = job.started_at
        model.completed_at = job.completed_at
        model.updated_at = job.updated_at
        await self._session.flush()
        return job

    def _to_domain(self, model: SyncJobModel) -> SyncJob:
        return SyncJob(
            id=model.id,
            organization_id=model.organization_id,
            connection_id=model.connection_id,
            sync_type=SyncType(model.sync_type),
            status=SyncJobStatus(model.status),
            metadata_type=model.metadata_type,
            progress=model.progress,
            total_items=model.total_items,
            processed_items=model.processed_items,
            failed_items=model.failed_items,
            error_message=model.error_message,
            started_at=model.started_at,
            completed_at=model.completed_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class MetadataVersionRepository(IMetadataVersionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, version_id: uuid.UUID) -> MetadataVersion | None:
        model = await self._session.get(MetadataVersionModel, version_id)
        return self._to_domain(model) if model else None

    async def get_latest_by_component(
        self, organization_id: uuid.UUID, component_type: str, component_name: str,
    ) -> MetadataVersion | None:
        result = await self._session.execute(
            select(MetadataVersionModel)
            .where(MetadataVersionModel.organization_id == organization_id)
            .where(MetadataVersionModel.component_type == component_type)
            .where(MetadataVersionModel.component_name == component_name)
            .order_by(MetadataVersionModel.version_number.desc())
            .limit(1),
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def list_by_sync_job(
        self, sync_job_id: uuid.UUID, limit: int = 1000, offset: int = 0,
    ) -> list[MetadataVersion]:
        result = await self._session.execute(
            select(MetadataVersionModel)
            .where(MetadataVersionModel.sync_job_id == sync_job_id)
            .order_by(MetadataVersionModel.component_type, MetadataVersionModel.component_name)
            .limit(limit)
            .offset(offset),
        )
        return [self._to_domain(m) for m in result.scalars().all()]

    async def list_by_organization(
        self, org_id: uuid.UUID, limit: int = 100, offset: int = 0,
    ) -> list[MetadataVersion]:
        result = await self._session.execute(
            select(MetadataVersionModel)
            .where(MetadataVersionModel.organization_id == org_id)
            .order_by(MetadataVersionModel.created_at.desc())
            .limit(limit)
            .offset(offset),
        )
        return [self._to_domain(m) for m in result.scalars().all()]

    async def count_by_organization(self, org_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(MetadataVersionModel)
            .where(MetadataVersionModel.organization_id == org_id),
        )
        return result.scalar() or 0

    async def save(self, version: MetadataVersion) -> MetadataVersion:
        model = MetadataVersionModel(
            id=version.id,
            organization_id=version.organization_id,
            sync_job_id=version.sync_job_id,
            component_type=version.component_type,
            component_name=version.component_name,
            component_id=version.component_id,
            hash=version.hash,
            version_number=version.version_number,
            action=version.action.value,
            payload=version.payload,
            salesforce_last_modified=version.salesforce_last_modified,
            sync_timestamp=version.sync_timestamp,
            change_source=version.change_source,
            created_at=version.created_at,
        )
        self._session.add(model)
        await self._session.flush()
        return version

    async def save_many(self, versions: list[MetadataVersion]) -> list[MetadataVersion]:
        for v in versions:
            await self.save(v)
        return versions

    def _to_domain(self, model: MetadataVersionModel) -> MetadataVersion:
        return MetadataVersion(
            id=model.id,
            organization_id=model.organization_id,
            sync_job_id=model.sync_job_id,
            component_type=model.component_type,
            component_name=model.component_name,
            component_id=model.component_id,
            hash=model.hash,
            version_number=model.version_number,
            action=MetadataAction(model.action),
            payload=model.payload,
            salesforce_last_modified=model.salesforce_last_modified,
            sync_timestamp=model.sync_timestamp,
            change_source=model.change_source,
            created_at=model.created_at,
        )


class SyncHistoryRepository(ISyncHistoryRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, history_id: uuid.UUID) -> SyncHistory | None:
        model = await self._session.get(SyncHistoryModel, history_id)
        return self._to_domain(model) if model else None

    async def list_by_organization(
        self, org_id: uuid.UUID, limit: int = 50, offset: int = 0,
    ) -> list[SyncHistory]:
        result = await self._session.execute(
            select(SyncHistoryModel)
            .where(SyncHistoryModel.organization_id == org_id)
            .order_by(SyncHistoryModel.created_at.desc())
            .limit(limit)
            .offset(offset),
        )
        return [self._to_domain(m) for m in result.scalars().all()]

    async def list_by_connection(
        self, connection_id: uuid.UUID, limit: int = 50, offset: int = 0,
    ) -> list[SyncHistory]:
        result = await self._session.execute(
            select(SyncHistoryModel)
            .where(SyncHistoryModel.connection_id == connection_id)
            .order_by(SyncHistoryModel.created_at.desc())
            .limit(limit)
            .offset(offset),
        )
        return [self._to_domain(m) for m in result.scalars().all()]

    async def save(self, history: SyncHistory) -> SyncHistory:
        model = SyncHistoryModel(
            id=history.id,
            organization_id=history.organization_id,
            connection_id=history.connection_id,
            sync_job_id=history.sync_job_id,
            sync_type=history.sync_type.value,
            status=history.status.value,
            total_items=history.total_items,
            processed_items=history.processed_items,
            failed_items=history.failed_items,
            error_message=history.error_message,
            started_at=history.started_at,
            completed_at=history.completed_at,
            created_at=history.created_at,
        )
        self._session.add(model)
        await self._session.flush()
        return history

    def _to_domain(self, model: SyncHistoryModel) -> SyncHistory:
        return SyncHistory(
            id=model.id,
            organization_id=model.organization_id,
            connection_id=model.connection_id,
            sync_job_id=model.sync_job_id,
            sync_type=SyncType(model.sync_type),
            status=SyncJobStatus(model.status),
            total_items=model.total_items,
            processed_items=model.processed_items,
            failed_items=model.failed_items,
            error_message=model.error_message,
            started_at=model.started_at,
            completed_at=model.completed_at,
            created_at=model.created_at,
        )


class SyncRetryQueueRepository(ISyncRetryQueueRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, item_id: uuid.UUID) -> SyncRetryQueueItem | None:
        model = await self._session.get(SyncRetryQueueItemModel, item_id)
        return self._to_domain(model) if model else None

    async def list_pending_by_organization(
        self, org_id: uuid.UUID, limit: int = 50,
    ) -> list[SyncRetryQueueItem]:
        result = await self._session.execute(
            select(SyncRetryQueueItemModel)
            .where(SyncRetryQueueItemModel.organization_id == org_id)
            .where(SyncRetryQueueItemModel.status == "pending")
            .where(SyncRetryQueueItemModel.next_retry_at <= datetime.now())
            .order_by(SyncRetryQueueItemModel.next_retry_at.asc())
            .limit(limit),
        )
        return [self._to_domain(m) for m in result.scalars().all()]

    async def list_by_sync_job(
        self, sync_job_id: uuid.UUID,
    ) -> list[SyncRetryQueueItem]:
        result = await self._session.execute(
            select(SyncRetryQueueItemModel)
            .where(SyncRetryQueueItemModel.sync_job_id == sync_job_id),
        )
        return [self._to_domain(m) for m in result.scalars().all()]

    async def count_pending(self, org_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(SyncRetryQueueItemModel)
            .where(SyncRetryQueueItemModel.organization_id == org_id)
            .where(SyncRetryQueueItemModel.status == "pending"),
        )
        return result.scalar() or 0

    async def save(self, item: SyncRetryQueueItem) -> SyncRetryQueueItem:
        model = SyncRetryQueueItemModel(
            id=item.id,
            organization_id=item.organization_id,
            sync_job_id=item.sync_job_id,
            component_type=item.component_type,
            component_name=item.component_name,
            attempt_count=item.attempt_count,
            max_attempts=item.max_attempts,
            last_error=item.last_error,
            next_retry_at=item.next_retry_at,
            status=item.status.value,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        self._session.add(model)
        await self._session.flush()
        return item

    async def update(self, item: SyncRetryQueueItem) -> SyncRetryQueueItem:
        model = await self._session.get(SyncRetryQueueItemModel, item.id)
        if not model:
            raise ValueError(f"SyncRetryQueueItem {item.id} not found")
        model.attempt_count = item.attempt_count
        model.max_attempts = item.max_attempts
        model.last_error = item.last_error
        model.next_retry_at = item.next_retry_at
        model.status = item.status.value
        model.updated_at = item.updated_at
        await self._session.flush()
        return item

    def _to_domain(self, model: SyncRetryQueueItemModel) -> SyncRetryQueueItem:
        return SyncRetryQueueItem(
            id=model.id,
            organization_id=model.organization_id,
            sync_job_id=model.sync_job_id,
            component_type=model.component_type,
            component_name=model.component_name,
            attempt_count=model.attempt_count,
            max_attempts=model.max_attempts,
            last_error=model.last_error,
            next_retry_at=model.next_retry_at,
            status=RetryStatus(model.status),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class SyncStatisticsRepository(ISyncStatisticsRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_connection(
        self, organization_id: uuid.UUID, connection_id: uuid.UUID,
    ) -> SyncStatistics | None:
        result = await self._session.execute(
            select(SyncStatisticsModel)
            .where(SyncStatisticsModel.organization_id == organization_id)
            .where(SyncStatisticsModel.connection_id == connection_id),
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def save(self, stats: SyncStatistics) -> SyncStatistics:
        model = SyncStatisticsModel(
            id=stats.id,
            organization_id=stats.organization_id,
            connection_id=stats.connection_id,
            total_syncs=stats.total_syncs,
            successful_syncs=stats.successful_syncs,
            failed_syncs=stats.failed_syncs,
            total_components_synced=stats.total_components_synced,
            total_components_created=stats.total_components_created,
            total_components_updated=stats.total_components_updated,
            total_components_deleted=stats.total_components_deleted,
            last_sync_at=stats.last_sync_at,
            last_successful_sync_at=stats.last_successful_sync_at,
            created_at=stats.created_at,
            updated_at=stats.updated_at,
        )
        self._session.add(model)
        await self._session.flush()
        return stats

    async def update(self, stats: SyncStatistics) -> SyncStatistics:
        model = await self._session.get(SyncStatisticsModel, stats.id)
        if not model:
            raise ValueError(f"SyncStatistics {stats.id} not found")
        model.total_syncs = stats.total_syncs
        model.successful_syncs = stats.successful_syncs
        model.failed_syncs = stats.failed_syncs
        model.total_components_synced = stats.total_components_synced
        model.total_components_created = stats.total_components_created
        model.total_components_updated = stats.total_components_updated
        model.total_components_deleted = stats.total_components_deleted
        model.last_sync_at = stats.last_sync_at
        model.last_successful_sync_at = stats.last_successful_sync_at
        model.updated_at = stats.updated_at
        await self._session.flush()
        return stats

    def _to_domain(self, model: SyncStatisticsModel) -> SyncStatistics:
        return SyncStatistics(
            id=model.id,
            organization_id=model.organization_id,
            connection_id=model.connection_id,
            total_syncs=model.total_syncs,
            successful_syncs=model.successful_syncs,
            failed_syncs=model.failed_syncs,
            total_components_synced=model.total_components_synced,
            total_components_created=model.total_components_created,
            total_components_updated=model.total_components_updated,
            total_components_deleted=model.total_components_deleted,
            last_sync_at=model.last_sync_at,
            last_successful_sync_at=model.last_successful_sync_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
