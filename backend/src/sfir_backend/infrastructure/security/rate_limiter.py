from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from typing import Any

from sfir_backend.application.cache.services import RateLimitCacheService
from sfir_backend.config.settings import Settings
from sfir_backend.domain.security.models import (
    RateLimitRule,
)
from sfir_backend.shared.exceptions.application import RateLimitExceededError


class RateLimiter:
    def __init__(
        self,
        settings: Settings,
        cache_service: RateLimitCacheService | None = None,
    ) -> None:
        self._settings = settings
        self._cache = cache_service
        self._rules: dict[str, RateLimitRule] = {}
        self._in_memory_counts: dict[str, list[float]] = {}

        self._add_default_rules()

    def _add_default_rules(self) -> None:
        self.add_rule(RateLimitRule(
            key="default",
            max_requests=self._settings.rate_limit_default,
            window_seconds=self._settings.rate_limit_window_seconds,
            group="default",
        ))
        self.add_rule(RateLimitRule(
            key="ai",
            max_requests=self._settings.rate_limit_ai_per_minute,
            window_seconds=60,
            group="ai",
        ))
        self.add_rule(RateLimitRule(
            key="deployment",
            max_requests=self._settings.rate_limit_deployment_per_minute,
            window_seconds=60,
            group="deployment",
        ))

    def add_rule(self, rule: RateLimitRule) -> None:
        self._rules[rule.key] = rule

    def remove_rule(self, key: str) -> None:
        self._rules.pop(key, None)

    async def check_rate_limit(
        self,
        key: str,
        user_id: uuid.UUID | None = None,
        ip_address: str = "",
        group: str = "default",
    ) -> None:
        rule = self._get_rule_for_group(group)
        if not rule or not rule.enabled:
            return

        limiter_key = self._build_key(key, user_id, ip_address, group)
        current_count = await self._get_count(limiter_key, rule)

        if current_count >= rule.max_requests:
            retry_after = self._compute_retry_after(limiter_key, rule)
            raise RateLimitExceededError(
                message=f"Rate limit exceeded for {group}",
                retry_after=retry_after,
            )

        await self._increment(limiter_key, rule)

    async def _get_count(self, key: str, rule: RateLimitRule) -> int:
        if self._cache:
            cached = await self._cache.get_rate_limit(key)
            if cached is not None:
                return cached
            return 0

        now = time.time()
        window_start = now - rule.window_seconds
        timestamps = self._in_memory_counts.get(key, [])
        valid = [t for t in timestamps if t > window_start]
        self._in_memory_counts[key] = valid
        return len(valid)

    async def _increment(self, key: str, rule: RateLimitRule) -> None:
        if self._cache:
            await self._cache.increment_rate_limit(key, rule.window_seconds)

        now = time.time()
        if key not in self._in_memory_counts:
            self._in_memory_counts[key] = []
        self._in_memory_counts[key].append(now)

    def _get_rule_for_group(self, group: str) -> RateLimitRule | None:
        for rule in self._rules.values():
            if rule.group == group and rule.enabled:
                return rule
        return self._rules.get("default")

    def _build_key(
        self,
        key: str,
        user_id: uuid.UUID | None,
        ip_address: str,
        group: str,
    ) -> str:
        identifier = str(user_id) if user_id else ip_address
        return f"ratelimit:{group}:{key}:{identifier}"

    def _compute_retry_after(self, key: str, rule: RateLimitRule) -> int:
        timestamps = self._in_memory_counts.get(key, [])
        if not timestamps:
            return 0
        oldest = min(timestamps)
        remaining = int(rule.window_seconds - (time.time() - oldest))
        return max(remaining, 0)


def rate_limit(
    group: str = "default",
    key_builder: Callable[[Any], str] | None = None,
) -> Callable[..., Any]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            rate_limiter: RateLimiter | None = getattr(self, "_rate_limiter", None)
            user_id: uuid.UUID | None = getattr(self, "_user_id", None)
            ip: str = getattr(self, "_ip_address", "")

            if rate_limiter:
                key = key_builder(kwargs) if key_builder else func.__name__
                await rate_limiter.check_rate_limit(
                    key=key,
                    user_id=user_id,
                    ip_address=ip,
                    group=group,
                )

            return await func(self, *args, **kwargs)
        return wrapper
    return decorator
