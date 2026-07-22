import uuid
from abc import ABC, abstractmethod
from datetime import datetime

from sfir_backend.domain.entities.audit_log import AuditLogEntry


class IAuditLogRepository(ABC):
    @abstractmethod
    async def save(self, entry: AuditLogEntry) -> AuditLogEntry: ...

    @abstractmethod
    async def list_by_org(
        self,
        org_id: uuid.UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLogEntry]: ...

    @abstractmethod
    async def list_by_user(
        self,
        user_id: uuid.UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLogEntry]: ...

    @abstractmethod
    async def count_by_org(
        self,
        org_id: uuid.UUID,
        since: datetime | None = None,
    ) -> int: ...
