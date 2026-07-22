import uuid
from abc import ABC, abstractmethod

from sfir_backend.domain.entities.organization import Organization


class IOrganizationRepository(ABC):
    @abstractmethod
    async def get_by_id(self, org_id: uuid.UUID) -> Organization | None: ...

    @abstractmethod
    async def get_by_slug(self, slug: str) -> Organization | None: ...

    @abstractmethod
    async def list_by_user(self, user_id: uuid.UUID) -> list[Organization]: ...

    @abstractmethod
    async def save(self, org: Organization) -> Organization: ...

    @abstractmethod
    async def update(self, org: Organization) -> Organization: ...

    @abstractmethod
    async def slug_exists(self, slug: str) -> bool: ...
