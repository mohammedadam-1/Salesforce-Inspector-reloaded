from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, UTC
from typing import Any

import structlog

from sfir_backend.domain.ai.models import (
    AIProviderType,
    CostEstimate,
    ProviderUsageStats,
    TokenUsage,
)

logger = structlog.get_logger(__name__)


PROVIDER_COST_PER_TOKEN: dict[str, dict[str, float]] = {
    "openai": {"prompt": 0.0000025, "completion": 0.00001},
    "anthropic": {"prompt": 0.000003, "completion": 0.000015},
    "gemini": {"prompt": 0.0000005, "completion": 0.0000015},
    "azure_openai": {"prompt": 0.0000025, "completion": 0.00001},
    "aws_bedrock": {"prompt": 0.000003, "completion": 0.000015},
    "ollama": {"prompt": 0.0, "completion": 0.0},
    "openrouter": {"prompt": 0.000002, "completion": 0.000008},
    "custom": {"prompt": 0.0000025, "completion": 0.00001},
}


class TokenManager:
    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    def truncate_to_limit(self, text: str, max_tokens: int) -> str:
        estimated = self.estimate_tokens(text)
        if estimated <= max_tokens:
            return text
        chars_per_token = 4
        max_chars = max_tokens * chars_per_token
        return text[:max_chars]


class CostTracker:
    def __init__(self) -> None:
        self._costs: dict[str, CostEstimate] = defaultdict(CostEstimate)

    def calculate_cost(
        self,
        provider: str | AIProviderType,
        token_usage: TokenUsage,
    ) -> CostEstimate:
        provider_key = str(provider)
        rates = PROVIDER_COST_PER_TOKEN.get(provider_key, {"prompt": 0.0, "completion": 0.0})
        prompt_cost = token_usage.prompt_tokens * rates["prompt"]
        completion_cost = token_usage.completion_tokens * rates["completion"]
        total_cost = prompt_cost + completion_cost

        estimate = CostEstimate(
            prompt_tokens=token_usage.prompt_tokens,
            completion_tokens=token_usage.completion_tokens,
            total_tokens=token_usage.total_tokens,
            prompt_cost=round(prompt_cost, 6),
            completion_cost=round(completion_cost, 6),
            total_cost=round(total_cost, 6),
        )
        self._costs[provider_key] = estimate
        return estimate

    def get_total_cost(self, provider: str | AIProviderType | None = None) -> float:
        if provider:
            return self._costs.get(str(provider), CostEstimate()).total_cost
        return sum(c.total_cost for c in self._costs.values())

    def reset(self) -> None:
        self._costs.clear()


class AIUsageTracker:
    def __init__(self) -> None:
        self._org_usage: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._user_usage: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._provider_stats: dict[str, ProviderUsageStats] = {}
        self._cost_tracker = CostTracker()
        self._token_manager = TokenManager()

    @property
    def cost_tracker(self) -> CostTracker:
        return self._cost_tracker

    @property
    def token_manager(self) -> TokenManager:
        return self._token_manager

    def track_request(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        provider: AIProviderType,
        token_usage: TokenUsage,
        latency_ms: float,
        success: bool = True,
    ) -> None:
        org_key = str(organization_id)
        user_key = str(user_id)
        provider_key = str(provider)

        self._org_usage[org_key]["total_requests"] += 1
        self._org_usage[org_key]["total_tokens"] += token_usage.total_tokens
        self._user_usage[user_key]["total_requests"] += 1
        self._user_usage[user_key]["total_tokens"] += token_usage.total_tokens

        self._cost_tracker.calculate_cost(provider, token_usage)

        stats = self._provider_stats.setdefault(
            provider_key,
            ProviderUsageStats(provider_type=provider),
        )
        stats.total_requests += 1
        stats.total_tokens += token_usage.total_tokens
        stats.total_cost += self._cost_tracker.get_total_cost(provider)
        if success:
            stats.success_count += 1
        else:
            stats.failure_count += 1
        stats.avg_latency_ms = (
            (stats.avg_latency_ms * (stats.total_requests - 1) + latency_ms)
            / stats.total_requests
        )
        stats.last_request_at = datetime.now(UTC)

        logger.info(
            "ai_request_tracked",
            org_id=org_key,
            user_id=user_key,
            provider=provider_key,
            tokens=token_usage.total_tokens,
            latency_ms=latency_ms,
            success=success,
        )

    def get_org_usage(self, organization_id: uuid.UUID) -> dict[str, int]:
        return dict(self._org_usage.get(str(organization_id), {}))

    def get_user_usage(self, user_id: uuid.UUID) -> dict[str, int]:
        return dict(self._user_usage.get(str(user_id), {}))

    def get_provider_stats(self, provider: str | AIProviderType | None = None) -> list[dict[str, Any]]:
        if provider:
            stats = self._provider_stats.get(str(provider))
            if not stats:
                return []
            return [{
                "provider": stats.provider_type,
                "total_requests": stats.total_requests,
                "total_tokens": stats.total_tokens,
                "total_cost": round(stats.total_cost, 6),
                "success_count": stats.success_count,
                "failure_count": stats.failure_count,
                "avg_latency_ms": round(stats.avg_latency_ms, 2),
                "last_request": stats.last_request_at.isoformat() if stats.last_request_at else None,
            }]
        return [
            {
                "provider": stats.provider_type,
                "total_requests": stats.total_requests,
                "total_tokens": stats.total_tokens,
                "total_cost": round(stats.total_cost, 6),
                "success_count": stats.success_count,
                "failure_count": stats.failure_count,
                "avg_latency_ms": round(stats.avg_latency_ms, 2),
                "last_request": stats.last_request_at.isoformat() if stats.last_request_at else None,
            }
            for stats in self._provider_stats.values()
        ]
