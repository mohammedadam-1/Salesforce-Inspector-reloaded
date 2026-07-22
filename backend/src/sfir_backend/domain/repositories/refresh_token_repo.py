import uuid
from abc import ABC, abstractmethod

from sfir_backend.domain.entities.refresh_token import RefreshToken


class IRefreshTokenRepository(ABC):
    @abstractmethod
    async def get_by_id(self, token_id: uuid.UUID) -> RefreshToken | None: ...

    @abstractmethod
    async def get_by_token_hash(self, token_hash: str) -> RefreshToken | None: ...

    @abstractmethod
    async def save(self, token: RefreshToken) -> RefreshToken: ...

    @abstractmethod
    async def revoke(self, token_id: uuid.UUID) -> None: ...

    @abstractmethod
    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None: ...
