from __future__ import annotations

from datetime import UTC, datetime

from sfir_backend.domain.observability.models import (
    Alert,
    AlertRule,
    AlertSeverity,
    AlertStatus,
    DiagnosticReport,
    HealthCheckResult,
    HealthComponentStatus,
    HealthReport,
    LogEvent,
    LogLevel,
    MetricSnapshot,
    MetricType,
    PerformanceProfile,
    TelemetryBatch,
    TraceSpan,
)


class TestLogLevel:
    def test_values(self) -> None:
        assert LogLevel.DEBUG == "debug"
        assert LogLevel.INFO == "info"
        assert LogLevel.WARNING == "warning"
        assert LogLevel.ERROR == "error"
        assert LogLevel.CRITICAL == "critical"


class TestHealthComponentStatus:
    def test_values(self) -> None:
        assert HealthComponentStatus.HEALTHY == "healthy"
        assert HealthComponentStatus.DEGRADED == "degraded"
        assert HealthComponentStatus.UNHEALTHY == "unhealthy"
        assert HealthComponentStatus.NOT_CONFIGURED == "not_configured"


class TestAlertSeverity:
    def test_values(self) -> None:
        assert AlertSeverity.INFO == "info"
        assert AlertSeverity.WARNING == "warning"
        assert AlertSeverity.CRITICAL == "critical"


class TestAlertStatus:
    def test_values(self) -> None:
        assert AlertStatus.FIRING == "firing"
        assert AlertStatus.RESOLVED == "resolved"
        assert AlertStatus.ACKNOWLEDGED == "acknowledged"


class TestMetricType:
    def test_values(self) -> None:
        assert MetricType.COUNTER == "counter"
        assert MetricType.GAUGE == "gauge"
        assert MetricType.HISTOGRAM == "histogram"


class TestHealthCheckResult:
    def test_defaults(self) -> None:
        r = HealthCheckResult()
        assert r.component == ""
        assert r.status == HealthComponentStatus.UNKNOWN
        assert r.latency_ms == 0.0
        assert r.message == ""

    def test_with_values(self) -> None:
        r = HealthCheckResult(
            component="redis",
            status=HealthComponentStatus.HEALTHY,
            latency_ms=5.0,
            message="Redis connected",
            details={"version": "7.2"},
        )
        assert r.component == "redis"
        assert r.status == HealthComponentStatus.HEALTHY
        assert r.latency_ms == 5.0
        assert r.details["version"] == "7.2"


class TestHealthReport:
    def test_defaults(self) -> None:
        r = HealthReport()
        assert r.overall_status == HealthComponentStatus.UNKNOWN
        assert r.checks == []
        assert r.service == "sfir-backend"

    def test_all_healthy_empty(self) -> None:
        r = HealthReport()
        assert r.all_healthy is True

    def test_all_healthy_true(self) -> None:
        r = HealthReport(checks=[
            HealthCheckResult(component="a", status=HealthComponentStatus.HEALTHY),
            HealthCheckResult(component="b", status=HealthComponentStatus.HEALTHY),
        ])
        assert r.all_healthy is True
        assert r.unhealthy_components == []

    def test_all_healthy_false(self) -> None:
        r = HealthReport(checks=[
            HealthCheckResult(component="a", status=HealthComponentStatus.HEALTHY),
            HealthCheckResult(component="b", status=HealthComponentStatus.UNHEALTHY),
        ])
        assert r.all_healthy is False
        assert len(r.unhealthy_components) == 1

    def test_unhealthy_components(self) -> None:
        r = HealthReport(checks=[
            HealthCheckResult(component="a", status=HealthComponentStatus.HEALTHY),
            HealthCheckResult(component="b", status=HealthComponentStatus.DEGRADED),
            HealthCheckResult(component="c", status=HealthComponentStatus.UNHEALTHY),
        ])
        assert len(r.unhealthy_components) == 2


class TestMetricSnapshot:
    def test_defaults(self) -> None:
        m = MetricSnapshot()
        assert m.name == ""
        assert m.type == MetricType.COUNTER
        assert m.value == 0.0

    def test_with_values(self) -> None:
        m = MetricSnapshot(
            name="test_metric",
            type=MetricType.HISTOGRAM,
            value=42.5,
            labels={"method": "GET"},
        )
        assert m.name == "test_metric"
        assert m.type == MetricType.HISTOGRAM
        assert m.value == 42.5
        assert m.labels["method"] == "GET"


