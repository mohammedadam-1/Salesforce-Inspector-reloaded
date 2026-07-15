from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sfir_backend.domain.cache.models import (
    CacheComponentType,
    CacheEntry,
    CacheHealthStatus,
    CacheInvalidationEvent,
    CacheInvalidationRequest,
    CacheInvalidationScope,
    CacheKey,
    CacheMetrics,
    CachePolicy,
    CacheStrategy,
)


class TestCacheStrategy:
    def test_values(self) -> None:
        assert CacheStrategy.ASIDE == "aside"
        assert CacheStrategy.READ_THROUGH == "read_through"
        assert CacheStrategy.WRITE_THROUGH == "write_through"
        assert CacheStrategy.WRITE_AROUND == "write_around"
        assert CacheStrategy.REFRESH_AHEAD == "refresh_ahead"


class TestCacheComponentType:
    def test_values(self) -> None:
        assert CacheComponentType.METADATA == "metadata"
        assert CacheComponentType.GRAPH == "graph"
        assert CacheComponentType.SEARCH == "search"
        assert CacheComponentType.DOCUMENTATION == "documentation"
        assert CacheComponentType.RATE_LIMIT == "rate_limit"


class TestCacheKey:
    def test_defaults(self) -> None:
        k = CacheKey()
        assert k.environment == "production"
        assert k.component_type == CacheComponentType.CONFIGURATION

    def test_to_string(self) -> None:
        k = CacheKey(
            tenant_id="tenant-1",
            organization_id="org-1",
            component_type=CacheComponentType.METADATA,
            component_id="meta-1",
            version="v1",
            environment="testing",
        )
        s = k.to_string()
        assert s == "testing:tenant-1:org-1:metadata:meta-1:v1"

    def test_to_string_empty_parts_use_underscore(self) -> None:
        k = CacheKey(
            component_type=CacheComponentType.GRAPH,
            component_id="graph-1",
        )
        s = k.to_string()
        assert s == "production:_:_:graph:graph-1:_"

    def test_from_string(self) -> None:
        k = CacheKey.from_string("testing:tenant-1:org-1:metadata:meta-1:v1")
        assert k.environment == "testing"
        assert k.tenant_id == "tenant-1"
        assert k.organization_id == "org-1"
        assert k.component_type == CacheComponentType.METADATA
        assert k.component_id == "meta-1"
        assert k.version == "v1"

    def test_from_string_with_underscore_defaults(self) -> None:
        k = CacheKey.from_string("production:_:_:graph:graph-1:_")
        assert k.environment == "production"
        assert k.tenant_id == ""
        assert k.organization_id == ""
        assert k.component_type == CacheComponentType.GRAPH
        assert k.component_id == "graph-1"
        assert k.version == ""

    def test_round_trip(self) -> None:
        original = CacheKey(
            tenant_id="t1",
            organization_id="o1",
            component_type=CacheComponentType.SEARCH,
            component_id="q1",
            version="v2",
            environment="staging",
        )
        restored = CacheKey.from_string(original.to_string())
        assert restored.model_dump() == original.model_dump()


class TestCacheEntry:
    def test_defaults(self) -> None:
        e = CacheEntry()
        assert e.key == ""
        assert e.value is None
        assert e.ttl_seconds == 300
        assert e.component_type == CacheComponentType.CONFIGURATION
        assert e.stale is False

    def test_is_expired_no_expiry(self) -> None:
        e = CacheEntry()
        assert e.is_expired() is False

    def test_is_expired_in_future(self) -> None:
        e = CacheEntry(
            expires_at=datetime.now(tz=UTC) + timedelta(hours=1),
        )
        assert e.is_expired() is False

    def test_is_expired_in_past(self) -> None:
        e = CacheEntry(
            expires_at=datetime.now(tz=UTC) - timedelta(seconds=1),
        )
        assert e.is_expired() is True

    def test_time_to_live_no_expiry(self) -> None:
        e = CacheEntry()
        assert e.time_to_live() == float("inf")

    def test_time_to_live_positive(self) -> None:
        e = CacheEntry(
            expires_at=datetime.now(tz=UTC) + timedelta(seconds=60),
        )
        ttl = e.time_to_live()
        assert 55 <= ttl <= 60

    def test_time_to_live_expired(self) -> None:
        e = CacheEntry(
            expires_at=datetime.now(tz=UTC) - timedelta(seconds=10),
        )
        assert e.time_to_live() == 0.0

    def test_with_values(self) -> None:
        e = CacheEntry(
            key="test:key",
            value={"data": 123},
            ttl_seconds=600,
            component_type=CacheComponentType.METADATA,
            version="v1",
        )
        assert e.key == "test:key"
        assert e.value["data"] == 123
        assert e.ttl_seconds == 600
        assert e.component_type == CacheComponentType.METADATA
        assert e.version == "v1"


