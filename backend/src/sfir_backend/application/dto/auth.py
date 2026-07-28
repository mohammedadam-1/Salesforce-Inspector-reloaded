import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class LoginRequest:
    email: str
    password: str
    ip_address: str = ""
    user_agent: str = ""


@dataclass
class LoginResponse:
    user_id: uuid.UUID
    email: str
    display_name: str
    access_token: str
    refresh_token: str
    expires_in: int
    organization_id: uuid.UUID | None = None
    organization_name: str | None = None
    role_slug: str | None = None


@dataclass
class RefreshTokenRequest:
    refresh_token: str


@dataclass
class RefreshTokenResponse:
    access_token: str
    refresh_token: str
    expires_in: int


@dataclass
class CurrentUserResponse:
    user_id: uuid.UUID
    email: str
    display_name: str
    status: str
    email_verified: bool
    last_login_at: datetime | None = None
    current_organization_id: uuid.UUID | None = None
    current_organization_name: str | None = None
    permissions: list[str] = field(default_factory=list)


@dataclass
class RegisterRequest:
    email: str
    password: str
    display_name: str