class TestTraceSpan:
    def test_defaults(self) -> None:
        s = TraceSpan()
        assert s.span_id == ""
        assert s.name == ""
        assert s.duration_ms == 0.0
        assert s.status == "ok"

    def test_with_values(self) -> None:
        s = TraceSpan(
            span_id="abc123",
            trace_id="def456",
            name="test_span",
            duration_ms=150.0,
            attributes={"key": "value"},
        )
        assert s.span_id == "abc123"
        assert s.trace_id == "def456"
        assert s.duration_ms == 150.0


class TestLogEvent:
    def test_defaults(self) -> None:
        e = LogEvent()
        assert e.level == LogLevel.INFO
        assert e.message == ""
        assert e.correlation_id == ""

    def test_with_values(self) -> None:
        e = LogEvent(
            level=LogLevel.ERROR,
            message="Something failed",
            correlation_id="cid-1",
            component="auth",
            operation="login",
            duration_ms=100.0,
            error="timeout",
        )
        assert e.level == LogLevel.ERROR
        assert e.message == "Something failed"
        assert e.correlation_id == "cid-1"
        assert e.duration_ms == 100.0


class TestAlertRule:
    def test_defaults(self) -> None:
        r = AlertRule()
        assert r.name == ""
        assert r.severity == AlertSeverity.WARNING
        assert r.enabled is True

    def test_with_values(self) -> None:
        r = AlertRule(
            name="high_error_rate",
            severity=AlertSeverity.CRITICAL,
            metric_name="error_rate",
            threshold=0.05,
            duration_seconds=300,
        )
        assert r.name == "high_error_rate"
        assert r.severity == AlertSeverity.CRITICAL
        assert r.threshold == 0.05


class TestAlert:
    def test_defaults(self) -> None:
        a = Alert()
        assert a.status == AlertStatus.FIRING
        assert a.metric_value == 0.0
        assert a.resolved_at is None

    def test_with_values(self) -> None:
        a = Alert(
            rule_name="high_error_rate",
            severity=AlertSeverity.CRITICAL,
            message="Error rate exceeded threshold",
            metric_value=0.15,
            threshold=0.05,
            component="api",
        )
        assert a.rule_name == "high_error_rate"
        assert a.severity == AlertSeverity.CRITICAL
        assert a.metric_value == 0.15
        assert a.resolved_at is None

    def test_resolve(self) -> None:
        a = Alert(status=AlertStatus.FIRING)
        a.status = AlertStatus.RESOLVED
        a.resolved_at = datetime.now(tz=UTC)
        assert a.status == AlertStatus.RESOLVED
        assert a.resolved_at is not None


class TestPerformanceProfile:
    def test_defaults(self) -> None:
        p = PerformanceProfile()
        assert p.operation == ""
        assert p.duration_ms == 0.0
        assert p.db_queries == 0

    def test_with_values(self) -> None:
        p = PerformanceProfile(
            operation="graph_build",
            component="GraphEngine",
            duration_ms=2500.0,
            db_queries=15,
            cache_hits=3,
            cache_misses=1,
        )
        assert p.operation == "graph_build"
        assert p.duration_ms == 2500.0
        assert p.db_queries == 15


class TestDiagnosticReport:
    def test_defaults(self) -> None:
        r = DiagnosticReport()
        assert r.service == "sfir-backend"
        assert r.environment == ""
        assert r.health.overall_status == HealthComponentStatus.UNKNOWN
        assert r.metrics == []
        assert r.active_alerts == []

    def test_with_values(self) -> None:
        r = DiagnosticReport(
            environment="production",
            health=HealthReport(overall_status=HealthComponentStatus.HEALTHY),
            system_info={"cpu": 4, "memory": "16GB"},
            redis_info={"version": "7.2"},
        )
        assert r.environment == "production"
        assert r.health.overall_status == HealthComponentStatus.HEALTHY


class TestTelemetryBatch:
    def test_defaults(self) -> None:
        b = TelemetryBatch()
        assert b.spans == []
        assert b.metrics == []
        assert b.logs == []
        assert b.source == "sfir-backend"
