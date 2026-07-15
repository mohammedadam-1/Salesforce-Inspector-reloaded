import uuid
from abc import ABC, abstractmethod

from sfir_backend.domain.entities.salesforce_connection import (
    SalesforceConnection,
)


class ISalesforceConnectionRepository(ABC):
    @abstractmethod
    async def get_by_id(self, connection_id: uuid.UUID) -> SalesforceConnection | None: ...

    @abstractmethod
    async def get_by_org_and_user(
        self, org_id: uuid.UUID, user_id: uuid.UUID,
    ) -> SalesforceConnection | None: ...

    @abstractmethod
    async def list_by_organization(self, org_id: uuid.UUID) -> list[SalesforceConnection]: ...

    @abstractmethod
    async def list_by_user(self, user_id: uuid.UUID) -> list[SalesforceConnection]: ...

    @abstractmethod
    async def list_active_by_organization(
        self, org_id: uuid.UUID,
    ) -> list[SalesforceConnection]: ...

    @abstractmethod
    async def save(self, connection: SalesforceConnection) -> SalesforceConnection: ...

    @abstractmethod
    async def update(self, connection: SalesforceConnection) -> SalesforceConnection: ...

    @abstractmethod
    async def delete(self, connection_id: uuid.UUID) -> None: ...
