import uuid
from abc import ABC, abstractmethod

from sfir_backend.domain.entities.role import Role


class IRoleRepository(ABC):
    @abstractmethod
    async def get_by_id(self, role_id: uuid.UUID) -> Role | None: ...

    @abstractmethod
    async def get_by_slug(self, slug: str) -> Role | None: ...

    @abstractmethod
    async def list_system_roles(self) -> list[Role]: ...

    @abstractmethod
    async def list_by_org(self, org_id: uuid.UUID) -> list[Role]: ...

    @abstractmethod
    async def save(self, role: Role) -> Role: ...

    @abstractmethod
    async def get_permissions_for_role(self, role_id: uuid.UUID) -> set[str]: ...

    @abstractmethod
    async def set_permissions_for_role(
        self, role_id: uuid.UUID, permissions: list[str],
    ) -> None: ...
