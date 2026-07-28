import uuid
from datetime import datetime, UTC
from sfir_backend.domain.ai.models import (
    AIFeature,
    AIProviderType,
    AIRequest,
    AIResponse,
    AIStreamChunk,
    CacheEntry,
    Citation,
    CitationSourceType,
    Conversation,
    ConversationMessage,
    CostEstimate,
    ProviderConfig,
    SafetyCheckResult,
    TokenUsage,
)


class TestAIFeature:
    def test_values(self) -> None:
        assert AIFeature.EXPLAIN_APEX.value == "explain_apex"
        assert AIFeature.NATURAL_LANGUAGE_SEARCH.value == "natural_language_search"
        assert AIFeature.QUESTION_ANSWERING.value == "question_answering"


class TestAIProviderType:
    def test_values(self) -> None:
        assert AIProviderType.OPENAI.value == "openai"
        assert AIProviderType.ANTHROPIC.value == "anthropic"
        assert AIProviderType.GEMINI.value == "gemini"


class TestCitation:
    def test_create(self) -> None:
        c = Citation(
            source_type=CitationSourceType.METADATA,
            source_id="01pXXX",
            source_name="Account.object",
        )
        assert c.source_type == CitationSourceType.METADATA
        assert c.source_id == "01pXXX"

    def test_to_dict(self) -> None:
        c = Citation(
            source_type=CitationSourceType.DEPENDENCY,
            source_id="dep1",
            source_name="TestDep",
        )
        d = c.to_dict()
        assert d["source_type"] == "dependency"
        assert d["source_name"] == "TestDep"


class TestTokenUsage:
    def test_defaults(self) -> None:
        t = TokenUsage()
        assert t.prompt_tokens == 0
        assert t.total_tokens == 0

    def test_to_dict(self) -> None:
        t = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150, estimated_cost=0.002)
        d = t.to_dict()
        assert d["prompt_tokens"] == 100
        assert d["estimated_cost"] == 0.002


class TestCostEstimate:
    def test_create(self) -> None:
        c = CostEstimate(prompt_tokens=100, completion_tokens=50, total_cost=0.003)
        assert c.total_cost == 0.003


class TestAIRequest:
    def test_create(self) -> None:
        org_id = uuid.uuid4()
        user_id = uuid.uuid4()
        req = AIRequest(
            feature=AIFeature.EXPLAIN_APEX,
            query="Explain this class",
            organization_id=org_id,
            user_id=user_id,
        )
        assert req.feature == AIFeature.EXPLAIN_APEX
        assert req.temperature == 0.1
        assert req.request_id is not None

    def test_to_dict(self) -> None:
        req = AIRequest(
            feature=AIFeature.QUESTION_ANSWERING,
            query="test",
            organization_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
        )
        d = req.to_dict()
        assert d["query"] == "test"
        assert d["stream"] is False


class TestAIResponse:
    def test_create(self) -> None:
        resp = AIResponse(
            request_id=uuid.uuid4(),
            content="Test response",
        )
        assert resp.content == "Test response"
        assert resp.finish_reason == "stop"
        assert len(resp.citations) == 0

    def test_to_dict(self) -> None:
        resp = AIResponse(
            request_id=uuid.uuid4(),
            content="Hello",
            provider=AIProviderType.ANTHROPIC,
        )
        d = resp.to_dict()
        assert d["provider"] == "anthropic"
        assert d["content"] == "Hello"


class TestAIStreamChunk:
    def test_create(self) -> None:
        chunk = AIStreamChunk(request_id=uuid.uuid4(), content="Hello")
        assert not chunk.done
        chunk2 = AIStreamChunk(request_id=uuid.uuid4(), content="", done=True)
        assert chunk2.done


class TestConversation:
    def test_add_message(self) -> None:
        conv = Conversation(
            conversation_id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
        )
        assert len(conv.messages) == 0
        msg = ConversationMessage(role="user", content="Hello")
        conv.add_message(msg)
        assert len(conv.messages) == 1
        assert conv.messages[0].role == "user"

    def test_to_dict(self) -> None:
        conv = Conversation(
            conversation_id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            title="Test",
        )
        d = conv.to_dict()
        assert d["title"] == "Test"
        assert d["message_count"] == 0


class TestSafetyCheckResult:
    def test_passed(self) -> None:
        r = SafetyCheckResult(passed=True)
        assert r.passed
        assert r.reason is None

    def test_failed(self) -> None:
        r = SafetyCheckResult(passed=False, reason="Blocked", categories=["test"], score=0.9)
        assert not r.passed
        assert r.reason == "Blocked"


class TestProviderConfig:
    def test_create(self) -> None:
        c = ProviderConfig(provider_type=AIProviderType.OPENAI)
        assert c.model == "gpt-4o"
        assert c.enabled


class TestCacheEntry:
    def test_create(self) -> None:
        e = CacheEntry(key="test-key", response="cached response")
        assert e.hit_count == 0
        assert e.ttl_seconds == 300
