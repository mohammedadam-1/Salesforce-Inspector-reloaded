from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import fakeredis
import pytest

from sfir_backend.domain.cache.models import (
    CacheComponentType,
    CacheInvalidationEvent,
    CacheInvalidationRequest,
    CacheInvalidationScope,
    CachePolicy,
    CacheStrategy,
)
from sfir_backend.infrastructure.cache.coordinator import CacheCoordinator
from sfir_backend.infrastructure.cache.health_monitor import CacheHealthMonitor
from sfir_backend.infrastructure.cache.invalidation import CacheInvalidationManager
from sfir_backend.infrastructure.cache.key_builder import CacheKeyBuilder
from sfir_backend.infrastructure.cache.manager import CacheManager
from sfir_backend.infrastructure.cache.metrics import CacheMetricsCollector
from sfir_backend.infrastructure.cache.redis_cache import RedisCache
from sfir_backend.infrastructure.cache.serializer import CacheSerializer
from sfir_backend.infrastructure.cache.tenant_cache import TenantAwareCache


@pytest.fixture
def fake_redis() -> Any:
    server = fakeredis.FakeServer()
    return fakeredis.FakeAsyncRedis(server=server)


@pytest.fixture
def redis_cache(fake_redis: Any) -> RedisCache:
    return RedisCache(fake_redis)


@pytest.fixture
def metrics() -> CacheMetricsCollector:
    return CacheMetricsCollector()


@pytest.fixture
def serializer() -> CacheSerializer:
    return CacheSerializer()


@pytest.fixture
def key_builder() -> CacheKeyBuilder:
    return CacheKeyBuilder(environment="testing")


@pytest.fixture
def cache_manager(
    redis_cache: RedisCache, metrics: CacheMetricsCollector, serializer: CacheSerializer,
) -> CacheManager:
    return CacheManager(cache=redis_cache, metrics=metrics, serializer=serializer)


@pytest.fixture
def coordinator(cache_manager: CacheManager) -> CacheCoordinator:
    return CacheCoordinator(cache_manager)


@pytest.fixture
def invalidation(
    coordinator: CacheCoordinator, key_builder: CacheKeyBuilder,
) -> CacheInvalidationManager:
    return CacheInvalidationManager(coordinator, key_builder)


# --- Serializer Tests ---

class TestCacheSerializer:
    def test_serialize_deserialize_dict(self) -> None:
        s = CacheSerializer()
        data = {"key": "value", "number": 42, "nested": {"a": 1}}
        serialized = s.serialize(data)
        deserialized = s.deserialize(serialized)
        assert deserialized == data

    def test_serialize_deserialize_list(self) -> None:
        s = CacheSerializer()
        data = [1, 2, 3, "four"]
        serialized = s.serialize(data)
        assert s.deserialize(serialized) == data

    def test_serialize_deserialize_none(self) -> None:
        s = CacheSerializer()
        serialized = s.serialize(None)
        assert s.deserialize(serialized) is None

    def test_serialize_datetime(self) -> None:
        s = CacheSerializer()
        dt = datetime(2024, 1, 15, 12, 30, 0, tzinfo=UTC)
        data = {"timestamp": dt}
        serialized = s.serialize(data)
        result = s.deserialize(serialized)
        assert result["timestamp"] == "2024-01-15T12:30:00+00:00"

    def test_deserialize_bytes_string(self) -> None:
        s = CacheSerializer()
        result = s.deserialize(b'"hello"')
        assert result == "hello"


# --- CacheKeyBuilder Tests ---

