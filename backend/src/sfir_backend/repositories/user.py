"""User repository."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.infrastructure.database.models.identity import (
    Permission,
    RolePermission,
    User,
    UserRole,
)
from sfir_backend.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, User)

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def get_by_external_subject(self, subject: str) -> User | None:
        result = await self._session.execute(
            select(User).where(User.external_subject == subject)
        )
        return result.scalar_one_or_none()

    async def has_permission(
        self, user_id: uuid.UUID, permission_code: str
    ) -> bool:
        query = (
            select(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(
                UserRole.user_id == user_id,
                Permission.code == permission_code,
            )
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none() is not None

    async def get_users_by_organization(
        self, organization_id: uuid.UUID, skip: int = 0, limit: int = 100
    ) -> list[User]:
        query = (
            select(User)
            .join(UserRole, UserRole.user_id == User.id)
            .where(UserRole.organization_id == organization_id)
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())