class TestCachePolicy:
    def test_defaults(self) -> None:
        p = CachePolicy()
        assert p.strategy == CacheStrategy.ASIDE
        assert p.ttl_seconds == 300
        assert p.refresh_ahead_ttl_seconds == 60
        assert p.cache_null_values is False
        assert p.compress is False
        assert p.versioned is True

    def test_with_values(self) -> None:
        p = CachePolicy(
            strategy=CacheStrategy.WRITE_THROUGH,
            ttl_seconds=600,
            invalidation_events=[CacheInvalidationEvent.METADATA_UPDATE],
            cache_null_values=True,
        )
        assert p.strategy == CacheStrategy.WRITE_THROUGH
        assert p.ttl_seconds == 600
        assert CacheInvalidationEvent.METADATA_UPDATE in p.invalidation_events
        assert p.cache_null_values is True


class TestCacheMetrics:
    def test_defaults(self) -> None:
        m = CacheMetrics()
        assert m.hits == 0
        assert m.misses == 0
        assert m.hit_ratio == 0.0
        assert m.total_operations == 0
        assert m.connection_errors == 0

    def test_with_values(self) -> None:
        m = CacheMetrics(
            hits=90,
            misses=10,
            hit_ratio=0.9,
            total_operations=100,
            average_latency_ms=5.0,
            evictions=5,
        )
        assert m.hits == 90
        assert m.misses == 10
        assert m.hit_ratio == 0.9
        assert m.average_latency_ms == 5.0


class TestCacheHealthStatus:
    def test_defaults(self) -> None:
        h = CacheHealthStatus()
        assert h.healthy is True
        assert h.connected is False
        assert h.ping_latency_ms == 0.0
        assert h.total_errors == 0

    def test_with_values(self) -> None:
        h = CacheHealthStatus(
            healthy=False,
            connected=True,
            ping_latency_ms=150.0,
            memory_used_bytes=1_000_000,
            connected_clients=5,
            uptime_seconds=3600,
        )
        assert h.healthy is False
        assert h.connected is True
        assert h.ping_latency_ms == 150.0
        assert h.memory_used_bytes == 1_000_000


class TestCacheInvalidationEvent:
    def test_values(self) -> None:
        assert CacheInvalidationEvent.METADATA_UPDATE == "metadata_update"
        assert CacheInvalidationEvent.GRAPH_REBUILD == "graph_rebuild"
        assert CacheInvalidationEvent.MANUAL_FLUSH == "manual_flush"


class TestCacheInvalidationScope:
    def test_values(self) -> None:
        assert CacheInvalidationScope.FULL == "full"
        assert CacheInvalidationScope.PARTIAL == "partial"
        assert CacheInvalidationScope.TENANT == "tenant"
        assert CacheInvalidationScope.ORGANIZATION == "organization"
        assert CacheInvalidationScope.COMPONENT == "component"


class TestCacheInvalidationRequest:
    def test_defaults(self) -> None:
        r = CacheInvalidationRequest()
        assert r.event == CacheInvalidationEvent.MANUAL_FLUSH
        assert r.scope == CacheInvalidationScope.FULL
        assert r.reason == ""
        assert r.processed is False
        assert r.keys_invalidated == 0

    def test_with_values(self) -> None:
        r = CacheInvalidationRequest(
            event=CacheInvalidationEvent.METADATA_UPDATE,
            scope=CacheInvalidationScope.COMPONENT,
            component_type=CacheComponentType.METADATA,
            component_id="meta-1",
            reason="metadata updated",
        )
        assert r.event == CacheInvalidationEvent.METADATA_UPDATE
        assert r.scope == CacheInvalidationScope.COMPONENT
        assert r.component_type == CacheComponentType.METADATA
        assert r.component_id == "meta-1"
        assert r.reason == "metadata updated"

    def test_processed_updates(self) -> None:
        r = CacheInvalidationRequest()
        assert r.processed is False
        r.processed = True
        assert r.processed is True
