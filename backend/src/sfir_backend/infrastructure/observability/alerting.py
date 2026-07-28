from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import structlog

from sfir_backend.domain.observability.models import (
    Alert,
    AlertRule,
    AlertSeverity,
    AlertStatus,
)

logger = structlog.get_logger(__name__)


class AlertManager:
    def __init__(self) -> None:
        self._rules: dict[str, AlertRule] = {}
        self._alerts: list[Alert] = []
        self._max_alerts: int = 1000
        self._hooks: list[Any] = []

    def add_rule(self, rule: AlertRule) -> None:
        self._rules[rule.id or rule.name] = rule
        logger.info("alert_rule_added", rule_name=rule.name, severity=rule.severity.value)

    def remove_rule(self, rule_id: str) -> None:
        self._rules.pop(rule_id, None)

    def get_rules(self) -> list[AlertRule]:
        return list(self._rules.values())

    def register_hook(self, hook: Any) -> None:
        self._hooks.append(hook)

    async def fire(
        self,
        rule_name: str,
        metric_value: float,
        message: str = "",
        *,
        severity: AlertSeverity | None = None,
        component: str = "",
        details: dict[str, Any] | None = None,
    ) -> Alert:
        rule = next(
            (r for r in self._rules.values() if r.name == rule_name),
            None,
        )

        alert = Alert(
            id=str(uuid4()),
            rule_id=rule.id if rule else "",
            rule_name=rule_name,
            severity=severity or (rule.severity if rule else AlertSeverity.WARNING),
            status=AlertStatus.FIRING,
            message=message or f"Alert: {rule_name} = {metric_value}",
            metric_value=metric_value,
            threshold=rule.threshold if rule else 0.0,
            component=component or rule_name,
            details=details or {},
        )
        self._alerts.append(alert)
        if len(self._alerts) > self._max_alerts:
            self._alerts.pop(0)

        logger.warning(
            "alert_fired",
            rule_name=rule_name,
            severity=alert.severity.value,
            metric_value=metric_value,
            threshold=alert.threshold,
            component=component,
        )

        for hook in self._hooks:
            try:
                if callable(hook):
                    result = hook(alert)
                    if hasattr(result, "__await__"):
                        await result
            except Exception as e:
                logger.error("alert_hook_failed", error=str(e))

        return alert

    async def resolve(self, alert_id: str) -> Alert | None:
        for alert in self._alerts:
            if alert.id == alert_id and alert.status == AlertStatus.FIRING:
                alert.status = AlertStatus.RESOLVED
                alert.resolved_at = datetime.now(tz=UTC)
                logger.info("alert_resolved", alert_id=alert_id, rule_name=alert.rule_name)
                return alert
        return None

    def get_active_alerts(self) -> list[Alert]:
        return [
            a for a in self._alerts
            if a.status == AlertStatus.FIRING
        ]

    def get_recent_alerts(self, limit: int = 100) -> list[Alert]:
        return self._alerts[-limit:]

    def acknowledge(self, alert_id: str) -> bool:
        for alert in self._alerts:
            if alert.id == alert_id and alert.status == AlertStatus.FIRING:
                alert.status = AlertStatus.ACKNOWLEDGED
                return True
        return False

    def clear_resolved(self) -> int:
        before = len(self._alerts)
        self._alerts = [a for a in self._alerts if a.status == AlertStatus.FIRING]
        return before - len(self._alerts)