class TestCacheKeyBuilder:
    def test_build_default(self) -> None:
        b = CacheKeyBuilder("testing")
        key = b.build(CacheComponentType.METADATA, "meta-1")
        assert key == "testing:_:_:metadata:meta-1:_"

    def test_build_full(self) -> None:
        b = CacheKeyBuilder("testing")
        key = b.build(
            CacheComponentType.METADATA,
            "meta-1",
            tenant_id="tenant-1",
            organization_id="org-1",
            version="v1",
        )
        assert key == "testing:tenant-1:org-1:metadata:meta-1:v1"

    def test_build_pattern_component(self) -> None:
        b = CacheKeyBuilder("testing")
        pattern = b.build_pattern(
            CacheComponentType.GRAPH,
            tenant_id="tenant-1",
            organization_id="org-1",
        )
        assert pattern == "testing:tenant-1:org-1:graph:*:*"

    def test_build_pattern_wildcard(self) -> None:
        b = CacheKeyBuilder("testing")
        pattern = b.build_pattern()
        assert pattern == "testing:*:*:*:*:*"

    def test_metadata_key(self) -> None:
        b = CacheKeyBuilder("testing")
        key = b.metadata_key("meta-1", tenant_id="t1", organization_id="o1", version="v1")
        assert key == "testing:t1:o1:metadata:meta-1:v1"

    def test_graph_key(self) -> None:
        b = CacheKeyBuilder("testing")
        key = b.graph_key("org-1", tenant_id="t1", version="v2")
        assert key == "testing:t1:org-1:graph:org-1:v2"

    def test_search_key(self) -> None:
        b = CacheKeyBuilder("testing")
        key = b.search_key("abc123", tenant_id="t1", organization_id="o1")
        assert key == "testing:t1:o1:search:abc123:_"

    def test_autocomplete_key_lowercase(self) -> None:
        b = CacheKeyBuilder("testing")
        key = b.autocomplete_key("Hello", tenant_id="t1", organization_id="o1")
        assert "hello" in key

    def test_documentation_key(self) -> None:
        b = CacheKeyBuilder("testing")
        key = b.documentation_key("doc-1", tenant_id="t1", organization_id="o1")
        assert key == "testing:t1:o1:documentation:doc-1:_"

    def test_impact_key(self) -> None:
        b = CacheKeyBuilder("testing")
        key = b.impact_key("comp-1", tenant_id="t1", organization_id="o1")
        assert key == "testing:t1:o1:impact:comp-1:_"

    def test_settings_key(self) -> None:
        b = CacheKeyBuilder("testing")
        key = b.settings_key("org-1", tenant_id="t1")
        assert key == "testing:t1:org-1:settings:org-1:_"

    def test_connection_status_key(self) -> None:
        b = CacheKeyBuilder("testing")
        key = b.connection_status_key("conn-1", tenant_id="t1", organization_id="o1")
        assert key == "testing:t1:o1:connection_status:conn-1:_"

    def test_permissions_key(self) -> None:
        b = CacheKeyBuilder("testing")
        key = b.permissions_key("user-1", "org-1", tenant_id="t1")
        expected = "testing:t1:org-1:permissions:user-1:org-1:_"
        assert key == expected

    def test_rate_limit_key(self) -> None:
        b = CacheKeyBuilder("testing")
        key = b.rate_limit_key("user-1:api", tenant_id="t1")
        assert key == "testing:t1:_:rate_limit:user-1:api:_"

    def test_feature_flag_key(self) -> None:
        b = CacheKeyBuilder("testing")
        key = b.feature_flag_key("dark-mode", tenant_id="t1", organization_id="o1")
        assert key == "testing:t1:o1:feature_flags:dark-mode:_"


# --- RedisCache Tests (via fakeredis) ---

