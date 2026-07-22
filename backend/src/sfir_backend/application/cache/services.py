from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from sfir_backend.domain.cache.models import CacheComponentType, CachePolicy, CacheStrategy
from sfir_backend.infrastructure.cache.coordinator import CacheCoordinator
from sfir_backend.infrastructure.cache.key_builder import CacheKeyBuilder
from sfir_backend.infrastructure.cache.metrics import CacheMetricsCollector

logger = structlog.get_logger(__name__)

_SEARCH_TTL = 60
_METADATA_TTL = 600
_GRAPH_TTL = 900
_DOC_TTL = 1800
_SETTINGS_TTL = 300
_CONNECTION_TTL = 120
_PERMISSION_TTL = 120
_RATE_LIMIT_TTL = 60
_FEATURE_FLAG_TTL = 60


class BaseCacheService:
    def __init__(
        self,
        coordinator: CacheCoordinator,
        key_builder: CacheKeyBuilder,
        metrics: CacheMetricsCollector | None = None,
    ) -> None:
        self._coordinator = coordinator
        self._key_builder = key_builder
        self._metrics = metrics or CacheMetricsCollector()
        self._policy = CachePolicy(strategy=CacheStrategy.ASIDE)

    @property
    def metrics(self) -> CacheMetricsCollector:
        return self._metrics


class MetadataCacheService(BaseCacheService):
    def __init__(
        self,
        coordinator: CacheCoordinator,
        key_builder: CacheKeyBuilder,
        metrics: CacheMetricsCollector | None = None,
    ) -> None:
        super().__init__(coordinator, key_builder, metrics)
        self._policy = CachePolicy(
            strategy=CacheStrategy.ASIDE,
            ttl_seconds=_METADATA_TTL,
        )
        self._metrics.component = "metadata"

    async def get_metadata(
        self,
        metadata_id: str,
        loader: Callable[[], Awaitable[Any]],
        *,
        tenant_id: str = "",
        organization_id: str = "",
        version: str = "",
    ) -> Any | None:
        key = self._key_builder.metadata_key(
            metadata_id,
            tenant_id=tenant_id,
            organization_id=organization_id,
            version=version,
        )
        return await self._coordinator.read(key, loader, policy=self._policy)

    async def invalidate(
        self,
        metadata_id: str,
        *,
        tenant_id: str = "",
        organization_id: str = "",
    ) -> int:
        pattern = self._key_builder.build_pattern(
            CacheComponentType.METADATA,
            tenant_id=tenant_id,
            organization_id=organization_id,
            component_id=metadata_id,
        )
        return await self._coordinator.invalidate_pattern(pattern)


class GraphCacheService(BaseCacheService):
    def __init__(
        self,
        coordinator: CacheCoordinator,
        key_builder: CacheKeyBuilder,
        metrics: CacheMetricsCollector | None = None,
    ) -> None:
        super().__init__(coordinator, key_builder, metrics)
        self._policy = CachePolicy(
            strategy=CacheStrategy.ASIDE,
            ttl_seconds=_GRAPH_TTL,
        )
        self._metrics.component = "graph"

    async def get_graph(
        self,
        organization_id: str,
        loader: Callable[[], Awaitable[Any]],
        *,
        tenant_id: str = "",
        version: str = "",
    ) -> Any | None:
        key = self._key_builder.graph_key(
            organization_id,
            tenant_id=tenant_id,
            version=version,
        )
        return await self._coordinator.read(key, loader, policy=self._policy)

    async def invalidate(
        self,
        *,
        tenant_id: str = "",
        organization_id: str = "",
    ) -> int:
        pattern = self._key_builder.build_pattern(
            CacheComponentType.GRAPH,
            tenant_id=tenant_id,
            organization_id=organization_id,
        )
        return await self._coordinator.invalidate_pattern(pattern)


class SearchCacheService(BaseCacheService):
    def __init__(
        self,
        coordinator: CacheCoordinator,
        key_builder: CacheKeyBuilder,
        metrics: CacheMetricsCollector | None = None,
    ) -> None:
        super().__init__(coordinator, key_builder, metrics)
        self._policy = CachePolicy(
            strategy=CacheStrategy.ASIDE,
            ttl_seconds=_SEARCH_TTL,
        )
        self._metrics.component = "search"

    async def get_search_results(
        self,
        query_hash: str,
        loader: Callable[[], Awaitable[Any]],
        *,
        tenant_id: str = "",
        organization_id: str = "",
    ) -> Any | None:
        key = self._key_builder.search_key(
            query_hash,
            tenant_id=tenant_id,
            organization_id=organization_id,
        )
        return await self._coordinator.read(key, loader, policy=self._policy)

    async def invalidate(
        self,
        *,
        tenant_id: str = "",
        organization_id: str = "",
    ) -> int:
        pattern = self._key_builder.build_pattern(
            CacheComponentType.SEARCH,
            tenant_id=tenant_id,
            organization_id=organization_id,
        )
        return await self._coordinator.invalidate_pattern(pattern)


