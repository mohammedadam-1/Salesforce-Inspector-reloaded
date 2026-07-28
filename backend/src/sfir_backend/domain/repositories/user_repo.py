import uuid
from abc import ABC, abstractmethod

from sfir_backend.domain.entities.user import User
from sfir_backend.domain.value_objects.email import Email


class IUserRepository(ABC):
    @abstractmethod
    async def get_by_id(self, user_id: uuid.UUID) -> User | None: ...

    @abstractmethod
    async def get_by_email(self, email: Email) -> User | None: ...

    @abstractmethod
    async def email_exists(self, email: Email) -> bool: ...

    @abstractmethod
    async def save(self, user: User) -> User: ...

    @abstractmethod
    async def update(self, user: User) -> User: ...

    @abstractmethod
    async def update_login_attempts(
        self, user_id: uuid.UUID, attempts: int,
    ) -> None: ...
