import uuid
from datetime import UTC

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.domain.entities.refresh_token import RefreshToken
from sfir_backend.domain.repositories.refresh_token_repo import IRefreshTokenRepository
from sfir_backend.infrastructure.persistence.models.refresh_token import (
    RefreshTokenModel,
)


class RefreshTokenRepository(IRefreshTokenRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, token_id: uuid.UUID) -> RefreshToken | None:
        result = await self._session.get(RefreshTokenModel, token_id)
        return self._to_domain(result) if result else None

    async def get_by_token_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self._session.execute(
            select(RefreshTokenModel)
            .where(RefreshTokenModel.token_hash == token_hash),
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def save(self, token: RefreshToken) -> RefreshToken:
        model = RefreshTokenModel(
            id=token.id,
            user_id=token.user_id,
            token_hash=token.token_hash,
            expires_at=token.expires_at,
            is_revoked=token.is_revoked,
            revoked_at=token.revoked_at,
            created_at=token.created_at,
        )
        self._session.add(model)
        await self._session.flush()
        return token

    async def revoke(self, token_id: uuid.UUID) -> None:
        from datetime import datetime

        await self._session.execute(
            update(RefreshTokenModel)
            .where(RefreshTokenModel.id == token_id)
            .values(is_revoked=True, revoked_at=datetime.now(UTC)),
        )
        await self._session.flush()

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        from datetime import datetime

        await self._session.execute(
            update(RefreshTokenModel)
            .where(RefreshTokenModel.user_id == user_id)
            .where(RefreshTokenModel.is_revoked.is_(False))
            .values(is_revoked=True, revoked_at=datetime.now(UTC)),
        )
        await self._session.flush()

    def _to_domain(self, model: RefreshTokenModel) -> RefreshToken:
        return RefreshToken(
            id=model.id,
            user_id=model.user_id,
            token_hash=model.token_hash,
            expires_at=model.expires_at,
            is_revoked=model.is_revoked,
            revoked_at=model.revoked_at,
            created_at=model.created_at,
        )
