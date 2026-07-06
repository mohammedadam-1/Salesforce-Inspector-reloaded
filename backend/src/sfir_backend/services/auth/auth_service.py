"""Authentication service — login, logout, token refresh, OAuth."""

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.infrastructure.database.models.identity import User
from sfir_backend.infrastructure.security.jwt import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from sfir_backend.repositories.user import UserRepository

logger = structlog.get_logger(__name__)


class AuthenticationError(Exception):
    pass


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._user_repo = UserRepository(session)

    async def login(
        self, email: str, password: str, organization_id: uuid.UUID | None = None
    ) -> tuple[str, str, User]:
        """Authenticate a user with email and password.

        Returns:
            Tuple of (access_token, refresh_token, user)
        """
        user = await self._user_repo.get_by_email(email)
        if not user:
            raise AuthenticationError("Invalid email or password")

        if not user.password_hash:
            raise AuthenticationError(
                "This account uses SSO. Please sign in with your provider."
            )

        if not verify_password(password, user.password_hash):
            raise AuthenticationError("Invalid email or password")

        if not user.is_active:
            raise AuthenticationError("Account is deactivated")

        user.last_login_at = datetime.now(UTC)
        await self._session.flush()

        org_id_str = str(organization_id) if organization_id else None
        access_token = create_access_token(
            subject=str(user.id),
            organization_id=org_id_str,
        )
        refresh_token = create_refresh_token(subject=str(user.id))

        logger.info("user_logged_in", user_id=str(user.id))
        return access_token, refresh_token, user

    async def refresh_token(
        self, refresh_token_str: str
    ) -> tuple[str, str]:
        """Refresh an access token using a refresh token.

        Returns:
            Tuple of (new_access_token, new_refresh_token)
        """
        payload = decode_refresh_token(refresh_token_str)
        user_id = payload.get("sub")

        user = await self._user_repo.get_by_id(uuid.UUID(user_id))
        if not user or not user.is_active:
            raise AuthenticationError("User not found or inactive")

        new_access = create_access_token(
            subject=str(user.id),
            organization_id=payload.get("org"),
        )
        new_refresh = create_refresh_token(subject=str(user.id))

        logger.info("token_refreshed", user_id=str(user.id))
        return new_access, new_refresh

    async def register(
        self,
        email: str,
        display_name: str,
        password: str,
    ) -> User:
        """Register a new user account."""
        existing = await self._user_repo.get_by_email(email)
        if existing:
            raise AuthenticationError("Email already registered")

        user = User(
            id=uuid.uuid4(),
            email=email,
            display_name=display_name,
            password_hash=hash_password(password),
            is_active=True,
        )
        user = await self._user_repo.create(user)

        logger.info("user_registered", user_id=str(user.id))
        return user

    async def get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self._user_repo.get_by_id(user_id)

    async def get_current_user(self, user_id: uuid.UUID) -> User | None:
        return await self._user_repo.get_by_id(user_id)
