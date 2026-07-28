from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class AlertHookManager:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[..., Any]]] = {
            "info": [],
            "warning": [],
            "critical": [],
        }

    def register_handler(
        self,
        severity: str,
        handler: Callable[..., Any],
    ) -> None:
        self._handlers.setdefault(severity, []).append(handler)

    async def fire(
        self,
        title: str,
        message: str,
        severity: str = "warning",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        log_fn = {
            "info": logger.info,
            "warning": logger.warning,
            "critical": logger.error,
        }.get(severity, logger.warning)

        log_fn(
            "Alert fired",
            title=title,
            message=message,
            severity=severity,
            metadata=metadata,
        )

        handlers = self._handlers.get(severity, []) + self._handlers.get("critical", [])
        for handler in handlers:
            try:
                await handler(
                    title=title,
                    message=message,
                    severity=severity,
                    metadata=metadata or {},
                )
            except Exception as e:
                logger.error("Alert handler failed", error=str(e))

    async def fire_high_latency(
        self,
        component: str,
        latency_ms: float,
        threshold_ms: float,
    ) -> None:
        await self.fire(
            title=f"High latency on {component}",
            message=f"{component} latency is {latency_ms:.0f}ms (threshold: {threshold_ms:.0f}ms)",
            severity="warning",
            metadata={"component": component, "latency_ms": latency_ms, "threshold_ms": threshold_ms},
        )

    async def fire_error_rate(
        self,
        component: str,
        error_rate: float,
        threshold: float,
    ) -> None:
        await self.fire(
            title=f"Elevated error rate on {component}",
            message=f"{component} error rate is {error_rate:.2%} (threshold: {threshold:.2%})",
            severity="critical" if error_rate > threshold * 2 else "warning",
            metadata={"component": component, "error_rate": error_rate, "threshold": threshold},
        )
