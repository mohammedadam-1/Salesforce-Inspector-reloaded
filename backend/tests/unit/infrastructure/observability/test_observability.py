from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from sfir_backend.domain.observability.models import (
    Alert,
    AlertRule,
    AlertSeverity,
    AlertStatus,
    HealthCheckResult,
    HealthComponentStatus,
    HealthReport,
    LogLevel,
)
from sfir_backend.infrastructure.observability.alerting import AlertManager
from sfir_backend.infrastructure.observability.diagnostics import DiagnosticsService
from sfir_backend.infrastructure.observability.health import HealthCheckManager
from sfir_backend.infrastructure.observability.logging import LoggingManager
from sfir_backend.infrastructure.observability.metrics import MetricsCollector
from sfir_backend.infrastructure.observability.profiler import PerformanceProfiler
from sfir_backend.infrastructure.observability.telemetry import TelemetryCoordinator
from sfir_backend.infrastructure.observability.tracing import TracingManager

# ── LoggingManager Tests ────────────────────────────────

class TestLoggingManager:
    def test_get_logger(self) -> None:
        mgr = LoggingManager()
        logger = mgr.get_logger("test")
        assert logger is not None

    def test_bind_and_clear_context(self) -> None:
        mgr = LoggingManager()
        mgr.bind_context(correlation_id="test-123")
        mgr.clear_context()

    def test_to_log_event(self) -> None:
        mgr = LoggingManager()
        event_dict = {
            "event": "test_event",
            "level": "info",
            "correlation_id": "cid-1",
            "component": "test",
        }
        event = mgr.to_log_event(None, event_dict)  # type: ignore[arg-type]
        assert event.message == "test_event"
        assert event.level == LogLevel.INFO
        assert event.correlation_id == "cid-1"


# ── MetricsCollector Tests ─────────────────────────────

class TestMetricsCollector:
    def test_record_http_request(self) -> None:
        mc = MetricsCollector()
        mc.record_http_request(method="GET", endpoint="/test", status_code=200, duration=0.05)

    def test_record_db_query(self) -> None:
        mc = MetricsCollector()
        mc.record_db_query(operation="SELECT", duration=0.01)

    def test_record_db_error(self) -> None:
        mc = MetricsCollector()
        mc.record_db_error(operation="INSERT")

    def test_record_redis_operation(self) -> None:
        mc = MetricsCollector()
        mc.record_redis_operation(operation="get")

    def test_record_redis_error(self) -> None:
        mc = MetricsCollector()
        mc.record_redis_error()

    def test_record_salesforce_call(self) -> None:
        mc = MetricsCollector()
        mc.record_salesforce_call(method="GET", endpoint="/sobjects", status="200", duration=0.5)

    def test_record_auth_operation(self) -> None:
        mc = MetricsCollector()
        mc.record_auth_operation(operation="login", status="success", duration=0.1)

    def test_record_graph_operation(self) -> None:
        mc = MetricsCollector()
        mc.record_graph_operation(operation="build", status="success", duration=2.0)

    def test_record_search_operation(self) -> None:
        mc = MetricsCollector()
        mc.record_search_operation(operation="query", status="success", duration=0.05)

    def test_record_impact_operation(self) -> None:
        mc = MetricsCollector()
        mc.record_impact_operation(operation="analyze", status="success", duration=1.0)

    def test_record_doc_operation(self) -> None:
        mc = MetricsCollector()
        mc.record_doc_operation(operation="generate", status="success", duration=0.5)

    def test_set_db_connections(self) -> None:
        mc = MetricsCollector()
        mc.set_db_connections(active=10)

    def test_set_db_pool_size(self) -> None:
        mc = MetricsCollector()
        mc.set_db_pool_size(state="active", size=5)

    def test_set_redis_memory(self) -> None:
        mc = MetricsCollector()
        mc.set_redis_memory(bytes_=1024)

    def test_record_custom(self) -> None:
        mc = MetricsCollector()
        mc.record_custom("custom_metric", 42.0, labels={"key": "value"})

    def test_record_http_in_flight(self) -> None:
        mc = MetricsCollector()
        mc.record_http_in_flight(method="GET", delta=1)
        mc.record_http_in_flight(method="GET", delta=-1)


# ── TracingManager Tests ───────────────────────────────

class TestTracingManager:
    def test_init(self) -> None:
        tm = TracingManager()
        assert tm.tracer is not None

    def test_generate_ids(self) -> None:
        tm = TracingManager()
        trace_id = tm.generate_trace_id()
        span_id = tm.generate_span_id()
        assert trace_id is not None
        assert span_id is not None
        assert trace_id != span_id

    def test_current_span_no_trace(self) -> None:
        tm = TracingManager()
        span = tm.current_span()
        assert span is None


# ── HealthCheckManager Tests ───────────────────────────

