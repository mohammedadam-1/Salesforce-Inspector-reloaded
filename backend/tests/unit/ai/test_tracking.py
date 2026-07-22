import uuid
from sfir_backend.domain.ai.models import AIProviderType, TokenUsage
from sfir_backend.infrastructure.llm.tracking import AIUsageTracker, CostTracker, TokenManager


class TestTokenManager:
    def test_estimate_tokens(self) -> None:
        mgr = TokenManager()
        estimate = mgr.estimate_tokens("Hello world")
        assert estimate > 0

    def test_truncate_to_limit(self) -> None:
        mgr = TokenManager()
        text = "Hello world this is a test " * 100
        truncated = mgr.truncate_to_limit(text, max_tokens=10)
        assert len(truncated) < len(text)


class TestCostTracker:
    def setup_method(self) -> None:
        self.tracker = CostTracker()

    def test_calculate_cost_openai(self) -> None:
        usage = TokenUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        cost = self.tracker.calculate_cost(AIProviderType.OPENAI, usage)
        assert cost.total_tokens == 1500
        assert cost.total_cost > 0

    def test_calculate_cost_ollama_free(self) -> None:
        usage = TokenUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        cost = self.tracker.calculate_cost(AIProviderType.OLLAMA, usage)
        assert cost.total_cost == 0.0

    def test_get_total_cost(self) -> None:
        usage = TokenUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        self.tracker.calculate_cost(AIProviderType.OPENAI, usage)
        assert self.tracker.get_total_cost() > 0

    def test_reset(self) -> None:
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        self.tracker.calculate_cost(AIProviderType.OPENAI, usage)
        self.tracker.reset()
        assert self.tracker.get_total_cost() == 0.0


class TestAIUsageTracker:
    def setup_method(self) -> None:
        self.tracker = AIUsageTracker()

    def test_track_request(self) -> None:
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        self.tracker.track_request(org_id, user_id, AIProviderType.OPENAI, usage, 500.0)
        org_usage = self.tracker.get_org_usage(org_id)
        assert org_usage["total_requests"] == 1
        assert org_usage["total_tokens"] == 150

    def test_track_multiple_requests(self) -> None:
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        for _ in range(3):
            self.tracker.track_request(
                org_id, user_id, AIProviderType.OPENAI,
                TokenUsage(total_tokens=100), 200.0,
            )
        assert self.tracker.get_org_usage(org_id)["total_requests"] == 3

    def test_get_user_usage(self) -> None:
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        self.tracker.track_request(org_id, user_id, AIProviderType.ANTHROPIC, TokenUsage(total_tokens=50), 100.0)
        user_usage = self.tracker.get_user_usage(user_id)
        assert user_usage["total_requests"] == 1

    def test_get_provider_stats(self) -> None:
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        self.tracker.track_request(org_id, user_id, AIProviderType.OPENAI, TokenUsage(total_tokens=100), 200.0)
        stats = self.tracker.get_provider_stats()
        assert len(stats) >= 1

    def test_get_provider_stats_filtered(self) -> None:
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        self.tracker.track_request(org_id, user_id, AIProviderType.OPENAI, TokenUsage(total_tokens=100), 200.0)
        stats = self.tracker.get_provider_stats(AIProviderType.OPENAI)
        assert len(stats) == 1
        assert stats[0]["total_requests"] == 1

    def test_track_failure(self) -> None:
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        self.tracker.track_request(org_id, user_id, AIProviderType.OPENAI, TokenUsage(), 100.0, success=False)
        stats = self.tracker.get_provider_stats(AIProviderType.OPENAI)
        assert stats[0]["failure_count"] == 1