class AutocompleteCacheService(BaseCacheService):
    def __init__(
        self,
        coordinator: CacheCoordinator,
        key_builder: CacheKeyBuilder,
        metrics: CacheMetricsCollector | None = None,
    ) -> None:
        super().__init__(coordinator, key_builder, metrics)
        self._policy = CachePolicy(
            strategy=CacheStrategy.ASIDE,
            ttl_seconds=_SEARCH_TTL,
        )
        self._metrics.component = "autocomplete"

    async def get_suggestions(
        self,
        prefix: str,
        loader: Callable[[], Awaitable[Any]],
        *,
        tenant_id: str = "",
        organization_id: str = "",
    ) -> Any | None:
        key = self._key_builder.autocomplete_key(
            prefix,
            tenant_id=tenant_id,
            organization_id=organization_id,
        )
        return await self._coordinator.read(key, loader, policy=self._policy)

    async def invalidate(
        self,
        *,
        tenant_id: str = "",
        organization_id: str = "",
    ) -> int:
        pattern = self._key_builder.build_pattern(
            CacheComponentType.AUTOCOMPLETE,
            tenant_id=tenant_id,
            organization_id=organization_id,
        )
        return await self._coordinator.invalidate_pattern(pattern)


class ImpactCacheService(BaseCacheService):
    def __init__(
        self,
        coordinator: CacheCoordinator,
        key_builder: CacheKeyBuilder,
        metrics: CacheMetricsCollector | None = None,
    ) -> None:
        super().__init__(coordinator, key_builder, metrics)
        self._policy = CachePolicy(
            strategy=CacheStrategy.ASIDE,
            ttl_seconds=_GRAPH_TTL,
        )
        self._metrics.component = "impact"

    async def get_impact(
        self,
        component_id: str,
        loader: Callable[[], Awaitable[Any]],
        *,
        tenant_id: str = "",
        organization_id: str = "",
    ) -> Any | None:
        key = self._key_builder.impact_key(
            component_id,
            tenant_id=tenant_id,
            organization_id=organization_id,
        )
        return await self._coordinator.read(key, loader, policy=self._policy)

    async def invalidate(
        self,
        component_id: str,
        *,
        tenant_id: str = "",
        organization_id: str = "",
    ) -> int:
        pattern = self._key_builder.build_pattern(
            CacheComponentType.IMPACT,
            tenant_id=tenant_id,
            organization_id=organization_id,
            component_id=component_id,
        )
        return await self._coordinator.invalidate_pattern(pattern)


class DocumentationCacheService(BaseCacheService):
    def __init__(
        self,
        coordinator: CacheCoordinator,
        key_builder: CacheKeyBuilder,
        metrics: CacheMetricsCollector | None = None,
    ) -> None:
        super().__init__(coordinator, key_builder, metrics)
        self._policy = CachePolicy(
            strategy=CacheStrategy.ASIDE,
            ttl_seconds=_DOC_TTL,
        )
        self._metrics.component = "documentation"

    async def get_documentation(
        self,
        component_id: str,
        loader: Callable[[], Awaitable[Any]],
        *,
        tenant_id: str = "",
        organization_id: str = "",
        version: str = "",
    ) -> Any | None:
        key = self._key_builder.documentation_key(
            component_id,
            tenant_id=tenant_id,
            organization_id=organization_id,
            version=version,
        )
        return await self._coordinator.read(key, loader, policy=self._policy)

    async def invalidate(
        self,
        component_id: str,
        *,
        tenant_id: str = "",
        organization_id: str = "",
    ) -> int:
        pattern = self._key_builder.build_pattern(
            CacheComponentType.DOCUMENTATION,
            tenant_id=tenant_id,
            organization_id=organization_id,
            component_id=component_id,
        )
        return await self._coordinator.invalidate_pattern(pattern)


class OrgSettingsCacheService(BaseCacheService):
    def __init__(
        self,
        coordinator: CacheCoordinator,
        key_builder: CacheKeyBuilder,
        metrics: CacheMetricsCollector | None = None,
    ) -> None:
        super().__init__(coordinator, key_builder, metrics)
        self._policy = CachePolicy(
            strategy=CacheStrategy.ASIDE,
            ttl_seconds=_SETTINGS_TTL,
        )
        self._metrics.component = "settings"

    async def get_settings(
        self,
        organization_id: str,
        loader: Callable[[], Awaitable[Any]],
        *,
        tenant_id: str = "",
    ) -> Any | None:
        key = self._key_builder.settings_key(
            organization_id,
            tenant_id=tenant_id,
        )
        return await self._coordinator.read(key, loader, policy=self._policy)

    async def invalidate(
        self,
        organization_id: str,
        *,
        tenant_id: str = "",
    ) -> int:
        pattern = self._key_builder.build_pattern(
            CacheComponentType.SETTINGS,
            tenant_id=tenant_id,
            organization_id=organization_id,
        )
        return await self._coordinator.invalidate_pattern(pattern)