class TestHealthCheckManager:
    @pytest.fixture
    def health_mgr(self) -> HealthCheckManager:
        return HealthCheckManager()

    async def test_check_application(self, health_mgr: HealthCheckManager) -> None:
        result = await health_mgr.check_application()
        assert result.component == "application"
        assert result.status == HealthComponentStatus.HEALTHY

    async def test_check_redis_not_configured(self, health_mgr: HealthCheckManager) -> None:
        result = await health_mgr.check_redis()
        assert result.status == HealthComponentStatus.NOT_CONFIGURED

    async def test_check_redis_healthy(self) -> None:
        mock_pool = MagicMock()
        mock_pool.health_check = AsyncMock(return_value=True)
        mock_pool.info = AsyncMock(return_value={
            "used_memory": 500000,
            "connected_clients": 3,
            "uptime_in_seconds": 3600,
            "redis_version": "7.2",
        })
        health_mgr = HealthCheckManager(redis_pool=mock_pool)
        result = await health_mgr.check_redis()
        assert result.status == HealthComponentStatus.HEALTHY
        assert result.details["redis_version"] == "7.2"

    async def test_check_redis_unhealthy(self) -> None:
        mock_pool = MagicMock()
        mock_pool.health_check = AsyncMock(return_value=False)
        health_mgr = HealthCheckManager(redis_pool=mock_pool)
        result = await health_mgr.check_redis()
        assert result.status == HealthComponentStatus.UNHEALTHY

    async def test_check_cache_not_configured(self, health_mgr: HealthCheckManager) -> None:
        result = await health_mgr.check_cache()
        assert result.status == HealthComponentStatus.NOT_CONFIGURED

    async def test_check_cache_healthy(self) -> None:
        mock_cache_health = MagicMock()
        mock_cache_health.check_health = AsyncMock()
        mock_cache_health.check_health.return_value.healthy = True
        mock_cache_health.check_health.return_value.ping_latency_ms = 2.0
        mock_cache_health.check_health.return_value.connected = True
        mock_cache_health.check_health.return_value.memory_used_bytes = 1000
        mock_cache_health.consecutive_failures = 0

        health_mgr = HealthCheckManager(cache_health=mock_cache_health)
        result = await health_mgr.check_cache()
        assert result.status == HealthComponentStatus.HEALTHY

    async def test_check_cache_degraded(self) -> None:
        mock_cache_health = MagicMock()
        mock_cache_health.check_health = AsyncMock()
        mock_cache_health.check_health.return_value.healthy = False
        mock_cache_health.check_health.return_value.ping_latency_ms = 200.0
        mock_cache_health.check_health.return_value.connected = True
        mock_cache_health.check_health.return_value.memory_used_bytes = 1000
        mock_cache_health.consecutive_failures = 2

        health_mgr = HealthCheckManager(cache_health=mock_cache_health)
        result = await health_mgr.check_cache()
        assert result.status == HealthComponentStatus.DEGRADED

    async def test_check_database_not_configured(self, health_mgr: HealthCheckManager) -> None:
        result = await health_mgr.check_database(db_check_fn=None)
        assert result.status == HealthComponentStatus.NOT_CONFIGURED

    async def test_check_database_healthy(self, health_mgr: HealthCheckManager) -> None:
        db_check = AsyncMock()
        result = await health_mgr.check_database(db_check_fn=db_check)
        assert result.status == HealthComponentStatus.HEALTHY
        assert result.latency_ms >= 0

    async def test_check_database_timeout(self, health_mgr: HealthCheckManager) -> None:
        async def timeout_fn() -> None:
            raise TimeoutError("query timed out")
        result = await health_mgr.check_database(db_check_fn=timeout_fn)
        assert result.status == HealthComponentStatus.DEGRADED

    async def test_check_database_failure(self, health_mgr: HealthCheckManager) -> None:
        async def failing_fn() -> None:
            raise RuntimeError("connection refused")
        result = await health_mgr.check_database(db_check_fn=failing_fn)
        assert result.status == HealthComponentStatus.UNHEALTHY

    async def test_run_system_checks(self, health_mgr: HealthCheckManager) -> None:
        results = await health_mgr.run_system_checks()
        assert len(results) == 4
        components = [r.component for r in results]
        assert "application" in components
        assert "redis" in components
        assert "cache" in components
        assert "database" in components

    async def test_run_all_checks(self, health_mgr: HealthCheckManager) -> None:
        report = await health_mgr.run_all_checks()
        assert isinstance(report, HealthReport)
        assert len(report.checks) >= 4

    async def test_register_custom_check(self, health_mgr: HealthCheckManager) -> None:
        async def custom_check() -> HealthCheckResult:
            return HealthCheckResult(
                component="custom",
                status=HealthComponentStatus.HEALTHY,
            )
        health_mgr.register_check("custom", custom_check)
        report = await health_mgr.run_all_checks()
        components = [c.component for c in report.checks]
        assert "custom" in components


