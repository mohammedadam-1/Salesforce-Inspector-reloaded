from __future__ import annotations

from typing import Any

import structlog

from sfir_backend.domain.cache.models import CacheComponentType
from sfir_backend.infrastructure.cache.key_builder import CacheKeyBuilder
from sfir_backend.infrastructure.cache.manager import CacheManager

logger = structlog.get_logger(__name__)


class TenantAwareCache:
    def __init__(
        self,
        manager: CacheManager,
        tenant_id: str,
        organization_id: str = "",
    ) -> None:
        self._manager = manager
        self._tenant_id = tenant_id
        self._organization_id = organization_id
        self._key_builder = CacheKeyBuilder()

    def _build_key(
        self,
        component_type: CacheComponentType,
        component_id: str = "",
        *,
        version: str = "",
    ) -> str:
        return self._key_builder.build(
            component_type,
            component_id,
            tenant_id=self._tenant_id,
            organization_id=self._organization_id,
            version=version,
        )

    def _build_pattern(
        self,
        component_type: CacheComponentType | None = None,
        *,
        component_id: str = "",
    ) -> str:
        return self._key_builder.build_pattern(
            component_type,
            tenant_id=self._tenant_id,
            organization_id=self._organization_id,
            component_id=component_id,
        )

    async def get(self, key: str) -> Any | None:
        return await self._manager.get(key)

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int = 300,
    ) -> None:
        await self._manager.set(key, value, ttl_seconds=ttl_seconds)

    async def get_component(
        self,
        component_type: CacheComponentType,
        component_id: str = "",
        *,
        version: str = "",
    ) -> Any | None:
        key = self._build_key(component_type, component_id, version=version)
        return await self._manager.get(key)

    async def set_component(
        self,
        component_type: CacheComponentType,
        component_id: str,
        value: Any,
        *,
        ttl_seconds: int = 300,
        version: str = "",
    ) -> None:
        key = self._build_key(component_type, component_id, version=version)
        await self._manager.set(key, value, ttl_seconds=ttl_seconds)

    async def invalidate_component(
        self,
        component_type: CacheComponentType,
        component_id: str = "",
    ) -> int:
        pattern = self._build_pattern(component_type, component_id=component_id)
        return await self._manager.invalidate_pattern(pattern)

    async def invalidate_all(self) -> int:
        pattern = self._build_pattern()
        return await self._manager.invalidate_pattern(pattern)

    async def invalidate_organization(self) -> int:
        return await self.invalidate_all()

    async def exists(self, key: str) -> bool:
        return await self._manager.exists(key)

    async def increment(self, key: str, amount: int = 1) -> int:
        return await self._manager.increment(key, amount)

    @property
    def tenant_id(self) -> str:
        return self._tenant_id

    @property
    def organization_id(self) -> str:
        return self._organization_id

    @property
    def manager(self) -> CacheManager:
        return self._manager
