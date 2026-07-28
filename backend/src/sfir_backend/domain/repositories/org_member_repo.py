import uuid
from abc import ABC, abstractmethod

from sfir_backend.domain.entities.org_member import OrgMember


class IOrgMemberRepository(ABC):
    @abstractmethod
    async def get_by_id(self, member_id: uuid.UUID) -> OrgMember | None: ...

    @abstractmethod
    async def get_by_user_and_org(
        self, user_id: uuid.UUID, org_id: uuid.UUID,
    ) -> OrgMember | None: ...

    @abstractmethod
    async def list_by_user(self, user_id: uuid.UUID) -> list[OrgMember]: ...

    @abstractmethod
    async def list_by_org(self, org_id: uuid.UUID) -> list[OrgMember]: ...

    @abstractmethod
    async def save(self, member: OrgMember) -> OrgMember: ...

    @abstractmethod
    async def update(self, member: OrgMember) -> OrgMember: ...

    @abstractmethod
    async def set_default(self, user_id: uuid.UUID, org_id: uuid.UUID) -> None: ...