class TestRedisCache:
    async def test_get_missing(self, redis_cache: RedisCache) -> None:
        result = await redis_cache.get("nonexistent")
        assert result is None

    async def test_set_and_get(self, redis_cache: RedisCache) -> None:
        await redis_cache.set("key1", {"data": 123}, ttl_seconds=60)
        result = await redis_cache.get("key1")
        assert result == {"data": 123}

    async def test_set_and_get_string(self, redis_cache: RedisCache) -> None:
        await redis_cache.set("str_key", "hello", ttl_seconds=60)
        result = await redis_cache.get("str_key")
        assert result == "hello"

    async def test_set_and_get_list(self, redis_cache: RedisCache) -> None:
        await redis_cache.set("list_key", [1, 2, 3], ttl_seconds=60)
        result = await redis_cache.get("list_key")
        assert result == [1, 2, 3]

    async def test_delete(self, redis_cache: RedisCache) -> None:
        await redis_cache.set("del_key", "value", ttl_seconds=60)
        assert await redis_cache.get("del_key") == "value"
        await redis_cache.delete("del_key")
        assert await redis_cache.get("del_key") is None

    async def test_exists_true(self, redis_cache: RedisCache) -> None:
        await redis_cache.set("exists_key", "value", ttl_seconds=60)
        assert await redis_cache.exists("exists_key") is True

    async def test_exists_false(self, redis_cache: RedisCache) -> None:
        assert await redis_cache.exists("nonexistent") is False

    async def test_increment(self, redis_cache: RedisCache) -> None:
        result = await redis_cache.increment("counter", 1)
        assert result == 1
        result = await redis_cache.increment("counter", 5)
        assert result == 6

    async def test_invalidate_pattern(self, redis_cache: RedisCache) -> None:
        await redis_cache.set("testing:t1:o1:metadata:a:_", "a", ttl_seconds=60)
        await redis_cache.set("testing:t1:o1:metadata:b:_", "b", ttl_seconds=60)
        await redis_cache.set("testing:t1:o1:graph:c:_", "c", ttl_seconds=60)

        deleted = await redis_cache.invalidate_pattern("testing:t1:o1:metadata:*")
        assert deleted == 2
        assert await redis_cache.get("testing:t1:o1:metadata:a:_") is None
        assert await redis_cache.get("testing:t1:o1:metadata:b:_") is None
        assert await redis_cache.get("testing:t1:o1:graph:c:_") == "c"

    async def test_ttl_expiry(self, redis_cache: RedisCache, fake_redis: Any) -> None:
        await redis_cache.set("ttl_key", "value", ttl_seconds=1)
        assert await redis_cache.get("ttl_key") == "value"
        ttl = await fake_redis.ttl("ttl_key")
        assert ttl > 0


# --- CacheManager Tests ---

class TestCacheManager:
    async def test_get_missing(self, cache_manager: CacheManager) -> None:
        result = await cache_manager.get("nonexistent")
        assert result is None

    async def test_set_and_get(self, cache_manager: CacheManager) -> None:
        await cache_manager.set("key", {"value": 42})
        result = await cache_manager.get("key")
        assert result == {"value": 42}

    async def test_get_or_load_cache_hit(self, cache_manager: CacheManager) -> None:
        await cache_manager.set("hit_key", "cached_value")
        loader = AsyncMock(return_value="loaded_value")
        result = await cache_manager.get_or_load("hit_key", loader)
        assert result == "cached_value"
        loader.assert_not_called()

    async def test_get_or_load_cache_miss(self, cache_manager: CacheManager) -> None:
        loader = AsyncMock(return_value="loaded_value")
        result = await cache_manager.get_or_load("miss_key", loader, ttl_seconds=60)
        assert result == "loaded_value"
        loader.assert_called_once()
        cached = await cache_manager.get("miss_key")
        assert cached == "loaded_value"

    async def test_get_or_load_loader_returns_none(self, cache_manager: CacheManager) -> None:
        loader = AsyncMock(return_value=None)
        result = await cache_manager.get_or_load("null_key", loader)
        assert result is None
        cached = await cache_manager.get("null_key")
        assert cached is None

    async def test_get_or_load_loader_returns_none_with_policy(
        self, cache_manager: CacheManager,
    ) -> None:
        loader = AsyncMock(return_value=None)
        policy = CachePolicy(cache_null_values=True)
        result = await cache_manager.get_or_load("null_key2", loader, policy=policy)
        assert result is None
        cached = await cache_manager.get("null_key2")
        assert cached is None

    async def test_invalidate(self, cache_manager: CacheManager) -> None:
        await cache_manager.set("inv_key", "value")
        assert await cache_manager.get("inv_key") == "value"
        await cache_manager.invalidate("inv_key")
        assert await cache_manager.get("inv_key") is None

    async def test_invalidate_pattern(
        self, cache_manager: CacheManager, key_builder: CacheKeyBuilder,
    ) -> None:
        k1 = key_builder.metadata_key("a", tenant_id="t1", organization_id="o1")
        k2 = key_builder.metadata_key("b", tenant_id="t1", organization_id="o1")
        await cache_manager.set(k1, "a")
        await cache_manager.set(k2, "b")

        pattern = key_builder.build_pattern(
            CacheComponentType.METADATA,
            tenant_id="t1",
            organization_id="o1",
        )
        count = await cache_manager.invalidate_pattern(pattern)
        assert count == 2
        assert await cache_manager.get(k1) is None
        assert await cache_manager.get(k2) is None

    async def test_exists(self, cache_manager: CacheManager) -> None:
        await cache_manager.set("exists_test", "value")
        assert await cache_manager.exists("exists_test") is True
        await cache_manager.invalidate("exists_test")
        assert await cache_manager.exists("exists_test") is False

    async def test_increment(self, cache_manager: CacheManager) -> None:
        assert await cache_manager.increment("inc_key") == 1
        assert await cache_manager.increment("inc_key", 5) == 6


