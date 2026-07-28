from __future__ import annotations

import fnmatch
import uuid

from sfir_backend.domain.security.models import (
    AuditCategory,
    AuditSeverity,
    SecurityEventType,
    SecurityPolicyEffect,
    SecurityPolicyRule,
)
from sfir_backend.infrastructure.security.audit_engine import AuditEngine


class SecurityPolicyEngine:
    def __init__(
        self,
        audit_engine: AuditEngine | None = None,
    ) -> None:
        self._audit_engine = audit_engine
        self._rules: list[SecurityPolicyRule] = []
        self._register_default_rules()

    def _register_default_rules(self) -> None:
        self.add_rule(SecurityPolicyRule(
            id=uuid.uuid4(),
            name="allow-owner-all",
            effect=SecurityPolicyEffect.ALLOW,
            resource_pattern="*",
            action_pattern="*",
            role_pattern="owner",
            priority=10,
            description="Owners can do everything",
        ))
        self.add_rule(SecurityPolicyRule(
            id=uuid.uuid4(),
            name="deny-cross-tenant-access",
            effect=SecurityPolicyEffect.DENY,
            resource_pattern="org:*",
            action_pattern="*",
            organization_pattern="*",
            priority=1,
            description="Cross-tenant access is denied by default",
        ))
        self.add_rule(SecurityPolicyRule(
            id=uuid.uuid4(),
            name="audit-admin-actions",
            effect=SecurityPolicyEffect.AUDIT,
            resource_pattern="org:*:settings",
            action_pattern="update",
            role_pattern="admin",
            priority=50,
            description="Admin settings changes are audited",
        ))

    def add_rule(self, rule: SecurityPolicyRule) -> None:
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority)

    def remove_rule(self, rule_id: uuid.UUID) -> None:
        self._rules = [r for r in self._rules if r.id != rule_id]

    def evaluate(
        self,
        action: str,
        resource: str,
        role: str = "",
        organization_id: uuid.UUID | None = None,
        _user_id: uuid.UUID | None = None,
    ) -> SecurityPolicyEffect:
        org_str = str(organization_id) if organization_id else "*"

        for rule in self._rules:
            if not rule.enabled:
                continue
            if not fnmatch.fnmatch(resource, rule.resource_pattern):
                continue
            if not fnmatch.fnmatch(action, rule.action_pattern):
                continue
            if not fnmatch.fnmatch(role, rule.role_pattern):
                continue
            if not fnmatch.fnmatch(org_str, rule.organization_pattern):
                continue

            if rule.effect == SecurityPolicyEffect.DENY:
                return SecurityPolicyEffect.DENY
            if rule.effect == SecurityPolicyEffect.AUDIT:
                return SecurityPolicyEffect.AUDIT

        return SecurityPolicyEffect.ALLOW

    async def check_access(
        self,
        action: str,
        resource: str,
        role: str = "",
        organization_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> bool:
        effect = self.evaluate(action, resource, role, organization_id, user_id)

        if effect == SecurityPolicyEffect.AUDIT and self._audit_engine:
            await self._audit_engine.record_event(
                event_type=SecurityEventType.SECURITY_POLICY_VIOLATED,
                actor_id=user_id,
                organization_id=organization_id,
                target_type=resource,
                details={"action": action, "role": role, "effect": effect.value},
                severity=AuditSeverity.INFO,
                category=AuditCategory.SECURITY,
            )

        return effect != SecurityPolicyEffect.DENY

    def get_rules(
        self,
        enabled_only: bool = True,
    ) -> list[SecurityPolicyRule]:
        if enabled_only:
            return [r for r in self._rules if r.enabled]
        return list(self._rules)

    def clear_rules(self) -> None:
        self._rules.clear()
