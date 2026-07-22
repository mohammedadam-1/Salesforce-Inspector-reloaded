from __future__ import annotations

from sfir_backend.domain.cache.models import CacheComponentType, CacheKey


class CacheKeyBuilder:
    def __init__(self, environment: str = "production") -> None:
        self._environment = environment

    def build(
        self,
        component_type: CacheComponentType | str,
        component_id: str = "",
        *,
        tenant_id: str = "",
        organization_id: str = "",
        version: str = "",
    ) -> str:
        return CacheKey(
            environment=self._environment,
            tenant_id=tenant_id,
            organization_id=organization_id,
            component_type=(
                component_type
                if isinstance(component_type, CacheComponentType)
                else CacheComponentType(component_type)
            ),
            component_id=component_id,
            version=version,
        ).to_string()

    def build_pattern(
        self,
        component_type: CacheComponentType | str | None = None,
        *,
        tenant_id: str = "",
        organization_id: str = "",
        component_id: str = "",
    ) -> str:
        env = self._environment
        tenant = tenant_id or "*"
        org = organization_id or "*"
        if isinstance(component_type, CacheComponentType):
            comp = component_type.value
        else:
            comp = component_type or "*"
        cid = component_id or "*"
        return f"{env}:{tenant}:{org}:{comp}:{cid}:*"

    def parse(self, key: str) -> CacheKey:
        return CacheKey.from_string(key)

    def metadata_key(
        self,
        metadata_id: str,
        *,
        tenant_id: str = "",
        organization_id: str = "",
        version: str = "",
    ) -> str:
        return self.build(
            CacheComponentType.METADATA,
            metadata_id,
            tenant_id=tenant_id,
            organization_id=organization_id,
            version=version,
        )

    def graph_key(
        self,
        organization_id: str,
        *,
        tenant_id: str = "",
        version: str = "",
    ) -> str:
        return self.build(
            CacheComponentType.GRAPH,
            organization_id,
            tenant_id=tenant_id,
            organization_id=organization_id,
            version=version,
        )

    def search_key(
        self,
        query_hash: str,
        *,
        tenant_id: str = "",
        organization_id: str = "",
    ) -> str:
        return self.build(
            CacheComponentType.SEARCH,
            query_hash,
            tenant_id=tenant_id,
            organization_id=organization_id,
        )

    def autocomplete_key(
        self,
        prefix: str,
        *,
        tenant_id: str = "",
        organization_id: str = "",
    ) -> str:
        return self.build(
            CacheComponentType.AUTOCOMPLETE,
            prefix.lower(),
            tenant_id=tenant_id,
            organization_id=organization_id,
        )

    def documentation_key(
        self,
        component_id: str,
        *,
        tenant_id: str = "",
        organization_id: str = "",
        version: str = "",
    ) -> str:
        return self.build(
            CacheComponentType.DOCUMENTATION,
            component_id,
            tenant_id=tenant_id,
            organization_id=organization_id,
            version=version,
        )

    def impact_key(
        self,
        component_id: str,
        *,
        tenant_id: str = "",
        organization_id: str = "",
    ) -> str:
        return self.build(
            CacheComponentType.IMPACT,
            component_id,
            tenant_id=tenant_id,
            organization_id=organization_id,
        )

    def settings_key(
        self,
        organization_id: str,
        *,
        tenant_id: str = "",
    ) -> str:
        return self.build(
            CacheComponentType.SETTINGS,
            organization_id,
            tenant_id=tenant_id,
            organization_id=organization_id,
        )

    def connection_status_key(
        self,
        connection_id: str,
        *,
        tenant_id: str = "",
        organization_id: str = "",
    ) -> str:
        return self.build(
            CacheComponentType.CONNECTION_STATUS,
            connection_id,
            tenant_id=tenant_id,
            organization_id=organization_id,
        )

    def permissions_key(
        self,
        user_id: str,
        organization_id: str,
        *,
        tenant_id: str = "",
    ) -> str:
        return self.build(
            CacheComponentType.PERMISSIONS,
            f"{user_id}:{organization_id}",
            tenant_id=tenant_id,
            organization_id=organization_id,
        )

    def rate_limit_key(
        self,
        identifier: str,
        *,
        tenant_id: str = "",
        organization_id: str = "",
    ) -> str:
        return self.build(
            CacheComponentType.RATE_LIMIT,
            identifier,
            tenant_id=tenant_id,
            organization_id=organization_id,
        )

    def feature_flag_key(
        self,
        flag_name: str,
        *,
        tenant_id: str = "",
        organization_id: str = "",
    ) -> str:
        return self.build(
            CacheComponentType.FEATURE_FLAGS,
            flag_name,
            tenant_id=tenant_id,
            organization_id=organization_id,
        )