# --- CacheCoordinator Tests ---

class TestCacheCoordinator:
    async def test_read_cache_hit(self, coordinator: CacheCoordinator) -> None:
        await coordinator.manager.set("coord_key", "cached")
        loader = AsyncMock(return_value="loaded")
        result = await coordinator.read("coord_key", loader)
        assert result == "cached"
        loader.assert_not_called()

    async def test_read_cache_miss(self, coordinator: CacheCoordinator) -> None:
        loader = AsyncMock(return_value="loaded")
        result = await coordinator.read("coord_miss", loader)
        assert result == "loaded"
        loader.assert_called_once()

    async def test_write_default_strategy(self, coordinator: CacheCoordinator) -> None:
        await coordinator.write("write_key", "written")
        result = await coordinator.manager.get("write_key")
        assert result == "written"

    async def test_write_through(self, coordinator: CacheCoordinator) -> None:
        db_writer = AsyncMock()
        policy = CachePolicy(strategy=CacheStrategy.WRITE_THROUGH)
        await coordinator.write("wt_key", "cache_value", policy=policy, db_writer=db_writer)
        assert await coordinator.manager.get("wt_key") == "cache_value"
        db_writer.assert_called_once()

    async def test_write_through_rollback_on_db_failure(
        self, coordinator: CacheCoordinator,
    ) -> None:
        db_writer = AsyncMock(side_effect=RuntimeError("db error"))
        policy = CachePolicy(strategy=CacheStrategy.WRITE_THROUGH)
        with pytest.raises(RuntimeError):
            await coordinator.write("rollback_key", "value", policy=policy, db_writer=db_writer)
        assert await coordinator.manager.get("rollback_key") is None

    async def test_write_around(self, coordinator: CacheCoordinator) -> None:
        await coordinator.manager.set("wa_key", "old_value")
        db_writer = AsyncMock()
        policy = CachePolicy(strategy=CacheStrategy.WRITE_AROUND)
        await coordinator.write("wa_key", "new_value", policy=policy, db_writer=db_writer)
        db_writer.assert_called_once()
        assert await coordinator.manager.get("wa_key") is None

    async def test_invalidate(self, coordinator: CacheCoordinator) -> None:
        await coordinator.manager.set("inv_coord", "value")
        await coordinator.invalidate("inv_coord")
        assert await coordinator.manager.get("inv_coord") is None

    async def test_invalidate_pattern(
        self, coordinator: CacheCoordinator, key_builder: CacheKeyBuilder,
    ) -> None:
        k1 = key_builder.metadata_key("a", tenant_id="t1", organization_id="o1")
        k2 = key_builder.metadata_key("b", tenant_id="t1", organization_id="o1")
        await coordinator.manager.set(k1, "a")
        await coordinator.manager.set(k2, "b")
        pattern = key_builder.build_pattern(
            CacheComponentType.METADATA, tenant_id="t1", organization_id="o1",
        )
        count = await coordinator.invalidate_pattern(pattern)
        assert count == 2


# --- CacheInvalidationManager Tests ---

