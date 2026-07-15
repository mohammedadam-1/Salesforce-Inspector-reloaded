from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sfir_backend.application.cache.services import RateLimitCacheService
from sfir_backend.config.settings import Settings
from sfir_backend.domain.repositories import (
    IAuditLogRepository,
    IOrgMemberRepository,
    IRefreshTokenRepository,
    IRoleRepository,
    ISessionRepository,
)
from sfir_backend.domain.security.models import (
    AuditCategory,
    AuditSeverity,
    SecurityEvent,
    SecurityEventType,
)
from sfir_backend.infrastructure.security.abuse_detection import AbuseDetector
from sfir_backend.infrastructure.security.audit_engine import AuditEngine
from sfir_backend.infrastructure.security.authorization_engine import (
    AuthorizationEngine,
)
from sfir_backend.infrastructure.security.encryption_service import (
    EncryptionService,
)
from sfir_backend.infrastructure.security.jwt import JWTService
from sfir_backend.infrastructure.security.rate_limiter import RateLimiter
from sfir_backend.infrastructure.security.secrets_manager import SecretsManager
from sfir_backend.infrastructure.security.security_event_publisher import (
    SecurityEventPublisher,
)
from sfir_backend.infrastructure.security.security_policy_engine import (
    SecurityPolicyEngine,
)
from sfir_backend.infrastructure.security.session_security import (
    SessionSecurityManager,
)


@dataclass
class SecurityStatus:
    overall: str = "healthy"
    encryption_key_version: int = 0
    encryption_algorithm: str = ""
    active_rules: int = 0
    active_rate_limit_rules: int = 0
    events_last_hour: int = 0
    secrets_provider: str = ""
    last_audit_event: str = ""
    last_audit_timestamp: str = ""
    checks: dict[str, Any] = field(default_factory=dict)


class SecurityManager:
    def __init__(
        self,
        settings: Settings,
        encryption_service: EncryptionService,
        jwt_service: JWTService,
        org_member_repo: IOrgMemberRepository,
        role_repo: IRoleRepository,
        session_repo: ISessionRepository,
        refresh_token_repo: IRefreshTokenRepository,
        audit_log_repo: IAuditLogRepository,
        rate_limit_cache: RateLimitCacheService | None = None,
        metrics_collector: Any = None,
        alert_manager: Any = None,
    ) -> None:
        self._settings = settings
        self._encryption_service = encryption_service
        self._jwt_service = jwt_service

        self._audit_engine = AuditEngine(audit_log_repo=audit_log_repo)
        self._authorization_engine = AuthorizationEngine(
            org_member_repo=org_member_repo,
            role_repo=role_repo,
            audit_engine=self._audit_engine,
        )
        self._rate_limiter = RateLimiter(settings, rate_limit_cache)
        self._abuse_detector = AbuseDetector()
        self._session_security = SessionSecurityManager(
            jwt_service=jwt_service,
            session_repo=session_repo,
            refresh_token_repo=refresh_token_repo,
            audit_engine=self._audit_engine,
        )
        self._secrets_manager = SecretsManager(settings)
        self._security_policy_engine = SecurityPolicyEngine(
            audit_engine=self._audit_engine,
        )
        self._security_event_publisher = SecurityEventPublisher(
            metrics_collector=metrics_collector,
            alert_manager=alert_manager,
        )

        self._event_count_last_hour = 0
        self._last_event: SecurityEvent | None = None
        self._abuse_tasks: set[Any] = set()

        self._wire_abuse_detection()

    def _wire_abuse_detection(self) -> None:
        self._abuse_detector.register_reporter(self._on_abuse_detected)

    def _on_abuse_detected(self, pattern: Any, identifier: str) -> None:
        import asyncio
        task = asyncio.ensure_future(self._handle_abuse(pattern, identifier))
        self._abuse_tasks.add(task)
        task.add_done_callback(self._abuse_tasks.discard)

    async def _handle_abuse(self, pattern: Any, identifier: str) -> None:
        await self._audit_engine.record_event(
            event_type=SecurityEventType.ABUSE_DETECTED,
            details={
                "pattern_type": pattern.pattern_type.value,
                "identifier": identifier,
                "action": pattern.action,
            },
            severity=AuditSeverity.WARNING,
            category=AuditCategory.SECURITY,
        )

    @property
    def audit(self) -> AuditEngine:
        return self._audit_engine

    @property
    def authorization(self) -> AuthorizationEngine:
        return self._authorization_engine

    @property
    def rate_limiter(self) -> RateLimiter:
        return self._rate_limiter

    @property
    def session_security(self) -> SessionSecurityManager:
        return self._session_security

    @property
    def secrets_manager(self) -> SecretsManager:
        return self._secrets_manager

    @property
    def encryption(self) -> EncryptionService:
        return self._encryption_service

    @property
    def policy_engine(self) -> SecurityPolicyEngine:
        return self._security_policy_engine

    @property
    def event_publisher(self) -> SecurityEventPublisher:
        return self._security_event_publisher

    @property
    def abuse_detector(self) -> AbuseDetector:
        return self._abuse_detector

    @property
    def jwt_service(self) -> JWTService:
        return self._jwt_service

    async def record_event(
        self,
        event_type: SecurityEventType,
        user_id: uuid.UUID | None = None,
        organization_id: uuid.UUID | None = None,
        ip_address: str = "",
        user_agent: str = "",
        resource_type: str = "",
        resource_id: str = "",
        details: dict | None = None,
        severity: AuditSeverity = AuditSeverity.INFO,
        category: AuditCategory = AuditCategory.SECURITY,
        correlation_id: str = "",
    ) -> SecurityEvent:
        event = await self._audit_engine.record_event(
            event_type=event_type,
            actor_id=user_id,
            organization_id=organization_id,
            target_type=resource_type,
            target_id=resource_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            severity=severity,
            category=category,
            correlation_id=correlation_id,
        )

        await self._security_event_publisher.publish(event)

        self._event_count_last_hour += 1
        self._last_event = event

        return event

    async def get_status(self) -> SecurityStatus:
        return SecurityStatus(
            encryption_key_version=self._encryption_service.get_key_metadata().version,
            encryption_algorithm=self._settings.encryption_algorithm,
            active_rules=len(self._security_policy_engine.get_rules()),
            active_rate_limit_rules=len(self._rate_limiter._rules),
            events_last_hour=self._event_count_last_hour,
            secrets_provider=type(self._secrets_manager._provider).__name__,
            last_audit_event=self._last_event.event_type.value if self._last_event else "",
            last_audit_timestamp=(
                self._last_event.timestamp.isoformat() if self._last_event else ""
            ),
            checks={
                "encryption": self._encryption_service.get_key_metadata().status.value,
                "secrets": "healthy",
                "audit_engine": "enabled",
                "authorization": "active",
                "rate_limiter": "active",
                "session_security": "active",
                "policy_engine": "active",
            },
        )
