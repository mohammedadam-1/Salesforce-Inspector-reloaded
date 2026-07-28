import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.domain.entities.user import User
from sfir_backend.domain.repositories import IUserRepository
from sfir_backend.domain.value_objects.email import Email
from sfir_backend.domain.value_objects.user_status import UserStatus
from sfir_backend.infrastructure.persistence.models.user import UserModel


class UserRepository(IUserRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self._session.get(UserModel, user_id)
        return self._to_domain(result) if result else None

    async def get_by_email(self, email: Email) -> User | None:
        result = await self._session.execute(
            select(UserModel).where(UserModel.email == str(email)),
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def email_exists(self, email: Email) -> bool:
        result = await self._session.execute(
            select(UserModel.id).where(UserModel.email == str(email)).limit(1),
        )
        return result.scalar_one_or_none() is not None

    async def save(self, user: User) -> User:
        model = UserModel(
            id=user.id,
            email=str(user.email),
            password_hash=user.password_hash,
            display_name=user.display_name,
            status=user.status.value,
            is_locked=user.is_locked,
            locked_until=user.locked_until,
            login_attempts=user.login_attempts,
            last_login_at=user.last_login_at,
            email_verified_at=user.email_verified_at,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.commit()
        return user

    async def update(self, user: User) -> User:
        model = await self._session.get(UserModel, user.id)
        if not model:
            raise ValueError(f"User {user.id} not found for update")
        model.email = str(user.email)
        model.password_hash = user.password_hash
        model.display_name = user.display_name
        model.status = user.status.value
        model.is_locked = user.is_locked
        model.locked_until = user.locked_until
        model.login_attempts = user.login_attempts
        model.last_login_at = user.last_login_at
        model.updated_at = user.updated_at
        await self._session.flush()
        await self._session.commit()
        return user

    async def update_login_attempts(
        self, user_id: uuid.UUID, attempts: int,
    ) -> None:
        model = await self._session.get(UserModel, user_id)
        if model:
            model.login_attempts = attempts
            await self._session.flush()
            await self._session.commit()

    def _to_domain(self, model: UserModel) -> User:
        return User(
            id=model.id,
            email=Email(model.email),
            password_hash=model.password_hash,
            display_name=model.display_name,
            status=UserStatus(model.status),
            is_locked=model.is_locked,
            locked_until=model.locked_until,
            login_attempts=model.login_attempts,
            last_login_at=model.last_login_at,
            email_verified_at=model.email_verified_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
