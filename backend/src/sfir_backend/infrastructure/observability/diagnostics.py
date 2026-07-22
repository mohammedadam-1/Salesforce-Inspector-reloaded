from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import structlog

from sfir_backend.domain.observability.models import (
    DiagnosticReport,
    LogEvent,
)
from sfir_backend.infrastructure.observability.alerting import AlertManager
from sfir_backend.infrastructure.observability.health import HealthCheckManager
from sfir_backend.infrastructure.observability.logging import LoggingManager
from sfir_backend.infrastructure.observability.metrics import MetricsCollector
from sfir_backend.infrastructure.observability.profiler import PerformanceProfiler

logger = structlog.get_logger(__name__)


class DiagnosticsService:
    def __init__(
        self,
        health: HealthCheckManager,
        metrics: MetricsCollector,
        profiler: PerformanceProfiler,
        alerting: AlertManager,
        logging_mgr: LoggingManager,
        environment: str = "development",
        service_version: str = "0.1.0",
    ) -> None:
        self._health = health
        self._metrics = metrics
        self._profiler = profiler
        self._alerting = alerting
        self._logging = logging_mgr
        self._environment = environment
        self._service_version = service_version

    async def generate_report(
        self,
        db_check_fn: Any = None,
    ) -> DiagnosticReport:
        health_report = await self._health.run_all_checks(db_check_fn=db_check_fn)

        return DiagnosticReport(
            id=str(uuid4()),
            environment=self._environment,
            version=self._service_version,
            health=health_report,
            metrics=self._metrics.snapshot(),
            recent_errors=self._collect_errors(),
            performance=self._profiler.get_recent(limit=20),
            active_alerts=self._alerting.get_active_alerts(),
            system_info=self._get_system_info(),
        )

    async def quick_check(self) -> dict[str, Any]:
        app_check = await self._health.check_application()
        return {
            "status": app_check.status.value,
            "service": "sfir-backend",
            "version": self._service_version,
            "timestamp": datetime.now(tz=UTC).isoformat(),
        }

    def _collect_errors(self) -> list[LogEvent]:
        return []

    def _get_system_info(self) -> dict[str, Any]:
        return {
            "environment": self._environment,
            "service": "sfir-backend",
            "version": self._service_version,
            "python": __import__("sys").version,
            "platform": __import__("sys").platform,
        }
