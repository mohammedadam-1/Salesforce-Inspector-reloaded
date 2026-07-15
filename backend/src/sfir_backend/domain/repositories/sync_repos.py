import uuid
from abc import ABC, abstractmethod

from sfir_backend.domain.entities.metadata_sync import (
    MetadataVersion,
    SyncHistory,
    SyncJob,
    SyncRetryQueueItem,
    SyncStatistics,
)


class ISyncJobRepository(ABC):
    @abstractmethod
    async def get_by_id(self, job_id: uuid.UUID) -> SyncJob | None: ...

    @abstractmethod
    async def list_by_organization(
        self, org_id: uuid.UUID, limit: int = 50, offset: int = 0,
    ) -> list[SyncJob]: ...

    @abstractmethod
    async def list_active_by_organization(
        self, org_id: uuid.UUID,
    ) -> list[SyncJob]: ...

    @abstractmethod
    async def list_by_connection(
        self, connection_id: uuid.UUID, limit: int = 50, offset: int = 0,
    ) -> list[SyncJob]: ...

    @abstractmethod
    async def has_running_job(
        self, organization_id: uuid.UUID, connection_id: uuid.UUID,
    ) -> bool: ...

    @abstractmethod
    async def save(self, job: SyncJob) -> SyncJob: ...

    @abstractmethod
    async def update(self, job: SyncJob) -> SyncJob: ...


class IMetadataVersionRepository(ABC):
    @abstractmethod
    async def get_by_id(self, version_id: uuid.UUID) -> MetadataVersion | None: ...

    @abstractmethod
    async def get_latest_by_component(
        self, organization_id: uuid.UUID, component_type: str, component_name: str,
    ) -> MetadataVersion | None: ...

    @abstractmethod
    async def list_by_sync_job(
        self, sync_job_id: uuid.UUID, limit: int = 1000, offset: int = 0,
    ) -> list[MetadataVersion]: ...

    @abstractmethod
    async def list_by_organization(
        self, org_id: uuid.UUID, limit: int = 100, offset: int = 0,
    ) -> list[MetadataVersion]: ...

    @abstractmethod
    async def count_by_organization(self, org_id: uuid.UUID) -> int: ...

    @abstractmethod
    async def save(self, version: MetadataVersion) -> MetadataVersion: ...

    @abstractmethod
    async def save_many(self, versions: list[MetadataVersion]) -> list[MetadataVersion]: ...


class ISyncHistoryRepository(ABC):
    @abstractmethod
    async def get_by_id(self, history_id: uuid.UUID) -> SyncHistory | None: ...

    @abstractmethod
    async def list_by_organization(
        self, org_id: uuid.UUID, limit: int = 50, offset: int = 0,
    ) -> list[SyncHistory]: ...

    @abstractmethod
    async def list_by_connection(
        self, connection_id: uuid.UUID, limit: int = 50, offset: int = 0,
    ) -> list[SyncHistory]: ...

    @abstractmethod
    async def save(self, history: SyncHistory) -> SyncHistory: ...


class ISyncRetryQueueRepository(ABC):
    @abstractmethod
    async def get_by_id(self, item_id: uuid.UUID) -> SyncRetryQueueItem | None: ...

    @abstractmethod
    async def list_pending_by_organization(
        self, org_id: uuid.UUID, limit: int = 50,
    ) -> list[SyncRetryQueueItem]: ...

    @abstractmethod
    async def list_by_sync_job(
        self, sync_job_id: uuid.UUID,
    ) -> list[SyncRetryQueueItem]: ...

    @abstractmethod
    async def count_pending(self, org_id: uuid.UUID) -> int: ...

    @abstractmethod
    async def save(self, item: SyncRetryQueueItem) -> SyncRetryQueueItem: ...

    @abstractmethod
    async def update(self, item: SyncRetryQueueItem) -> SyncRetryQueueItem: ...


class ISyncStatisticsRepository(ABC):
    @abstractmethod
    async def get_by_connection(
        self, organization_id: uuid.UUID, connection_id: uuid.UUID,
    ) -> SyncStatistics | None: ...

    @abstractmethod
    async def save(self, stats: SyncStatistics) -> SyncStatistics: ...

    @abstractmethod
    async def update(self, stats: SyncStatistics) -> SyncStatistics: ...
