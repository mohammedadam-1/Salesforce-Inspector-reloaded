from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from sfir_backend.domain.security.models import (
    AuditSeverity,
    SecurityEvent,
    SecurityEventType,
)
from sfir_backend.infrastructure.observability.alerting import AlertManager
from sfir_backend.infrastructure.observability.metrics import MetricsCollector


class SecurityEventPublisher:
    def __init__(
        self,
        metrics_collector: MetricsCollector | None = None,
        alert_manager: AlertManager | None = None,
    ) -> None:
        self._metrics_collector = metrics_collector
        self._alert_manager = alert_manager
        self._subscribers: dict[str, list[Callable[[SecurityEvent], Any]]] = {}

    def subscribe(
        self,
        event_type: SecurityEventType,
        handler: Callable[[SecurityEvent], Any],
    ) -> None:
        key = event_type.value
        if key not in self._subscribers:
            self._subscribers[key] = []
        self._subscribers[key].append(handler)

    def subscribe_all(self, handler: Callable[[SecurityEvent], Any]) -> None:
        for event_type in SecurityEventType:
            self.subscribe(event_type, handler)

    async def publish(self, event: SecurityEvent) -> None:
        self._publish_metrics(event)

        key = event.event_type.value
        handlers = self._subscribers.get(key, []) + self._subscribers.get("*", [])
        for handler in handlers:
            try:
                result = handler(event)
                if hasattr(result, "__await__"):
                    await result
            except Exception:
                pass

    def _publish_metrics(self, event: SecurityEvent) -> None:
        if not self._metrics_collector:
            return

        self._metrics_collector.record_custom(
            f"security_event_{event.event_type.value.replace('.', '_')}",
            1,
            labels={
                "event_type": event.event_type.value,
                "severity": event.severity.value,
                "category": event.category.value,
            },
        )

        if event.severity in (
            AuditSeverity.ERROR, AuditSeverity.CRITICAL,
        ):
            self._metrics_collector.record_custom(
                "security_event_severe_total",
                1,
                labels={"severity": event.severity.value},
            )

    async def publish_alert(
        self,
        event: SecurityEvent,
        title: str,
        description: str,
    ) -> None:
        if not self._alert_manager:
            return

        from sfir_backend.domain.observability.models import (
            Alert,
            AlertSeverity,
        )

        severity_map = {
            AuditSeverity.CRITICAL: AlertSeverity.CRITICAL,
            AuditSeverity.ERROR: AlertSeverity.HIGH,
            AuditSeverity.WARNING: AlertSeverity.MEDIUM,
            AuditSeverity.INFO: AlertSeverity.LOW,
            AuditSeverity.DEBUG: AlertSeverity.LOW,
        }

        await self._alert_manager.fire_alert(Alert(
            id=uuid.uuid4(),
            rule_name=f"security_{event.event_type.value.replace('.', '_')}",
            title=title,
            description=description,
            severity=severity_map.get(event.severity, AlertSeverity.MEDIUM),
            source="security",
            metadata={
                "event_id": str(event.id),
                "event_type": event.event_type.value,
                "user_id": str(event.user_id) if event.user_id else None,
                "org_id": str(event.organization_id) if event.organization_id else None,
            },
        ))

    def unsubscribe(
        self, event_type: SecurityEventType, handler: Callable[[SecurityEvent], Any],
    ) -> None:
        key = event_type.value
        if key in self._subscribers:
            self._subscribers[key] = [
                h for h in self._subscribers[key] if h != handler
            ]
