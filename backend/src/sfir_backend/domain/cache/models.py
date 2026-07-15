from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class CacheStrategy(StrEnum):
    ASIDE = "aside"
    READ_THROUGH = "read_through"
    WRITE_THROUGH = "write_through"
    WRITE_AROUND = "write_around"
    REFRESH_AHEAD = "refresh_ahead"


class CacheComponentType(StrEnum):
    METADATA = "metadata"
    CANONICAL = "canonical"
    GRAPH = "graph"
    SEARCH = "search"
    AUTOCOMPLETE = "autocomplete"
    IMPACT = "impact"
    DOCUMENTATION = "documentation"
    SETTINGS = "settings"
    CONNECTION_STATUS = "connection_status"
    JWT = "jwt"
    PERMISSIONS = "permissions"
    RATE_LIMIT = "rate_limit"
    FEATURE_FLAGS = "feature_flags"
    CONFIGURATION = "configuration"


class CacheInvalidationEvent(StrEnum):
    METADATA_UPDATE = "metadata_update"
    GRAPH_REBUILD = "graph_rebuild"
    DOCUMENTATION_GENERATE = "documentation_generate"
    SEARCH_INDEX = "search_index"
    ORGANIZATION_REMOVAL = "organization_removal"
    PERMISSION_CHANGE = "permission_change"
    SETTINGS_UPDATE = "settings_update"
    CONNECTION_CHANGE = "connection_change"
    MANUAL_FLUSH = "manual_flush"


class CacheInvalidationScope(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    SINGLE_KEY = "single_key"
    COMPONENT = "component"
    TENANT = "tenant"
    ORGANIZATION = "organization"


class CacheKey(BaseModel):
    tenant_id: str = ""
    organization_id: str = ""
    component_type: CacheComponentType = CacheComponentType.CONFIGURATION
    component_id: str = ""
    version: str = ""
    environment: str = "production"

    def to_string(self) -> str:
        parts = [
            self.environment,
            self.tenant_id or "_",
            self.organization_id or "_",
            self.component_type.value,
            self.component_id or "_",
            self.version or "_",
        ]
        return ":".join(parts)

    @classmethod
    def from_string(cls, key: str) -> CacheKey:
        parts = key.split(":")
        return cls(
            environment=parts[0] if len(parts) > 0 else "",
            tenant_id=parts[1] if len(parts) > 1 and parts[1] != "_" else "",
            organization_id=parts[2] if len(parts) > 2 and parts[2] != "_" else "",
            component_type=(
                CacheComponentType(parts[3])
                if len(parts) > 3
                else CacheComponentType.CONFIGURATION
            ),
            component_id=parts[4] if len(parts) > 4 and parts[4] != "_" else "",
            version=parts[5] if len(parts) > 5 and parts[5] != "_" else "",
        )


class CacheEntry(BaseModel):
    key: str = ""
    value: Any = None
    ttl_seconds: int = 300
    component_type: CacheComponentType = CacheComponentType.CONFIGURATION
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    expires_at: datetime | None = None
    version: str = ""
    stale: bool = False

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(tz=UTC) >= self.expires_at

    def time_to_live(self) -> float:
        if self.expires_at is None:
            return float("inf")
        remaining = (self.expires_at - datetime.now(tz=UTC)).total_seconds()
        return max(0.0, remaining)


class CachePolicy(BaseModel):
    strategy: CacheStrategy = CacheStrategy.ASIDE
    ttl_seconds: int = 300
    refresh_ahead_ttl_seconds: int = 60
    invalidation_events: list[CacheInvalidationEvent] = Field(default_factory=list)
    cache_null_values: bool = False
    compress: bool = False
    versioned: bool = True
    max_entry_size_bytes: int = 1_048_576


class CacheMetrics(BaseModel):
    hits: int = 0
    misses: int = 0
    hit_ratio: float = 0.0
    total_operations: int = 0
    average_latency_ms: float = 0.0
    evictions: int = 0
    memory_used_bytes: int = 0
    connection_errors: int = 0


class CacheHealthStatus(BaseModel):
    healthy: bool = True
    connected: bool = False
    ping_latency_ms: float = 0.0
    memory_used_bytes: int = 0
    memory_limit_bytes: int = 0
    peak_memory_bytes: int = 0
    connected_clients: int = 0
    uptime_seconds: int = 0
    total_errors: int = 0
    last_check: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class CacheInvalidationRequest(BaseModel):
    id: str = ""
    event: CacheInvalidationEvent = CacheInvalidationEvent.MANUAL_FLUSH
    scope: CacheInvalidationScope = CacheInvalidationScope.FULL
    tenant_id: str = ""
    organization_id: str = ""
    component_type: CacheComponentType | None = None
    component_id: str = ""
    reason: str = ""
    requested_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    processed: bool = False
    keys_invalidated: int = 0
