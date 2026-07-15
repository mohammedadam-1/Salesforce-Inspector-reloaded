import uuid

from sfir_backend.domain.security.models import (
    SecurityPolicyEffect,
    SecurityPolicyRule,
)
from sfir_backend.infrastructure.security.security_policy_engine import (
    SecurityPolicyEngine,
)


class TestSecurityPolicyEngine:
    def setup_method(self) -> None:
        self.engine = SecurityPolicyEngine()

    def test_default_rules_exist(self) -> None:
        rules = self.engine.get_rules()
        assert len(rules) >= 3

    def test_evaluate_allow_by_default(self) -> None:
        effect = self.engine.evaluate(
            action="search:execute",
            resource="search",
            role="viewer",
        )
        assert effect == SecurityPolicyEffect.ALLOW

    def test_evaluate_deny_for_unknown(self) -> None:
        self.engine.add_rule(SecurityPolicyRule(
            id=uuid.uuid4(),
            name="deny-all",
            effect=SecurityPolicyEffect.DENY,
            resource_pattern="*",
            action_pattern="*",
            priority=1,
        ))
        effect = self.engine.evaluate(
            action="anything", resource="anything",
        )
        assert effect == SecurityPolicyEffect.DENY

    async def test_check_access_allowed(self) -> None:
        result = await self.engine.check_access(
            action="view", resource="docs", role="viewer",
        )
        assert result is True

    async def test_check_access_denied(self) -> None:
        self.engine.add_rule(SecurityPolicyRule(
            id=uuid.uuid4(),
            name="deny-docs",
            effect=SecurityPolicyEffect.DENY,
            resource_pattern="docs",
            action_pattern="delete",
            priority=0,
        ))
        result = await self.engine.check_access(
            action="delete", resource="docs", role="viewer",
        )
        assert result is False

    def test_policy_rule_priority(self) -> None:
        self.engine.clear_rules()
        self.engine.add_rule(SecurityPolicyRule(
            id=uuid.uuid4(),
            name="deny-first",
            effect=SecurityPolicyEffect.DENY,
            resource_pattern="*",
            action_pattern="*",
            priority=1,
        ))
        self.engine.add_rule(SecurityPolicyRule(
            id=uuid.uuid4(),
            name="allow-second",
            effect=SecurityPolicyEffect.ALLOW,
            resource_pattern="*",
            action_pattern="*",
            priority=10,
        ))
        effect = self.engine.evaluate(
            action="test", resource="test",
        )
        assert effect == SecurityPolicyEffect.DENY

    def test_remove_rule(self) -> None:
        rule_id = uuid.uuid4()
        self.engine.add_rule(SecurityPolicyRule(
            id=rule_id, name="test", effect=SecurityPolicyEffect.DENY,
            resource_pattern="*", action_pattern="*",
        ))
        self.engine.remove_rule(rule_id)
        rule_ids = [r.id for r in self.engine.get_rules()]
        assert rule_id not in rule_ids

    def test_disabled_rule_skipped(self) -> None:
        self.engine.add_rule(SecurityPolicyRule(
            id=uuid.uuid4(),
            name="disabled-deny",
            effect=SecurityPolicyEffect.DENY,
            resource_pattern="*",
            action_pattern="*",
            enabled=False,
            priority=1,
        ))
        effect = self.engine.evaluate(
            action="anything", resource="anything",
        )
        assert effect != SecurityPolicyEffect.DENY
