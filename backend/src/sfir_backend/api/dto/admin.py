import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AdminUserResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    status: str
    is_locked: bool
    login_attempts: int
    last_login_at: datetime | None = None
    created_at: datetime | None = None
    organization_count: int = 0


class AdminOrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    status: str
    member_count: int = 0
    salesforce_connected: bool = False
    created_at: datetime | None = None


class AdminAuditEntryResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    organization_id: uuid.UUID | None
    action: str
    resource_type: str
    resource_id: str
    details: dict | None
    ip_address: str
    created_at: datetime


class AdminSystemResponse(BaseModel):
    version: str = "0.1.0"
    environment: str
    uptime_seconds: float = 0
    database_status: str = "unknown"
    redis_status: str = "unknown"
    active_users: int = 0
    active_jobs: int = 0
    total_organizations: int = 0
    total_salesforce_connections: int = 0
    memory_usage_mb: float = 0


class AdminConfigResponse(BaseModel):
    environment: str
    log_level: str
    cors_origins: list[str]
    rate_limit_default: int
    observability: dict[str, Any] = {}
    security: dict[str, Any] = {}


class CacheStatisticsResponse(BaseModel):
    hits: int = 0
    misses: int = 0
    hit_ratio: float = 0.0
    size: int = 0
    memory_bytes: int = 0
    keys_by_prefix: dict[str, int] = {}
