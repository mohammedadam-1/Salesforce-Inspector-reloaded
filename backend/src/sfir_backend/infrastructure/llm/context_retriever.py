from __future__ import annotations

import uuid
from typing import Any

import structlog

from sfir_backend.domain.ai.models import Citation, CitationSourceType

logger = structlog.get_logger(__name__)


class ContextRetriever:
    def __init__(self) -> None:
        self._retrievers: dict[str, Any] = {}

    def register_retriever(self, name: str, retriever: Any) -> None:
        self._retrievers[name] = retriever

    async def retrieve_metadata(
        self,
        organization_id: uuid.UUID,
        query: str,
        limit: int = 20,
    ) -> tuple[str, list[Citation]]:
        metadata_service = self._retrievers.get("metadata")
        if not metadata_service:
            return "Metadata context unavailable.", []
        try:
            results = await metadata_service.search_metadata(
                organization_id=organization_id,
                query=query,
                limit=limit,
            )
            citations = []
            lines = []
            for item in results:
                citations.append(Citation(
                    source_type=CitationSourceType.METADATA,
                    source_id=item.get("id", ""),
                    source_name=item.get("name", ""),
                ))
                lines.append(f"- {item.get('type', '?')}: {item.get('name', '?')}")
            return "\n".join(lines), citations
        except Exception as e:
            logger.error("metadata_retrieval_failed", error=str(e))
            return "Metadata retrieval failed.", []

    async def retrieve_dependency_graph(
        self,
        organization_id: uuid.UUID,
        component_type: str | None = None,
        component_name: str | None = None,
    ) -> tuple[str, list[Citation]]:
        graph_service = self._retrievers.get("dependency_graph")
        if not graph_service:
            return "Dependency graph unavailable.", []
        try:
            if component_type and component_name:
                result = await graph_service.get_dependency_summary(
                    organization_id, component_type, component_name,
                )
            else:
                result = await graph_service.get_graph_summary(organization_id)
            citations = []
            for node in result.get("nodes", []):
                citations.append(Citation(
                    source_type=CitationSourceType.DEPENDENCY,
                    source_id=node.get("id", ""),
                    source_name=node.get("name", ""),
                ))
            return result.get("summary", "No graph data."), citations
        except Exception as e:
            logger.error("graph_retrieval_failed", error=str(e))
            return "Dependency graph retrieval failed.", []

    async def retrieve_impact_analysis(
        self,
        organization_id: uuid.UUID,
        analysis_id: uuid.UUID,
    ) -> tuple[str, list[Citation]]:
        impact_service = self._retrievers.get("impact_analysis")
        if not impact_service:
            return "Impact analysis unavailable.", []
        try:
            report = await impact_service.get_report(organization_id, analysis_id)
            citations = []
            for component in report.get("impacted_components", []):
                citations.append(Citation(
                    source_type=CitationSourceType.IMPACT_REPORT,
                    source_id=component.get("id", ""),
                    source_name=component.get("name", ""),
                ))
            return report.get("summary", "No impact data."), citations
        except Exception as e:
            logger.error("impact_retrieval_failed", error=str(e))
            return "Impact analysis retrieval failed.", []

    async def retrieve_documentation(
        self,
        organization_id: uuid.UUID,
        component_type: str | None = None,
        component_name: str | None = None,
    ) -> tuple[str, list[Citation]]:
        doc_service = self._retrievers.get("documentation")
        if not doc_service:
            return "Documentation unavailable.", []
        try:
            if component_type and component_name:
                docs = await doc_service.get_documentation(
                    organization_id, component_type, component_name,
                )
            else:
                docs = await doc_service.list_documentation(organization_id)
            citations = []
            lines = []
            for doc in docs:
                citations.append(Citation(
                    source_type=CitationSourceType.DOCUMENTATION,
                    source_id=doc.get("id", ""),
                    source_name=doc.get("title", ""),
                ))
                lines.append(f"- {doc.get('title', 'Untitled')}")
            return "\n".join(lines), citations
        except Exception as e:
            logger.error("documentation_retrieval_failed", error=str(e))
            return "Documentation retrieval failed.", []

    async def retrieve_search_results(
        self,
        organization_id: uuid.UUID,
        query: str,
        limit: int = 20,
    ) -> tuple[str, list[Citation]]:
        search_service = self._retrievers.get("search")
        if not search_service:
            return "Search unavailable.", []
        try:
            results = await search_service.search(
                organization_id=organization_id,
                query=query,
                limit=limit,
            )
            citations = []
            lines = []
            for item in results.get("items", []):
                citations.append(Citation(
                    source_type=CitationSourceType.SEARCH_RESULT,
                    source_id=item.get("id", ""),
                    source_name=item.get("name", ""),
                    relevance=item.get("score", 1.0),
                ))
                lines.append(f"- {item.get('type', '?')}: {item.get('name', '?')} (score: {item.get('score', 0):.2f})")
            return "\n".join(lines), citations
        except Exception as e:
            logger.error("search_retrieval_failed", error=str(e))
            return "Search retrieval failed.", []

    async def retrieve_all_context(
        self,
        organization_id: uuid.UUID,
        query: str,
    ) -> tuple[str, list[Citation]]:
        all_citations: list[Citation] = []
        context_parts: list[str] = []

        metadata_text, metadata_citations = await self.retrieve_metadata(
            organization_id, query,
        )
        if metadata_text:
            context_parts.append(metadata_text)
            all_citations.extend(metadata_citations)

        search_text, search_citations = await self.retrieve_search_results(
            organization_id, query,
        )
        if search_text:
            context_parts.append(search_text)
            all_citations.extend(search_citations)

        combined = "\n\n".join(context_parts)
        return combined, all_citations


class ContextCompressor:
    def __init__(self, max_tokens: int = 8000) -> None:
        self._max_tokens = max_tokens

    def compress(self, context: str, citations: list[Citation]) -> tuple[str, list[Citation]]:
        estimated_tokens = len(context) // 4
        if estimated_tokens <= self._max_tokens:
            return context, citations

        paragraphs = context.split("\n\n")
        compressed_paragraphs: list[str] = []
        compressed_citations: list[Citation] = []
        seen_ids: set[str] = set()
        current_tokens = 0

        for para in paragraphs:
            para_tokens = len(para) // 4
            if current_tokens + para_tokens > self._max_tokens:
                break
            compressed_paragraphs.append(para)
            current_tokens += para_tokens

        for citation in citations:
            if citation.source_id not in seen_ids:
                compressed_citations.append(citation)
                seen_ids.add(citation.source_id)

        logger.info(
            "context_compressed",
            original_tokens=estimated_tokens,
            compressed_tokens=current_tokens,
            original_citations=len(citations),
            compressed_citations=len(compressed_citations),
        )
        return "\n\n".join(compressed_paragraphs), compressed_citations
