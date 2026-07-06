"""FastAPI dependency injection.

Provides reusable dependencies for:
- Database sessions
- Current authenticated user
- Organization context
- Permission checks
- Rate limiting
"""

import uuid
from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.config.settings import get_settings
from sfir_backend.infrastructure.database.session import get_async_session
from sfir_backend.infrastructure.cache.redis import get_redis

settings = get_settings()


async def get_db() -> AsyncIterator[AsyncSession]:
    async for session in get_async_session():
        yield session


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)):
    """Extract and validate the current user from JWT token."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    token = auth_header.removeprefix("Bearer ")
    try:
        from sfir_backend.infrastructure.security.jwt import decode_access_token

        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )

    from sfir_backend.repositories.user import UserRepository

    repo = UserRepository(db)
    user = await repo.get_by_id(uuid.UUID(user_id))
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    request.state.current_user = user
    return user


async def get_current_org_id(request: Request) -> uuid.UUID:
    """Extract the current organization ID from request headers or path."""
    org_id = request.headers.get("X-Organization-ID")
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Organization-ID header is required",
        )
    try:
        return uuid.UUID(org_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid X-Organization-ID format",
        )


async def require_permission(permission_code: str):
    """Dependency factory for permission-based access control."""

    async def _check_permission(
        request: Request,
        db: AsyncSession = Depends(get_db),
        user=Depends(get_current_user),
    ) -> bool:
        if settings.is_development:
            return True
        from sfir_backend.repositories.user import UserRepository
        repo = UserRepository(db)
        has_perm = await repo.has_permission(user.id, permission_code)
        if not has_perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission_code}",
            )
        return True

    return _check_permission


async def get_from_api_key(request: Request, db: AsyncSession = Depends(get_db)):
    """Authenticate via API key (X-API-Key header)."""
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        return None

    from sfir_backend.infrastructure.security.jwt import hash_api_key
    from sfir_backend.repositories.api_key import ApiKeyRepository

    repo = ApiKeyRepository(db)
    key_hash = hash_api_key(api_key)
    key = await repo.get_by_key_hash(key_hash)
    if not key or key.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key",
        )
    if key.expires_at and key.expires_at < __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key has expired",
        )

    await repo.update_last_used(key.id)
    return key