# ── PerformanceProfiler Tests ──────────────────────────

class TestPerformanceProfiler:
    @pytest.fixture
    def profiler(self) -> PerformanceProfiler:
        return PerformanceProfiler(enabled=True)

    async def test_profile(self, profiler: PerformanceProfiler) -> None:
        async def work() -> str:
            return "done"
        result = await profiler.profile("test_op", "test_comp", work)
        assert result == "done"
        assert len(profiler.get_recent()) == 1

    async def test_profile_disabled(self) -> None:
        profiler = PerformanceProfiler(enabled=False)
        async def work() -> str:
            return "done"
        result = await profiler.profile("test_op", "test_comp", work)
        assert result == "done"
        assert len(profiler.get_recent()) == 0

    async def test_get_recent(self, profiler: PerformanceProfiler) -> None:
        async def work() -> None:
            pass
        for _ in range(5):
            await profiler.profile("op", "comp", work)
        recent = profiler.get_recent(limit=3)
        assert len(recent) == 3

    async def test_get_slowest(self, profiler: PerformanceProfiler) -> None:
        for i in range(5):
            import asyncio
            delay = (5 - i) * 0.001
            async def work(d: float = delay) -> None:
                await asyncio.sleep(d)
            await profiler.profile("op", "comp", work)
        slowest = profiler.get_slowest(limit=2)
        assert len(slowest) == 2

    def test_get_average_duration_empty(self, profiler: PerformanceProfiler) -> None:
        avg = profiler.get_average_duration("nonexistent")
        assert avg == 0.0

    async def test_get_average_duration(self, profiler: PerformanceProfiler) -> None:
        import asyncio
        for _ in range(3):
            async def work() -> None:
                await asyncio.sleep(0.001)
            await profiler.profile("test_op", "comp", work)
        avg = profiler.get_average_duration("test_op")
        assert avg > 0

    def test_get_statistics_empty(self) -> None:
        profiler = PerformanceProfiler()
        stats = profiler.get_statistics()
        assert stats["total_profiles"] == 0

    async def test_get_statistics(self, profiler: PerformanceProfiler) -> None:
        async def work() -> None:
            pass
        await profiler.profile("op", "comp", work)
        stats = profiler.get_statistics()
        assert stats["total_profiles"] == 1
        assert "avg_duration_ms" in stats

    async def test_clear(self, profiler: PerformanceProfiler) -> None:
        async def work() -> None:
            pass
        await profiler.profile("op", "comp", work)
        assert len(profiler.get_recent()) == 1
        profiler.clear()
        assert len(profiler.get_recent()) == 0


# ── AlertManager Tests ─────────────────────────────────

