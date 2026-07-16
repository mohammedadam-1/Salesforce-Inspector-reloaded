import uuid
import pytest
from sfir_backend.infrastructure.llm.context_retriever import (
    ContextCompressor,
    ContextRetriever,
)
from sfir_backend.domain.ai.models import Citation, CitationSourceType


class TestContextRetriever:
    @pytest.mark.asyncio
    async def test_retrieve_metadata_no_service(self) -> None:
        retriever = ContextRetriever()
        text, citations = await retriever.retrieve_metadata(uuid.uuid4(), "test")
        assert "unavailable" in text
        assert len(citations) == 0

    @pytest.mark.asyncio
    async def test_retrieve_graph_no_service(self) -> None:
        retriever = ContextRetriever()
        text, citations = await retriever.retrieve_dependency_graph(uuid.uuid4())
        assert "unavailable" in text

    @pytest.mark.asyncio
    async def test_retrieve_impact_no_service(self) -> None:
        retriever = ContextRetriever()
        text, citations = await retriever.retrieve_impact_analysis(uuid.uuid4(), uuid.uuid4())
        assert "unavailable" in text

    @pytest.mark.asyncio
    async def test_retrieve_documentation_no_service(self) -> None:
        retriever = ContextRetriever()
        text, citations = await retriever.retrieve_documentation(uuid.uuid4())
        assert "unavailable" in text

    @pytest.mark.asyncio
    async def test_retrieve_search_no_service(self) -> None:
        retriever = ContextRetriever()
        text, citations = await retriever.retrieve_search_results(uuid.uuid4(), "test")
        assert "unavailable" in text

    @pytest.mark.asyncio
    async def test_retrieve_all_context_no_services(self) -> None:
        retriever = ContextRetriever()
        text, citations = await retriever.retrieve_all_context(uuid.uuid4(), "test")
        assert text == "" or "unavailable" in text


class TestContextCompressor:
    def test_no_compression_needed(self) -> None:
        compressor = ContextCompressor(max_tokens=8000)
        text = "Short text"
        citations = [Citation(source_type=CitationSourceType.METADATA, source_id="1", source_name="Test")]
        compressed_text, compressed_citations = compressor.compress(text, citations)
        assert compressed_text == text
        assert len(compressed_citations) == 1

    def test_compression_truncates(self) -> None:
        compressor = ContextCompressor(max_tokens=5)
        text = "\n\n".join([f"Paragraph {i} " * 20 for i in range(100)])
        citations = [
            Citation(source_type=CitationSourceType.METADATA, source_id=str(i), source_name=f"Test{i}")
            for i in range(100)
        ]
        compressed_text, compressed_citations = compressor.compress(text, citations)
        assert len(compressed_text) < len(text)
        assert len(compressed_citations) <= len(citations)
