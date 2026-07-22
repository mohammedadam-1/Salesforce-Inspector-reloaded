from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class LogLevel(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class HealthComponentStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    NOT_CONFIGURED = "not_configured"
    UNKNOWN = "unknown"


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(StrEnum):
    FIRING = "firing"
    RESOLVED = "resolved"
    ACKNOWLEDGED = "acknowledged"


class MetricType(StrEnum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


class HealthCheckResult(BaseModel):
    component: str = ""
    status: HealthComponentStatus = HealthComponentStatus.UNKNOWN
    latency_ms: float = 0.0
    message: str = ""
    last_check: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    details: dict[str, Any] = Field(default_factory=dict)


class HealthReport(BaseModel):
    overall_status: HealthComponentStatus = HealthComponentStatus.UNKNOWN
    checks: list[HealthCheckResult] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    service: str = "sfir-backend"
    version: str = "0.1.0"

    @property
    def all_healthy(self) -> bool:
        return all(
            c.status == HealthComponentStatus.HEALTHY
            for c in self.checks
        )

    @property
    def unhealthy_components(self) -> list[HealthCheckResult]:
        return [
            c for c in self.checks
            if c.status != HealthComponentStatus.HEALTHY
        ]


class MetricSnapshot(BaseModel):
    name: str = ""
    type: MetricType = MetricType.COUNTER
    value: float = 0.0
    labels: dict[str, str] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class TraceSpan(BaseModel):
    span_id: str = ""
    trace_id: str = ""
    parent_span_id: str = ""
    name: str = ""
    start_time: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    end_time: datetime | None = None
    duration_ms: float = 0.0
    attributes: dict[str, Any] = Field(default_factory=dict)
    status: str = "ok"
    service: str = "sfir-backend"


class LogEvent(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    level: LogLevel = LogLevel.INFO
    message: str = ""
    logger: str = ""
    correlation_id: str = ""
    trace_id: str = ""
    span_id: str = ""
    tenant_id: str = ""
    organization_id: str = ""
    user_id: str = ""
    component: str = ""
    operation: str = ""
    duration_ms: float = 0.0
    error: str = ""
    context: dict[str, Any] = Field(default_factory=dict)


class AlertRule(BaseModel):
    id: str = ""
    name: str = ""
    description: str = ""
    severity: AlertSeverity = AlertSeverity.WARNING
    metric_name: str = ""
    condition: str = ""
    threshold: float = 0.0
    duration_seconds: int = 60
    enabled: bool = True
    cooldown_seconds: int = 300


class Alert(BaseModel):
    id: str = ""
    rule_id: str = ""
    rule_name: str = ""
    severity: AlertSeverity = AlertSeverity.WARNING
    status: AlertStatus = AlertStatus.FIRING
    message: str = ""
    metric_value: float = 0.0
    threshold: float = 0.0
    triggered_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    resolved_at: datetime | None = None
    component: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class PerformanceProfile(BaseModel):
    operation: str = ""
    component: str = ""
    duration_ms: float = 0.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    cpu_percent: float = 0.0
    memory_bytes: int = 0
    db_queries: int = 0
    db_duration_ms: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    context: dict[str, Any] = Field(default_factory=dict)


class DiagnosticReport(BaseModel):
    id: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    service: str = "sfir-backend"
    version: str = "0.1.0"
    environment: str = ""
    health: HealthReport = Field(default_factory=HealthReport)
    metrics: list[MetricSnapshot] = Field(default_factory=list)
    recent_errors: list[LogEvent] = Field(default_factory=list)
    performance: list[PerformanceProfile] = Field(default_factory=list)
    active_alerts: list[Alert] = Field(default_factory=list)
    system_info: dict[str, Any] = Field(default_factory=dict)
    redis_info: dict[str, Any] = Field(default_factory=dict)
    db_info: dict[str, Any] = Field(default_factory=dict)


class TelemetryBatch(BaseModel):
    id: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    spans: list[TraceSpan] = Field(default_factory=list)
    metrics: list[MetricSnapshot] = Field(default_factory=list)
    logs: list[LogEvent] = Field(default_factory=list)
    source: str = "sfir-backend"
    environment: str = ""
