"""API key repository."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update

from sfir_backend.infrastructure.database.models.identity import ApiKey
from sfir_backend.repositories.base import BaseRepository


class ApiKeyRepository(BaseRepository[ApiKey]):
    def __init__(self, session) -> None:
        super().__init__(session, ApiKey)

    async def get_by_key_hash(self, key_hash: str) -> ApiKey | None:
        result = await self._session.execute(
            select(ApiKey).where(ApiKey.key_hash == key_hash)
        )
        return result.scalar_one_or_none()

    async def get_keys_by_user(
        self, user_id: uuid.UUID, skip: int = 0, limit: int = 100
    ) -> list[ApiKey]:
        result = await self._session.execute(
            select(ApiKey)
            .where(ApiKey.user_id == user_id, ApiKey.revoked_at.is_(None))
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update_last_used(self, key_id: uuid.UUID) -> None:
        await self._session.execute(
            update(ApiKey)
            .where(ApiKey.id == key_id)
            .values(last_used_at=datetime.now(UTC))
        )
        await self._session.flush()
