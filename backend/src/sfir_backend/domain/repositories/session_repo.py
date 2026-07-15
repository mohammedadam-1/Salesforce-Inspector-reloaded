import uuid
from abc import ABC, abstractmethod

from sfir_backend.domain.entities.session import Session


class ISessionRepository(ABC):
    @abstractmethod
    async def get_by_id(self, session_id: uuid.UUID) -> Session | None: ...

    @abstractmethod
    async def list_active_by_user(self, user_id: uuid.UUID) -> list[Session]: ...

    @abstractmethod
    async def save(self, session: Session) -> Session: ...

    @abstractmethod
    async def revoke(self, session_id: uuid.UUID) -> None: ...

    @abstractmethod
    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None: ...