class TestCacheInvalidationManager:
    async def test_invalidate_full_flush(
        self,
        invalidation: CacheInvalidationManager,
        key_builder: CacheKeyBuilder,
        coordinator: CacheCoordinator,
    ) -> None:
        k1 = key_builder.metadata_key("a", tenant_id="t1", organization_id="o1")
        k2 = key_builder.graph_key("o1", tenant_id="t1")
        await coordinator.manager.set(k1, "a")
        await coordinator.manager.set(k2, "b")

        request = CacheInvalidationRequest(
            event=CacheInvalidationEvent.MANUAL_FLUSH,
            scope=CacheInvalidationScope.FULL,
        )
        result = await invalidation.invalidate(request)
        assert result.processed is True
        assert result.keys_invalidated >= 2
        assert await coordinator.manager.get(k1) is None
        assert await coordinator.manager.get(k2) is None

    async def test_invalidate_component_type(
        self,
        invalidation: CacheInvalidationManager,
        key_builder: CacheKeyBuilder,
        coordinator: CacheCoordinator,
    ) -> None:
        k1 = key_builder.metadata_key("a", tenant_id="t1", organization_id="o1")
        k2 = key_builder.graph_key("o1", tenant_id="t1")
        await coordinator.manager.set(k1, "a")
        await coordinator.manager.set(k2, "b")

        request = CacheInvalidationRequest(
            event=CacheInvalidationEvent.METADATA_UPDATE,
            scope=CacheInvalidationScope.COMPONENT,
            component_type=CacheComponentType.METADATA,
            tenant_id="t1",
            organization_id="o1",
        )
        result = await invalidation.invalidate(request)
        assert result.processed is True
        assert result.keys_invalidated >= 1
        assert await coordinator.manager.get(k1) is None
        assert await coordinator.manager.get(k2) == "b"

    async def test_invalidate_metadata_update(
        self,
        invalidation: CacheInvalidationManager,
        key_builder: CacheKeyBuilder,
        coordinator: CacheCoordinator,
    ) -> None:
        k1 = key_builder.metadata_key("m1", tenant_id="t1", organization_id="o1")
        k2 = key_builder.metadata_key("m2", tenant_id="t1", organization_id="o1")
        await coordinator.manager.set(k1, "a")
        await coordinator.manager.set(k2, "b")

        count = await invalidation.invalidate_metadata_update(
            "m1", tenant_id="t1", organization_id="o1",
        )
        assert count >= 1
        assert await coordinator.manager.get(k1) is None
        assert await coordinator.manager.get(k2) == "b"

    async def test_invalidate_graph_rebuild(
        self,
        invalidation: CacheInvalidationManager,
        key_builder: CacheKeyBuilder,
        coordinator: CacheCoordinator,
    ) -> None:
        k = key_builder.graph_key("o1", tenant_id="t1")
        await coordinator.manager.set(k, "graph_data")
        count = await invalidation.invalidate_graph_rebuild(tenant_id="t1", organization_id="o1")
        assert count >= 1
        assert await coordinator.manager.get(k) is None

    async def test_invalidate_documentation(
        self,
        invalidation: CacheInvalidationManager,
        key_builder: CacheKeyBuilder,
        coordinator: CacheCoordinator,
    ) -> None:
        k = key_builder.documentation_key("doc-1", tenant_id="t1", organization_id="o1")
        await coordinator.manager.set(k, "doc")
        count = await invalidation.invalidate_documentation(
            "doc-1", tenant_id="t1", organization_id="o1",
        )
        assert count >= 1
        assert await coordinator.manager.get(k) is None

    async def test_invalidate_search_index(
        self,
        invalidation: CacheInvalidationManager,
        key_builder: CacheKeyBuilder,
        coordinator: CacheCoordinator,
    ) -> None:
        sk = key_builder.search_key("q1", tenant_id="t1", organization_id="o1")
        ak = key_builder.autocomplete_key("pre", tenant_id="t1", organization_id="o1")
        await coordinator.manager.set(sk, "results")
        await coordinator.manager.set(ak, "suggestions")
        count = await invalidation.invalidate_search_index(tenant_id="t1", organization_id="o1")
        assert count >= 2

    async def test_invalidate_organization(
        self,
        invalidation: CacheInvalidationManager,
        key_builder: CacheKeyBuilder,
        coordinator: CacheCoordinator,
    ) -> None:
        k = key_builder.metadata_key("m1", tenant_id="t1", organization_id="o1")
        await coordinator.manager.set(k, "data")
        k2 = key_builder.metadata_key("m2", tenant_id="t1", organization_id="o2")
        await coordinator.manager.set(k2, "other")
        count = await invalidation.invalidate_organization("o1", tenant_id="t1")
        assert count >= 1
        assert await coordinator.manager.get(k) is None
        assert await coordinator.manager.get(k2) == "other"

    async def test_invalidate_permission_change(
        self,
        invalidation: CacheInvalidationManager,
        key_builder: CacheKeyBuilder,
        coordinator: CacheCoordinator,
    ) -> None:
        k = key_builder.permissions_key("u1", "o1", tenant_id="t1")
        await coordinator.manager.set(k, "perms")
        count = await invalidation.invalidate_permission_change("u1", "o1", tenant_id="t1")
        assert count >= 1
        assert await coordinator.manager.get(k) is None

    async def test_full_flush(
        self,
        invalidation: CacheInvalidationManager,
        key_builder: CacheKeyBuilder,
        coordinator: CacheCoordinator,
    ) -> None:
        k = key_builder.metadata_key("m1", tenant_id="t1", organization_id="o1")
        await coordinator.manager.set(k, "data")
        count = await invalidation.full_flush()
        assert count >= 1
        assert await coordinator.manager.get(k) is None


