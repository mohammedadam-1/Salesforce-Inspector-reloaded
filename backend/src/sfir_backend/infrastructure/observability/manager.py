from __future__ import annotations

import structlog

from sfir_backend.infrastructure.observability.alerting import AlertManager
from sfir_backend.infrastructure.observability.diagnostics import DiagnosticsService
from sfir_backend.infrastructure.observability.health import HealthCheckManager
from sfir_backend.infrastructure.observability.logging import LoggingManager
from sfir_backend.infrastructure.observability.metrics import MetricsCollector
from sfir_backend.infrastructure.observability.profiler import PerformanceProfiler
from sfir_backend.infrastructure.observability.telemetry import TelemetryCoordinator
from sfir_backend.infrastructure.observability.tracing import TracingManager

logger = structlog.get_logger(__name__)


class ObservabilityManager:
    def __init__(
        self,
        metrics: MetricsCollector,
        tracing: TracingManager,
        logging_mgr: LoggingManager,
        health: HealthCheckManager,
        profiler: PerformanceProfiler,
        alerting: AlertManager,
        telemetry: TelemetryCoordinator,
        diagnostics: DiagnosticsService,
    ) -> None:
        self._metrics = metrics
        self._tracing = tracing
        self._logging = logging_mgr
        self._health = health
        self._profiler = profiler
        self._alerting = alerting
        self._telemetry = telemetry
        self._diagnostics = diagnostics
        self._initialized = True

        logger.info("observability_manager_initialized")

    @property
    def metrics(self) -> MetricsCollector:
        return self._metrics

    @property
    def tracing(self) -> TracingManager:
        return self._tracing

    @property
    def logging(self) -> LoggingManager:
        return self._logging

    @property
    def health(self) -> HealthCheckManager:
        return self._health

    @property
    def profiler(self) -> PerformanceProfiler:
        return self._profiler

    @property
    def alerting(self) -> AlertManager:
        return self._alerting

    @property
    def telemetry(self) -> TelemetryCoordinator:
        return self._telemetry

    @property
    def diagnostics(self) -> DiagnosticsService:
        return self._diagnostics
