"""Authentication endpoints."""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.api.deps import get_current_user, get_db
from sfir_backend.config.settings import get_settings
from sfir_backend.schemas.auth import (
    ErrorResponse,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    TokenRefreshRequest,
    TokenRefreshResponse,
    UserResponse,
)
from sfir_backend.services.auth.auth_service import AuthService, AuthenticationError

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()


@router.post(
    "/login",
    response_model=LoginResponse,
    responses={401: {"model": ErrorResponse}},
)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate a user with email and password."""
    service = AuthService(db)
    try:
        org_id = uuid.UUID(request.organization_id) if request.organization_id else None
        access_token, refresh_token, user = await service.login(
            email=request.email,
            password=request.password,
            organization_id=org_id,
        )
        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.jwt_access_token_expire_minutes * 60,
            user=UserResponse.model_validate(user),
        )
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_ERROR", "message": str(e)},
        )


@router.post(
    "/refresh",
    response_model=TokenRefreshResponse,
    responses={401: {"model": ErrorResponse}},
)
async def refresh_token(
    request: TokenRefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Refresh an access token."""
    service = AuthService(db)
    try:
        access_token, new_refresh = await service.refresh_token(
            request.refresh_token
        )
        return TokenRefreshResponse(
            access_token=access_token,
            refresh_token=new_refresh,
            expires_in=settings.jwt_access_token_expire_minutes * 60,
        )
    except (AuthenticationError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "TOKEN_ERROR", "message": str(e)},
        )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorResponse}},
)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user account."""
    service = AuthService(db)
    try:
        user = await service.register(
            email=request.email,
            display_name=request.display_name,
            password=request.password,
        )
        return UserResponse.model_validate(user)
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "REGISTRATION_ERROR", "message": str(e)},
        )


@router.get(
    "/me",
    response_model=UserResponse,
)
async def get_current_user_info(
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Get the current authenticated user's information."""
    return UserResponse.model_validate(user)
