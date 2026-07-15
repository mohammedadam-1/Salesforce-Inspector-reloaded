import uuid

import pytest

from sfir_backend.config.settings import Settings
from sfir_backend.domain.security.models import RateLimitRule
from sfir_backend.infrastructure.security.rate_limiter import RateLimiter
from sfir_backend.shared.exceptions.application import RateLimitExceededError


class TestRateLimiter:
    def setup_method(self) -> None:
        self.settings = Settings(
            environment="testing",
            rate_limit_default=5,
            rate_limit_window_seconds=60,
        )
        self.limiter = RateLimiter(self.settings)

    async def test_default_rules_loaded(self) -> None:
        assert "default" in self.limiter._rules
        assert "ai" in self.limiter._rules
        assert "deployment" in self.limiter._rules

    async def test_check_rate_limit_allows(self) -> None:
        await self.limiter.check_rate_limit(
            key="test", user_id=uuid.uuid4(), group="default",
        )

    async def test_add_rule(self) -> None:
        rule = RateLimitRule(
            key="custom", max_requests=10, window_seconds=30, group="custom",
        )
        self.limiter.add_rule(rule)
        assert "custom" in self.limiter._rules

    async def test_remove_rule(self) -> None:
        self.limiter.remove_rule("ai")
        assert "ai" not in self.limiter._rules

    async def test_rate_limit_exceeded(self) -> None:
        user_id = uuid.uuid4()

        rule = RateLimitRule(
            key="strict", max_requests=2, window_seconds=60, group="strict",
        )
        self.limiter.add_rule(rule)

        await self.limiter.check_rate_limit(
            key="strict-test", user_id=user_id, group="strict",
        )
        await self.limiter.check_rate_limit(
            key="strict-test", user_id=user_id, group="strict",
        )

        with pytest.raises(RateLimitExceededError):
            await self.limiter.check_rate_limit(
                key="strict-test", user_id=user_id, group="strict",
            )

    async def test_different_keys_independent(self) -> None:
        user_id = uuid.uuid4()

        rule = RateLimitRule(
            key="limited", max_requests=1, window_seconds=60, group="limited",
        )
        self.limiter.add_rule(rule)

        await self.limiter.check_rate_limit(
            key="key-a", user_id=user_id, group="limited",
        )

        with pytest.raises(RateLimitExceededError):
            await self.limiter.check_rate_limit(
                key="key-a", user_id=user_id, group="limited",
            )

        await self.limiter.check_rate_limit(
            key="key-b", user_id=user_id, group="limited",
        )

    async def test_disabled_rule_allows_all(self) -> None:
        rule = RateLimitRule(
            key="disabled", max_requests=0, window_seconds=60,
            group="disabled", enabled=False,
        )
        self.limiter.add_rule(rule)
        await self.limiter.check_rate_limit(
            key="any", user_id=uuid.uuid4(), group="disabled",
        )
