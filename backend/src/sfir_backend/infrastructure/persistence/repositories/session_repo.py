import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.domain.entities.session import Session
from sfir_backend.domain.repositories.session_repo import ISessionRepository
from sfir_backend.infrastructure.persistence.models.session import SessionModel


class SessionRepository(ISessionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, session_id: uuid.UUID) -> Session | None:
        result = await self._session.get(SessionModel, session_id)
        return self._to_domain(result) if result else None

    async def list_active_by_user(self, user_id: uuid.UUID) -> list[Session]:
        result = await self._session.execute(
            select(SessionModel)
            .where(SessionModel.user_id == user_id)
            .where(SessionModel.is_active.is_(True)),
        )
        return [self._to_domain(m) for m in result.scalars().all()]

    async def save(self, session: Session) -> Session:
        model = SessionModel(
            id=session.id,
            user_id=session.user_id,
            organization_id=session.organization_id,
            refresh_token_id=session.refresh_token_id,
            ip_address=session.ip_address,
            user_agent=session.user_agent,
            is_active=session.is_active,
            expires_at=session.expires_at,
            created_at=session.created_at,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.commit()
        return session

    async def revoke(self, session_id: uuid.UUID) -> None:
        await self._session.execute(
            update(SessionModel)
            .where(SessionModel.id == session_id)
            .values(is_active=False),
        )
        await self._session.flush()
        await self._session.commit()

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        await self._session.execute(
            update(SessionModel)
            .where(SessionModel.user_id == user_id)
            .where(SessionModel.is_active.is_(True))
            .values(is_active=False),
        )
        await self._session.flush()
        await self._session.commit()

    def _to_domain(self, model: SessionModel) -> Session:
        return Session(
            id=model.id,
            user_id=model.user_id,
            organization_id=model.organization_id,
            refresh_token_id=model.refresh_token_id,
            ip_address=model.ip_address,
            user_agent=model.user_agent,
            is_active=model.is_active,
            expires_at=model.expires_at,
            created_at=model.created_at,
        )
