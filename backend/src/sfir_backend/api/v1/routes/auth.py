import uuid

from fastapi import APIRouter, Depends, Request

from sfir_backend.api.deps import (
    get_auth_service,
    get_current_org_id,
    get_current_user_id,
)
from sfir_backend.application.dto.auth import (
    CurrentUserResponse,
    LoginRequest,
    LoginResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    RegisterRequest,
)
from sfir_backend.application.use_cases.auth import AuthUseCase

router = APIRouter(tags=["Authentication"])


@router.post("/auth/register")
async def register(
    request: RegisterRequest,
    auth: AuthUseCase = Depends(get_auth_service),
) -> LoginResponse:
    return await auth.register(request)


@router.post("/auth/login")
async def login(
    request: LoginRequest,
    http_request: Request,
    auth: AuthUseCase = Depends(get_auth_service),
) -> LoginResponse:
    request.ip_address = http_request.client.host if http_request.client else ""
    request.user_agent = http_request.headers.get("user-agent", "")
    return await auth.login(request)


@router.post("/auth/logout")
async def logout(
    user_id: uuid.UUID = Depends(get_current_user_id),
    auth: AuthUseCase = Depends(get_auth_service),
) -> dict[str, str]:
    await auth.logout(user_id)
    return {"message": "Logged out successfully"}


@router.post("/auth/refresh")
async def refresh(
    request: RefreshTokenRequest,
    auth: AuthUseCase = Depends(get_auth_service),
) -> RefreshTokenResponse:
    return await auth.refresh(request)


@router.get("/auth/me")
async def get_current_user(
    user_id: uuid.UUID = Depends(get_current_user_id),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    auth: AuthUseCase = Depends(get_auth_service),
) -> CurrentUserResponse:
    return await auth.get_current_user(user_id, org_id)
