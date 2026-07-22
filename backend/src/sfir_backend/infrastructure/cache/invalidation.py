from __future__ import annotations

import structlog

from sfir_backend.domain.cache.models import (
    CacheComponentType,
    CacheInvalidationEvent,
    CacheInvalidationRequest,
    CacheInvalidationScope,
)
from sfir_backend.infrastructure.cache.coordinator import CacheCoordinator
from sfir_backend.infrastructure.cache.key_builder import CacheKeyBuilder

logger = structlog.get_logger(__name__)


class CacheInvalidationManager:
    def __init__(
        self,
        coordinator: CacheCoordinator,
        key_builder: CacheKeyBuilder,
    ) -> None:
        self._coordinator = coordinator
        self._key_builder = key_builder

    async def invalidate(
        self,
        request: CacheInvalidationRequest,
    ) -> CacheInvalidationRequest:
        evt_name = request.event.value
        logger.info(
            "cache_invalidation_started",
            event_name=evt_name,
            scope=request.scope.value,
            reason=request.reason,
        )

        try:
            keys_invalidated = 0

            if request.scope == CacheInvalidationScope.FULL:
                keys_invalidated = await self._full_flush()
            elif request.scope == CacheInvalidationScope.TENANT:
                keys_invalidated = await self._invalidate_tenant(request.tenant_id)
            elif request.scope == CacheInvalidationScope.ORGANIZATION:
                keys_invalidated = await self._invalidate_organization(
                    request.tenant_id, request.organization_id,
                )
            elif request.scope == CacheInvalidationScope.COMPONENT:
                if request.component_type:
                    keys_invalidated = await self._invalidate_component_type(
                        request.tenant_id,
                        request.organization_id,
                        request.component_type,
                    )
            elif request.scope == CacheInvalidationScope.SINGLE_KEY:
                keys_invalidated = await self._invalidate_single_key(request.component_id)
            elif request.scope == CacheInvalidationScope.PARTIAL:
                keys_invalidated = await self._partial_flush(
                    request.tenant_id,
                    request.organization_id,
                )

            request.processed = True
            request.keys_invalidated = keys_invalidated
            logger.info(
                "cache_invalidation_completed",
                keys_invalidated=keys_invalidated,
                event_name=evt_name,
            )
        except Exception as e:
            logger.error(
                "cache_invalidation_failed",
                event_name=evt_name,
                error=str(e),
            )

        return request

    async def invalidate_metadata_update(
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
        count = await self._coordinator.invalidate_pattern(pattern)

        canonical_pattern = self._key_builder.build_pattern(
            CacheComponentType.CANONICAL,
            tenant_id=tenant_id,
            organization_id=organization_id,
            component_id=metadata_id,
        )
        count += await self._coordinator.invalidate_pattern(canonical_pattern)
        return count

    async def invalidate_graph_rebuild(
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

    async def invalidate_documentation(
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

    async def invalidate_search_index(
        self,
        *,
        tenant_id: str = "",
        organization_id: str = "",
    ) -> int:
        search_pattern = self._key_builder.build_pattern(
            CacheComponentType.SEARCH,
            tenant_id=tenant_id,
            organization_id=organization_id,
        )
        auto_pattern = self._key_builder.build_pattern(
            CacheComponentType.AUTOCOMPLETE,
            tenant_id=tenant_id,
            organization_id=organization_id,
        )
        count = await self._coordinator.invalidate_pattern(search_pattern)
        count += await self._coordinator.invalidate_pattern(auto_pattern)
        return count

    async def invalidate_organization(
        self,
        organization_id: str,
        *,
        tenant_id: str = "",
    ) -> int:
        pattern = self._key_builder.build_pattern(
            tenant_id=tenant_id,
            organization_id=organization_id,
        )
        return await self._coordinator.invalidate_pattern(pattern)

    async def invalidate_permission_change(
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

    async def invalidate_settings(
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

    async def invalidate_connection(
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

    async def full_flush(self) -> int:
        request = CacheInvalidationRequest(
            event=CacheInvalidationEvent.MANUAL_FLUSH,
            scope=CacheInvalidationScope.FULL,
            reason="manual_full_flush",
        )
        result = await self.invalidate(request)
        return result.keys_invalidated

    async def _full_flush(self) -> int:
        pattern = self._key_builder.build_pattern()
        return await self._coordinator.invalidate_pattern(pattern)

    async def _invalidate_tenant(self, tenant_id: str) -> int:
        pattern = self._key_builder.build_pattern(tenant_id=tenant_id)
        return await self._coordinator.invalidate_pattern(pattern)

    async def _invalidate_organization(
        self,
        tenant_id: str,
        organization_id: str,
    ) -> int:
        pattern = self._key_builder.build_pattern(
            tenant_id=tenant_id,
            organization_id=organization_id,
        )
        return await self._coordinator.invalidate_pattern(pattern)

    async def _invalidate_component_type(
        self,
        tenant_id: str,
        organization_id: str,
        component_type: CacheComponentType,
    ) -> int:
        pattern = self._key_builder.build_pattern(
            component_type,
            tenant_id=tenant_id,
            organization_id=organization_id,
        )
        return await self._coordinator.invalidate_pattern(pattern)

    async def _invalidate_single_key(self, key: str) -> int:
        await self._coordinator.invalidate(key)
        return 1

    async def _partial_flush(
        self,
        tenant_id: str,
        organization_id: str,
    ) -> int:
        return await self._invalidate_organization(organization_id, tenant_id=tenant_id)
