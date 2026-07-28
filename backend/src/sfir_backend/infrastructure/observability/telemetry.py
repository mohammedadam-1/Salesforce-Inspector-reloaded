from __future__ import annotations

from typing import Any

import structlog

from sfir_backend.domain.observability.models import (
    TelemetryBatch,
    TraceSpan,
)
from sfir_backend.infrastructure.observability.alerting import AlertManager
from sfir_backend.infrastructure.observability.health import HealthCheckManager
from sfir_backend.infrastructure.observability.logging import LoggingManager
from sfir_backend.infrastructure.observability.metrics import MetricsCollector
from sfir_backend.infrastructure.observability.profiler import PerformanceProfiler
from sfir_backend.infrastructure.observability.tracing import TracingManager

logger = structlog.get_logger(__name__)


class TelemetryCoordinator:
    def __init__(
        self,
        metrics: MetricsCollector,
        tracing: TracingManager,
        logging_mgr: LoggingManager,
        health: HealthCheckManager,
        profiler: PerformanceProfiler,
        alerting: AlertManager,
        environment: str = "development",
    ) -> None:
        self._metrics = metrics
        self._tracing = tracing
        self._logging = logging_mgr
        self._health = health
        self._profiler = profiler
        self._alerting = alerting
        self._environment = environment
        self._batches: list[TelemetryBatch] = []
        self._max_batches: int = 100
        self._exporters: list[Any] = []

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

    def register_exporter(self, exporter: Any) -> None:
        self._exporters.append(exporter)

    async def collect_batch(self) -> TelemetryBatch:
        batch = TelemetryBatch(
            source="sfir-backend",
            environment=self._environment,
            spans=self._collect_spans(),
            metrics=self._metrics.snapshot(),
            logs=[],
        )
        self._batches.append(batch)
        if len(self._batches) > self._max_batches:
            self._batches.pop(0)
        return batch

    def _collect_spans(self) -> list[TraceSpan]:
        return []

    async def export(self) -> None:
        batch = await self.collect_batch()
        for exporter in self._exporters:
            try:
                if callable(exporter):
                    result = exporter(batch)
                    if hasattr(result, "__await__"):
                        await result
            except Exception as e:
                logger.error("telemetry_export_failed", error=str(e))

    def get_metrics_collector(self) -> MetricsCollector:
        return self._metrics

    def get_tracing_manager(self) -> TracingManager:
        return self._tracing

    def get_logging_manager(self) -> LoggingManager:
        return self._logging

    def get_health_manager(self) -> HealthCheckManager:
        return self._health

    def get_profiler(self) -> PerformanceProfiler:
        return self._profiler

    def get_alert_manager(self) -> AlertManager:
        return self._alerting