class TestAlertManager:
    @pytest.fixture
    def alert_mgr(self) -> AlertManager:
        return AlertManager()

    def test_add_rule(self, alert_mgr: AlertManager) -> None:
        rule = AlertRule(name="high_error_rate", severity=AlertSeverity.CRITICAL, threshold=0.05)
        alert_mgr.add_rule(rule)
        assert len(alert_mgr.get_rules()) == 1

    def test_remove_rule(self, alert_mgr: AlertManager) -> None:
        rule = AlertRule(name="test_rule")
        alert_mgr.add_rule(rule)
        alert_mgr.remove_rule(rule.id or rule.name)
        assert len(alert_mgr.get_rules()) == 0

    async def test_fire_alert(self, alert_mgr: AlertManager) -> None:
        alert = await alert_mgr.fire(
            rule_name="error_rate",
            metric_value=0.15,
            message="Error rate exceeded",
            severity=AlertSeverity.CRITICAL,
            component="api",
        )
        assert alert.status == AlertStatus.FIRING
        assert alert.severity == AlertSeverity.CRITICAL
        assert alert.metric_value == 0.15

    async def test_fire_with_rule(self, alert_mgr: AlertManager) -> None:
        rule = AlertRule(name="error_rate", severity=AlertSeverity.CRITICAL, threshold=0.05)
        alert_mgr.add_rule(rule)
        alert = await alert_mgr.fire(rule_name="error_rate", metric_value=0.15)
        assert alert.rule_name == "error_rate"
        assert alert.threshold == 0.05

    async def test_resolve_alert(self, alert_mgr: AlertManager) -> None:
        alert = await alert_mgr.fire(rule_name="test", metric_value=1.0)
        resolved = await alert_mgr.resolve(alert.id)
        assert resolved is not None
        assert resolved.status == AlertStatus.RESOLVED

    async def test_resolve_nonexistent(self, alert_mgr: AlertManager) -> None:
        resolved = await alert_mgr.resolve("nonexistent")
        assert resolved is None

    async def test_get_active_alerts(self, alert_mgr: AlertManager) -> None:
        await alert_mgr.fire(rule_name="a", metric_value=1.0)
        await alert_mgr.fire(rule_name="b", metric_value=2.0)
        assert len(alert_mgr.get_active_alerts()) == 2

    async def test_get_active_alerts_after_resolve(self, alert_mgr: AlertManager) -> None:
        alert = await alert_mgr.fire(rule_name="test", metric_value=1.0)
        await alert_mgr.resolve(alert.id)
        assert len(alert_mgr.get_active_alerts()) == 0

    async def test_acknowledge(self, alert_mgr: AlertManager) -> None:
        alert = await alert_mgr.fire(rule_name="test", metric_value=1.0)
        assert alert_mgr.acknowledge(alert.id) is True
        assert alert.status == AlertStatus.ACKNOWLEDGED

    async def test_acknowledge_nonexistent(self, alert_mgr: AlertManager) -> None:
        assert alert_mgr.acknowledge("nonexistent") is False

    async def test_get_recent_alerts(self, alert_mgr: AlertManager) -> None:
        for i in range(5):
            await alert_mgr.fire(rule_name=f"rule_{i}", metric_value=float(i))
        recent = alert_mgr.get_recent_alerts(limit=3)
        assert len(recent) == 3

    async def test_clear_resolved(self, alert_mgr: AlertManager) -> None:
        a1 = await alert_mgr.fire(rule_name="a", metric_value=1.0)
        await alert_mgr.fire(rule_name="b", metric_value=2.0)
        await alert_mgr.resolve(a1.id)
        cleared = alert_mgr.clear_resolved()
        assert cleared == 1
        assert len(alert_mgr.get_recent_alerts()) == 1

    async def test_register_hook(self, alert_mgr: AlertManager) -> None:
        hook_called = False
        async def hook(_alert: Alert) -> None:
            nonlocal hook_called
            hook_called = True
        alert_mgr.register_hook(hook)
        await alert_mgr.fire(rule_name="test", metric_value=1.0)
        assert hook_called is True


# ── TelemetryCoordinator Tests ─────────────────────────

class TestTelemetryCoordinator:
    @pytest.fixture
    def coordinator(self) -> TelemetryCoordinator:
        return TelemetryCoordinator(
            metrics=MetricsCollector(),
            tracing=TracingManager(),
            logging_mgr=LoggingManager(),
            health=HealthCheckManager(),
            profiler=PerformanceProfiler(),
            alerting=AlertManager(),
            environment="testing",
        )

    async def test_collect_batch(self, coordinator: TelemetryCoordinator) -> None:
        batch = await coordinator.collect_batch()
        assert batch.source == "sfir-backend"
        assert batch.environment == "testing"

    async def test_export(self, coordinator: TelemetryCoordinator) -> None:
        await coordinator.export()

    async def test_export_with_exporter(self, coordinator: TelemetryCoordinator) -> None:
        exported = False
        async def exporter(_batch: object) -> None:
            nonlocal exported
            exported = True
        coordinator.register_exporter(exporter)
        await coordinator.export()
        assert exported is True

    def test_properties(self, coordinator: TelemetryCoordinator) -> None:
        assert coordinator.metrics is not None
        assert coordinator.tracing is not None
        assert coordinator.logging is not None
        assert coordinator.health is not None
        assert coordinator.profiler is not None
        assert coordinator.alerting is not None

    def test_get_methods(self, coordinator: TelemetryCoordinator) -> None:
        assert coordinator.get_metrics_collector() is coordinator.metrics
        assert coordinator.get_tracing_manager() is coordinator.tracing
        assert coordinator.get_logging_manager() is coordinator.logging
        assert coordinator.get_health_manager() is coordinator.health
        assert coordinator.get_profiler() is coordinator.profiler
        assert coordinator.get_alert_manager() is coordinator.alerting


# ── DiagnosticsService Tests ───────────────────────────

class TestDiagnosticsService:
    @pytest.fixture
    def diagnostics(self) -> DiagnosticsService:
        return DiagnosticsService(
            health=HealthCheckManager(),
            metrics=MetricsCollector(),
            profiler=PerformanceProfiler(),
            alerting=AlertManager(),
            logging_mgr=LoggingManager(),
            environment="testing",
        )

    async def test_generate_report(self, diagnostics: DiagnosticsService) -> None:
        report = await diagnostics.generate_report()
        assert report.environment == "testing"
        assert report.version == "0.1.0"
        assert report.health is not None

    async def test_quick_check(self, diagnostics: DiagnosticsService) -> None:
        result = await diagnostics.quick_check()
        assert result["status"] == "healthy"
        assert result["service"] == "sfir-backend"
        assert "timestamp" in result
