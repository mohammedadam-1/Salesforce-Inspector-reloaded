import enum
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


class SecurityEventType(enum.StrEnum):
    USER_LOGIN = "user.login"
    USER_LOGIN_FAILED = "user.login.failed"
    USER_LOGOUT = "user.logout"
    USER_REGISTERED = "user.registered"
    USER_LOCKED = "user.locked"
    USER_UNLOCKED = "user.unlocked"
    PASSWORD_CHANGED = "password.changed"
    PASSWORD_RESET_REQUESTED = "password.reset.requested"
    TOKEN_REFRESHED = "token.refreshed"
    TOKEN_REVOKED = "token.revoked"
    SESSION_CREATED = "session.created"
    SESSION_REVOKED = "session.revoked"
    ORG_CREATED = "org.created"
    ORG_UPDATED = "org.updated"
    ORG_DELETED = "org.deleted"
    ORG_MEMBER_ADDED = "org.member.added"
    ORG_MEMBER_REMOVED = "org.member.removed"
    ORG_MEMBER_ROLE_CHANGED = "org.member.role.changed"
    PERMISSION_CHANGED = "permission.changed"
    ROLE_CREATED = "role.created"
    ROLE_UPDATED = "role.updated"
    ROLE_DELETED = "role.deleted"
    SALESFORCE_CONNECTED = "salesforce.connected"
    SALESFORCE_DISCONNECTED = "salesforce.disconnected"
    SALESFORCE_SYNC_STARTED = "salesforce.sync.started"
    SALESFORCE_SYNC_COMPLETED = "salesforce.sync.completed"
    SALESFORCE_SYNC_FAILED = "salesforce.sync.failed"
    SEARCH_EXECUTED = "search.executed"
    IMPACT_ANALYSIS_RUN = "impact.analysis.run"
    DOCUMENTATION_GENERATED = "documentation.generated"
    ADMIN_ACTION = "admin.action"
    RATE_LIMIT_EXCEEDED = "rate.limit.exceeded"
    ABUSE_DETECTED = "abuse.detected"
    TENANT_ACCESS_DENIED = "tenant.access.denied"
    ENCRYPTION_KEY_ROTATED = "encryption.key.rotated"
    API_KEY_CREATED = "api.key.created"
    API_KEY_REVOKED = "api.key.revoked"
    SETTINGS_CHANGED = "settings.changed"
    SECURITY_POLICY_VIOLATED = "security.policy.violated"
    AUTH_METHOD_CHANGED = "auth.method.changed"