# --- CacheMetricsCollector Tests ---

class TestCacheMetricsCollector:
    def test_record_hit(self) -> None:
        m = CacheMetricsCollector()
        m.record_hit(latency_ms=5.0)
        snapshot = m.snapshot()
        assert snapshot.hits == 1
        assert snapshot.misses == 0
        assert snapshot.hit_ratio == 1.0

    def test_record_miss(self) -> None:
        m = CacheMetricsCollector()
        m.record_miss(latency_ms=10.0)
        snapshot = m.snapshot()
        assert snapshot.misses == 1
        assert snapshot.hit_ratio == 0.0

    def test_hit_ratio_mixed(self) -> None:
        m = CacheMetricsCollector()
        m.record_hit()
        m.record_hit()
        m.record_hit()
        m.record_miss()
        snapshot = m.snapshot()
        assert snapshot.hits == 3
        assert snapshot.misses == 1
        assert snapshot.hit_ratio == 0.75

    def test_record_write(self) -> None:
        m = CacheMetricsCollector()
        m.record_write(latency_ms=2.0)
        assert m._writes == 1

    def test_record_invalidation(self) -> None:
        m = CacheMetricsCollector()
        m.record_invalidation(count=5)
        assert m._invalidations == 5

    def test_record_error(self) -> None:
        m = CacheMetricsCollector()
        m.record_error()
        assert m._errors == 1

    def test_average_latency(self) -> None:
        m = CacheMetricsCollector()
        m.record_hit(latency_ms=5.0)
        m.record_hit(latency_ms=15.0)
        snapshot = m.snapshot()
        assert snapshot.average_latency_ms == 10.0

    def test_reset(self) -> None:
        m = CacheMetricsCollector()
        m.record_hit()
        m.record_miss()
        m.record_error()
        m.reset()
        snapshot = m.snapshot()
        assert snapshot.hits == 0
        assert snapshot.misses == 0
        assert snapshot.connection_errors == 0

    def test_component_label(self) -> None:
        m = CacheMetricsCollector()
        m.component = "metadata"
        assert m.component == "metadata"


# --- TenantAwareCache Tests ---