class ConnectionStatusCacheService(BaseCacheService):
    def __init__(
        self,
        coordinator: CacheCoordinator,
        key_builder: CacheKeyBuilder,
        metrics: CacheMetricsCollector | None = None,
    ) -> None:
        super().__init__(coordinator, key_builder, metrics)
        self._policy = CachePolicy(
            strategy=CacheStrategy.ASIDE,
            ttl_seconds=_CONNECTION_TTL,
        )
        self._metrics.component = "connection_status"

    async def get_connection_status(
        self,
        connection_id: str,
        loader: Callable[[], Awaitable[Any]],
        *,
        tenant_id: str = "",
        organization_id: str = "",
    ) -> Any | None:
        key = self._key_builder.connection_status_key(
            connection_id,
            tenant_id=tenant_id,
            organization_id=organization_id,
        )
        return await self._coordinator.read(key, loader, policy=self._policy)

    async def invalidate(
        self,
        connection_id: str,
        *,
        tenant_id: str = "",
        organization_id: str = "",
    ) -> int:
        pattern = self._key_builder.build_pattern(
            CacheComponentType.CONNECTION_STATUS,
            tenant_id=tenant_id,
            organization_id=organization_id,
            component_id=connection_id,
        )
        return await self._coordinator.invalidate_pattern(pattern)


class PermissionCacheService(BaseCacheService):
    def __init__(
        self,
        coordinator: CacheCoordinator,
        key_builder: CacheKeyBuilder,
        metrics: CacheMetricsCollector | None = None,
    ) -> None:
        super().__init__(coordinator, key_builder, metrics)
        self._policy = CachePolicy(
            strategy=CacheStrategy.ASIDE,
            ttl_seconds=_PERMISSION_TTL,
        )
        self._metrics.component = "permissions"

    async def get_permissions(
        self,
        user_id: str,
        organization_id: str,
        loader: Callable[[], Awaitable[Any]],
        *,
        tenant_id: str = "",
    ) -> Any | None:
        key = self._key_builder.permissions_key(
            user_id,
            organization_id,
            tenant_id=tenant_id,
        )
        return await self._coordinator.read(key, loader, policy=self._policy)

    async def invalidate(
        self,
        _user_id: str,
        organization_id: str,
        *,
        tenant_id: str = "",
    ) -> int:
        pattern = self._key_builder.build_pattern(
            CacheComponentType.PERMISSIONS,
            tenant_id=tenant_id,
            organization_id=organization_id,
        )
        return await self._coordinator.invalidate_pattern(pattern)


class RateLimitCacheService(BaseCacheService):
    def __init__(
        self,
        coordinator: CacheCoordinator,
        key_builder: CacheKeyBuilder,
        metrics: CacheMetricsCollector | None = None,
    ) -> None:
        super().__init__(coordinator, key_builder, metrics)
        self._policy = CachePolicy(
            strategy=CacheStrategy.ASIDE,
            ttl_seconds=_RATE_LIMIT_TTL,
        )
        self._metrics.component = "rate_limit"

    async def get_count(
        self,
        identifier: str,
        *,
        tenant_id: str = "",
        organization_id: str = "",
    ) -> int:
        key = self._key_builder.rate_limit_key(
            identifier,
            tenant_id=tenant_id,
            organization_id=organization_id,
        )
        result = await self._coordinator.manager.get(key)
        return result if isinstance(result, int) else 0

    async def increment(
        self,
        identifier: str,
        amount: int = 1,
        *,
        tenant_id: str = "",
        organization_id: str = "",
    ) -> int:
        key = self._key_builder.rate_limit_key(
            identifier,
            tenant_id=tenant_id,
            organization_id=organization_id,
        )
        return await self._coordinator.manager.increment(key, amount)


class FeatureFlagCacheService(BaseCacheService):
    def __init__(
        self,
        coordinator: CacheCoordinator,
        key_builder: CacheKeyBuilder,
        metrics: CacheMetricsCollector | None = None,
    ) -> None:
        super().__init__(coordinator, key_builder, metrics)
        self._policy = CachePolicy(
            strategy=CacheStrategy.ASIDE,
            ttl_seconds=_FEATURE_FLAG_TTL,
        )
        self._metrics.component = "feature_flags"

    async def get_flag(
        self,
        flag_name: str,
        loader: Callable[[], Awaitable[Any]],
        *,
        tenant_id: str = "",
        organization_id: str = "",
    ) -> Any | None:
        key = self._key_builder.feature_flag_key(
            flag_name,
            tenant_id=tenant_id,
            organization_id=organization_id,
        )
        return await self._coordinator.read(key, loader, policy=self._policy)

    async def invalidate(
        self,
        _flag_name: str,
        *,
        tenant_id: str = "",
        organization_id: str = "",
    ) -> int:
        pattern = self._key_builder.build_pattern(
            CacheComponentType.FEATURE_FLAGS,
            tenant_id=tenant_id,
            organization_id=organization_id,
        )
        return await self._coordinator.invalidate_pattern(pattern)