class AuditSeverity(enum.StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AuditCategory(enum.StrEnum):
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    ORGANIZATION = "organization"
    SALESFORCE = "salesforce"
    DATA_ACCESS = "data_access"
    CONFIGURATION = "configuration"
    SECURITY = "security"
    COMPLIANCE = "compliance"
    ADMINISTRATIVE = "administrative"
    SYSTEM = "system"


class RateLimitStrategy(enum.StrEnum):
    FIXED_WINDOW = "fixed_window"
    SLIDING_WINDOW = "sliding_window"
    TOKEN_BUCKET = "token_bucket"
    LEAKY_BUCKET = "leaky_bucket"


class SecurityPolicyEffect(enum.StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    AUDIT = "audit"


class EncryptionKeyStatus(enum.StrEnum):
    ACTIVE = "active"
    ROTATING = "rotating"
    RETIRED = "retired"
    COMPROMISED = "compromised"


class AbusePatternType(enum.StrEnum):
    BRUTE_FORCE = "brute_force"
    CREDENTIAL_STUFFING = "credential_stuffing"
    RAPID_FIRE = "rapid_fire"
    SCRAPING = "scraping"
    SUSPICIOUS_IP = "suspicious_ip"
    ANOMALOUS_BEHAVIOR = "anomalous_behavior"
    TOKEN_REUSE = "token_reuse"
    PARAMETER_TAMPERING = "parameter_tampering"


class TenantAccessValidation(enum.StrEnum):
    ALLOWED = "allowed"
    DENIED_CROSS_TENANT = "denied_cross_tenant"
    DENIED_NO_MEMBERSHIP = "denied_no_membership"
    DENIED_ORG_DISABLED = "denied_org_disabled"


@dataclass
class SecurityEvent:
    id: uuid.UUID
    event_type: SecurityEventType
    user_id: uuid.UUID | None = None
    organization_id: uuid.UUID | None = None
    ip_address: str = ""
    user_agent: str = ""
    resource_type: str = ""
    resource_id: str = ""
    details: dict | None = None
    severity: AuditSeverity = AuditSeverity.INFO
    category: AuditCategory = AuditCategory.SECURITY
    correlation_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @staticmethod
    def create(
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
    ) -> "SecurityEvent":
        return SecurityEvent(
            id=uuid.uuid4(),
            event_type=event_type,
            user_id=user_id,
            organization_id=organization_id,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            severity=severity,
            category=category,
            correlation_id=correlation_id,
        )


@dataclass
class AuditEntry:
    id: uuid.UUID
    action: SecurityEventType
    actor_id: uuid.UUID | None = None
    organization_id: uuid.UUID | None = None
    target_type: str = ""
    target_id: str = ""
    changes: dict | None = None
    ip_address: str = ""
    user_agent: str = ""
    severity: AuditSeverity = AuditSeverity.INFO
    category: AuditCategory = AuditCategory.SYSTEM
    outcome: str = "success"
    correlation_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @staticmethod
    def create(
        action: SecurityEventType,
        actor_id: uuid.UUID | None = None,
        organization_id: uuid.UUID | None = None,
        target_type: str = "",
        target_id: str = "",
        changes: dict | None = None,
        ip_address: str = "",
        user_agent: str = "",
        severity: AuditSeverity = AuditSeverity.INFO,
        category: AuditCategory = AuditCategory.SYSTEM,
        outcome: str = "success",
        correlation_id: str = "",
    ) -> "AuditEntry":
        return AuditEntry(
            id=uuid.uuid4(),
            action=action,
            actor_id=actor_id,
            organization_id=organization_id,
            target_type=target_type,
            target_id=target_id,
            changes=changes,
            ip_address=ip_address,
            user_agent=user_agent,
            severity=severity,
            category=category,
            outcome=outcome,
            correlation_id=correlation_id,
        )


@dataclass
class SecurityAlert:
    id: uuid.UUID
    title: str
    description: str
    severity: AuditSeverity
    event_type: SecurityEventType
    source_ip: str = ""
    user_id: uuid.UUID | None = None
    organization_id: uuid.UUID | None = None
    metadata: dict | None = None
    acknowledged: bool = False
    acknowledged_by: uuid.UUID | None = None
    acknowledged_at: datetime | None = None
    resolved: bool = False
    resolved_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def acknowledge(self, user_id: uuid.UUID) -> None:
        self.acknowledged = True
        self.acknowledged_by = user_id
        self.acknowledged_at = datetime.now(UTC)

    def resolve(self) -> None:
        self.resolved = True
        self.resolved_at = datetime.now(UTC)


@dataclass
class RateLimitRule:
    key: str
    max_requests: int
    window_seconds: int
    strategy: RateLimitStrategy = RateLimitStrategy.SLIDING_WINDOW
    group: str = "default"
    enabled: bool = True


@dataclass
class SecurityPolicyRule:
    id: uuid.UUID
    name: str
    effect: SecurityPolicyEffect
    resource_pattern: str
    action_pattern: str
    role_pattern: str = "*"
    organization_pattern: str = "*"
    conditions: dict | None = None
    priority: int = 100
    enabled: bool = True
    description: str = ""


@dataclass
class EncryptionKeyMetadata:
    id: uuid.UUID
    version: int
    algorithm: str
    status: EncryptionKeyStatus
    created_at: datetime
    rotated_at: datetime | None = None
    expires_at: datetime | None = None
    key_hash: str = ""


@dataclass
class AbusePattern:
    pattern_type: AbusePatternType
    criteria: dict
    threshold: int
    window_seconds: int
    action: str = "alert"


@dataclass
class TenantAccessResult:
    validation: TenantAccessValidation
    user_id: uuid.UUID
    organization_id: uuid.UUID
    resource_owner_org: uuid.UUID | None = None
    message: str = ""
