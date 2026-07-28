import uuid
from datetime import UTC, datetime

from sfir_backend.domain.security.models import (
    AbusePattern,
    AbusePatternType,
    AuditCategory,
    AuditEntry,
    AuditSeverity,
    EncryptionKeyMetadata,
    EncryptionKeyStatus,
    RateLimitRule,
    RateLimitStrategy,
    SecurityAlert,
    SecurityEvent,
    SecurityEventType,
    SecurityPolicyEffect,
    SecurityPolicyRule,
    TenantAccessResult,
    TenantAccessValidation,
)


class TestSecurityEvent:
    def test_create_minimal(self) -> None:
        event = SecurityEvent.create(SecurityEventType.USER_LOGIN)
        assert event.event_type == SecurityEventType.USER_LOGIN
        assert event.id is not None
        assert event.severity == AuditSeverity.INFO
        assert event.category == AuditCategory.SECURITY

    def test_create_full(self) -> None:
        user_id = uuid.uuid4()
        org_id = uuid.uuid4()
        event = SecurityEvent.create(
            event_type=SecurityEventType.USER_LOGIN_FAILED,
            user_id=user_id,
            organization_id=org_id,
            ip_address="192.168.1.1",
            user_agent="test-agent",
            resource_type="password",
            resource_id="attempt-1",
            details={"reason": "wrong_password"},
            severity=AuditSeverity.WARNING,
            category=AuditCategory.AUTHENTICATION,
            correlation_id="corr-123",
        )
        assert event.user_id == user_id
        assert event.organization_id == org_id
        assert event.ip_address == "192.168.1.1"
        assert event.details == {"reason": "wrong_password"}

    def test_timestamp_defaults_to_now(self) -> None:
        event = SecurityEvent.create(SecurityEventType.USER_LOGIN)
        assert isinstance(event.timestamp, datetime)
        assert (datetime.now(UTC) - event.timestamp).total_seconds() < 5


class TestAuditEntry:
    def test_create(self) -> None:
        entry = AuditEntry.create(
            action=SecurityEventType.ORG_CREATED,
            actor_id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            target_type="organization",
            target_id="org-123",
            changes={"name": "New Org"},
            outcome="success",
        )
        assert entry.action == SecurityEventType.ORG_CREATED
        assert entry.outcome == "success"
        assert entry.changes == {"name": "New Org"}


class TestSecurityAlert:
    def test_create_and_acknowledge(self) -> None:
        alert = SecurityAlert(
            id=uuid.uuid4(),
            title="Test Alert",
            description="A test security alert",
            severity=AuditSeverity.ERROR,
            event_type=SecurityEventType.ABUSE_DETECTED,
        )
        assert not alert.acknowledged
        assert not alert.resolved

        user_id = uuid.uuid4()
        alert.acknowledge(user_id)
        assert alert.acknowledged
        assert alert.acknowledged_by == user_id
        assert alert.acknowledged_at is not None

    def test_resolve(self) -> None:
        alert = SecurityAlert(
            id=uuid.uuid4(),
            title="Alert",
            description="Desc",
            severity=AuditSeverity.INFO,
            event_type=SecurityEventType.USER_LOGIN_FAILED,
        )
        alert.resolve()
        assert alert.resolved
        assert alert.resolved_at is not None


class TestRateLimitRule:
    def test_default_strategy(self) -> None:
        rule = RateLimitRule(key="test", max_requests=100, window_seconds=60)
        assert rule.strategy == RateLimitStrategy.SLIDING_WINDOW
        assert rule.enabled


class TestSecurityPolicyRule:
    def test_create(self) -> None:
        rule = SecurityPolicyRule(
            id=uuid.uuid4(),
            name="deny-all",
            effect=SecurityPolicyEffect.DENY,
            resource_pattern="*",
            action_pattern="*",
            priority=1,
        )
        assert rule.effect == SecurityPolicyEffect.DENY
        assert rule.enabled


class TestEncryptionKeyMetadata:
    def test_create(self) -> None:
        meta = EncryptionKeyMetadata(
            id=uuid.uuid4(),
            version=1,
            algorithm="AES-256-GCM",
            status=EncryptionKeyStatus.ACTIVE,
            created_at=datetime.now(UTC),
        )
        assert meta.status == EncryptionKeyStatus.ACTIVE
        assert meta.version == 1


class TestAbusePattern:
    def test_create(self) -> None:
        pattern = AbusePattern(
            pattern_type=AbusePatternType.BRUTE_FORCE,
            criteria={"event_type": SecurityEventType.USER_LOGIN_FAILED},
            threshold=10,
            window_seconds=300,
        )
        assert pattern.action == "alert"


class TestTenantAccessResult:
    def test_allowed(self) -> None:
        result = TenantAccessResult(
            validation=TenantAccessValidation.ALLOWED,
            user_id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
        )
        assert result.validation == TenantAccessValidation.ALLOWED

    def test_denied(self) -> None:
        result = TenantAccessResult(
            validation=TenantAccessValidation.DENIED_CROSS_TENANT,
            user_id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            message="Cross-tenant access denied",
        )
        assert result.validation == TenantAccessValidation.DENIED_CROSS_TENANT
        assert result.message == "Cross-tenant access denied"
