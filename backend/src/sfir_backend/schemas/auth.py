"""Auth request/response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: str = Field(..., examples=["user@example.com"])
    password: str = Field(..., min_length=8, max_length=128)
    organization_id: str | None = Field(default=None, examples=["org_001"])


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserResponse"


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class TokenRefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RegisterRequest(BaseModel):
    email: str = Field(..., examples=["user@example.com"])
    display_name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    is_active: bool
    is_service_account: bool
    last_login_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None


class ErrorResponse(BaseModel):
    status: str = "error"
    error: "ErrorDetail"


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict | None = None
