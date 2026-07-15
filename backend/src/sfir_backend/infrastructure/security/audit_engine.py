from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sfir_backend.domain.entities.audit_log import AuditLogEntry
from sfir_backend.domain.repositories.audit_log_repo import IAuditLogRepository
from sfir_backend.domain.security.models import (
    AuditCategory,
    AuditSeverity,
    SecurityEvent,
    SecurityEventType,
)


class AuditEngine:
    def __init__(
        self,
        audit_log_repo: IAuditLogRepository | None = None,
    ) -> None:
        self._audit_log_repo = audit_log_repo
        self._handlers: list[Callable[[SecurityEvent], Any]] = []
        self._enabled = True

    def register_handler(
        self, handler: Callable[[SecurityEvent], Any],
    ) -> None:
        self._handlers.append(handler)

    async def record_event(
        self,
        event_type: SecurityEventType,
        actor_id: uuid.UUID | None = None,
        organization_id: uuid.UUID | None = None,
        target_type: str = "",
        target_id: str = "",
        details: dict | None = None,
        ip_address: str = "",
        user_agent: str = "",
        severity: AuditSeverity = AuditSeverity.INFO,
        category: AuditCategory = AuditCategory.SYSTEM,
        outcome: str = "success",
        correlation_id: str = "",
    ) -> SecurityEvent:
        event = SecurityEvent.create(
            event_type=event_type,
            user_id=actor_id,
            organization_id=organization_id,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type=target_type,
            resource_id=target_id,
            details=details,
            severity=severity,
            category=category,
            correlation_id=correlation_id,
        )

        if self._audit_log_repo and self._enabled:
            audit_entry = AuditLogEntry(
                id=uuid.uuid4(),
                user_id=actor_id,
                organization_id=organization_id,
                action=event_type.value,
                resource_type=target_type,
                resource_id=target_id,
                details={
                    **(details or {}),
                    "severity": severity.value,
                    "category": category.value,
                    "outcome": outcome,
                    "correlation_id": correlation_id,
                    "user_agent": user_agent,
                },
                ip_address=ip_address,
            )
            await self._audit_log_repo.save(audit_entry)

        for handler in self._handlers:
            try:
                result = handler(event)
                if hasattr(result, "__await__"):
                    await result
            except Exception:
                pass

        return event

    async def query(
        self,
        organization_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
        event_types: list[SecurityEventType] | None = None,
        categories: list[AuditCategory] | None = None,
        severities: list[AuditSeverity] | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLogEntry]:
        if not self._audit_log_repo:
            return []

        entries: list[AuditLogEntry] = []
        if organization_id:
            entries = await self._audit_log_repo.list_by_org(
                organization_id, limit, offset,
            )
        elif actor_id:
            entries = await self._audit_log_repo.list_by_user(
                actor_id, limit, offset,
            )

        if not any([event_types, categories, severities, start_time, end_time]):
            return entries

        result = []
        for entry in entries:
            if event_types and entry.action not in [e.value for e in event_types]:
                continue
            if start_time and entry.created_at < start_time:
                continue
            if end_time and entry.created_at > end_time:
                continue
            result.append(entry)
        return result

    async def count_events(
        self,
        organization_id: uuid.UUID,
        since: datetime | None = None,
    ) -> int:
        if not self._audit_log_repo:
            return 0
        return await self._audit_log_repo.count_by_org(
            organization_id, since or datetime.now(UTC),
        )

    def disable(self) -> None:
        self._enabled = False

    def enable(self) -> None:
        self._enabled = True
