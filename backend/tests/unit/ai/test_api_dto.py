import uuid
from datetime import datetime, UTC
from sfir_backend.api.dto.ai import (
    AIResponseDTO,
    ChatRequest,
    CitationDTO,
    ExplainRequest,
    ProviderDTO,
    SummarizeRequest,
    TokenUsageDTO,
    UsageDTO,
)


class TestChatRequest:
    def test_valid(self) -> None:
        r = ChatRequest(query="Hello")
        assert r.query == "Hello"
        assert r.max_tokens == 4096
        assert r.stream is False

    def test_default_feature(self) -> None:
        r = ChatRequest(query="test")
        assert r.feature == "question_answering"


class TestExplainRequest:
    def test_valid(self) -> None:
        r = ExplainRequest(feature="explain_apex", query="Explain code")
        assert r.feature == "explain_apex"
        assert r.context == {}


class TestSummarizeRequest:
    def test_valid(self) -> None:
        r = SummarizeRequest(feature="summarize_dependency_graph", data="graph data")
        assert r.data == "graph data"


class TestCitationDTO:
    def test_create(self) -> None:
        c = CitationDTO(
            source_type="metadata",
            source_id="id1",
            source_name="Name",
        )
        assert c.source_type == "metadata"
        assert c.relevance == 1.0


class TestTokenUsageDTO:
    def test_defaults(self) -> None:
        t = TokenUsageDTO()
        assert t.prompt_tokens == 0
        assert t.total_tokens == 0


class TestAIResponseDTO:
    def test_create(self) -> None:
        r = AIResponseDTO(
            request_id=str(uuid.uuid4()),
            content="Response content",
        )
        assert r.content == "Response content"
        assert r.finish_reason == "stop"

    def test_with_citations(self) -> None:
        r = AIResponseDTO(
            request_id=str(uuid.uuid4()),
            content="Content",
            citations=[
                CitationDTO(source_type="metadata", source_id="id1", source_name="N1"),
            ],
        )
        assert len(r.citations) == 1


class TestProviderDTO:
    def test_create(self) -> None:
        p = ProviderDTO(name="openai", type="openai")
        assert p.name == "openai"


class TestUsageDTO:
    def test_create(self) -> None:
        u = UsageDTO(
            providers=[{"openai": {"total_requests": 10}}],
            costs={"total": 0.05},
        )
        assert len(u.providers) == 1