class TestTenantAwareCache:
    async def test_get_set_component(self, cache_manager: CacheManager) -> None:
        tc = TenantAwareCache(cache_manager, tenant_id="t1", organization_id="o1")
        await tc.set_component(CacheComponentType.METADATA, "m1", {"data": 1})
        result = await tc.get_component(CacheComponentType.METADATA, "m1")
        assert result == {"data": 1}

    async def test_invalidate_component(self, cache_manager: CacheManager) -> None:
        tc = TenantAwareCache(cache_manager, tenant_id="t1", organization_id="o1")
        await tc.set_component(CacheComponentType.METADATA, "m1", "val1")
        await tc.set_component(CacheComponentType.GRAPH, "g1", "val2")
        await tc.invalidate_component(CacheComponentType.METADATA)
        assert await tc.get_component(CacheComponentType.METADATA, "m1") is None
        assert await tc.get_component(CacheComponentType.GRAPH, "g1") == "val2"

    async def test_invalidate_all(self, cache_manager: CacheManager) -> None:
        tc = TenantAwareCache(cache_manager, tenant_id="t1", organization_id="o1")
        await tc.set_component(CacheComponentType.METADATA, "m1", "val1")
        await tc.set_component(CacheComponentType.GRAPH, "g1", "val2")
        await tc.invalidate_all()
        assert await tc.get_component(CacheComponentType.METADATA, "m1") is None
        assert await tc.get_component(CacheComponentType.GRAPH, "g1") is None

    async def test_tenant_isolation(self, cache_manager: CacheManager) -> None:
        tc1 = TenantAwareCache(cache_manager, tenant_id="t1", organization_id="o1")
        tc2 = TenantAwareCache(cache_manager, tenant_id="t2", organization_id="o2")
        await tc1.set_component(CacheComponentType.METADATA, "m1", "t1_value")
        result = await tc2.get_component(CacheComponentType.METADATA, "m1")
        assert result is None


# --- CacheHealthMonitor Tests (with mock pool) ---

@pytest.fixture
def mock_pool() -> MagicMock:
    pool = MagicMock()
    pool.health_check = AsyncMock(return_value=True)
    pool.info = AsyncMock(
        return_value={
            "used_memory": 500000,
            "maxmemory": 1000000,
            "connected_clients": 3,
            "uptime_in_seconds": 3600,
        },
    )
    pool.memory_usage = AsyncMock(return_value=500000)
    return pool


class TestCacheHealthMonitor:
    async def test_healthy_status(self, mock_pool: MagicMock) -> None:
        monitor = CacheHealthMonitor(mock_pool, warning_threshold_ms=1000.0)
        status = await monitor.check_health()
        assert status.healthy is True
        assert status.connected is True
        assert status.memory_used_bytes == 500000
        assert status.connected_clients == 3

    async def test_unhealthy_on_ping_failure(self, mock_pool: MagicMock) -> None:
        mock_pool.health_check = AsyncMock(return_value=False)
        monitor = CacheHealthMonitor(mock_pool)
        status = await monitor.check_health()
        assert status.healthy is False
        assert status.connected is False

    async def test_unhealthy_on_exception(self, mock_pool: MagicMock) -> None:
        mock_pool.health_check = AsyncMock(side_effect=RuntimeError("connection failed"))
        monitor = CacheHealthMonitor(mock_pool)
        status = await monitor.check_health()
        assert status.healthy is False
        assert status.connected is False

    async def test_consecutive_failures(self, mock_pool: MagicMock) -> None:
        mock_pool.health_check = AsyncMock(return_value=False)
        monitor = CacheHealthMonitor(mock_pool, warning_threshold_ms=1000.0)
        assert monitor.should_circuit_break is False
        for _ in range(3):
            await monitor.check_health()
        assert monitor.consecutive_failures == 3
        assert monitor.should_circuit_break is True

    async def test_is_healthy_property_initial(self, mock_pool: MagicMock) -> None:
        monitor = CacheHealthMonitor(mock_pool)
        assert monitor.is_healthy is True

    async def test_is_healthy_after_check(self, mock_pool: MagicMock) -> None:
        monitor = CacheHealthMonitor(mock_pool, warning_threshold_ms=1000.0)
        await monitor.check_health()
        assert monitor.is_healthy is True

    async def test_is_degraded(self, mock_pool: MagicMock) -> None:
        mock_pool.health_check = AsyncMock(return_value=True)
        monitor = CacheHealthMonitor(
            mock_pool, warning_threshold_ms=0.0, critical_threshold_ms=1000.0,
        )
        assert monitor.is_degraded is False
        status = await monitor.check_health()
        assert status.healthy is True

    async def test_get_memory_usage(self, mock_pool: MagicMock) -> None:
        monitor = CacheHealthMonitor(mock_pool)
        memory = await monitor.get_memory_usage()
        assert memory == 500000
