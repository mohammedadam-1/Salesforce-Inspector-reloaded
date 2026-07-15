from __future__ import annotations

import re
from typing import Any

import structlog

from sfir_backend.domain.ai.models import Citation, CitationSourceType

logger = structlog.get_logger(__name__)


class CitationGenerator:
    def __init__(self) -> None:
        self._source_registry: dict[str, Any] = {}

    def register_source_lookup(self, source_type: str, lookup_fn: Any) -> None:
        self._source_registry[source_type] = lookup_fn

    def extract_citations_from_response(self, response: str, context_citations: list[Citation]) -> list[Citation]:
        citations: list[Citation] = []
        seen_ids: set[str] = set()

        # Extract reference IDs from response text (e.g. [metadata:123], [dep:abc])
        for match in re.finditer(r"\[(\w+):([^\]]+)\]", response):
            source_type_str = match.group(1)
            source_id = match.group(2).strip()
            try:
                source_type = CitationSourceType(source_type_str)
                if source_id not in seen_ids:
                    citations.append(Citation(
                        source_type=source_type,
                        source_id=source_id,
                        source_name=source_id,
                    ))
                    seen_ids.add(source_id)
            except ValueError:
                pass

        # Match against provided context citations
        for ctx_citation in context_citations:
            if ctx_citation.source_id not in seen_ids:
                if ctx_citation.source_name.lower() in response.lower():
                    citations.append(ctx_citation)
                    seen_ids.add(ctx_citation.source_id)

        logger.info(
            "citations_generated",
            inline=len([c for c in citations if c.source_id in seen_ids]),
            contextual=len(citations),
        )
        return citations

    def validate_citations(self, citations: list[Citation], context_citations: list[Citation]) -> list[Citation]:
        valid_ids = {c.source_id for c in context_citations}
        valid: list[Citation] = []
        for citation in citations:
            if citation.source_id in valid_ids:
                valid.append(citation)
            else:
                logger.warning("citation_not_in_context", source_id=citation.source_id)
        return valid

    def format_citations(self, citations: list[Citation]) -> str:
        if not citations:
            return ""
        lines = ["\n\n**References:**"]
        for i, c in enumerate(citations, 1):
            lines.append(f"  [{i}] {c.source_type.value}: {c.source_name} (ID: {c.source_id})")
        return "\n".join(lines)

    def check_hallucination(self, content: str, context_citations: list[Citation]) -> list[dict[str, Any]]:
        warnings: list[dict[str, Any]] = []
        specific_claims = re.findall(
            r"(?:metadata|component|field|object|class|trigger|flow)[\s\w]{0,50}\b[A-Z]\w+\b",
            content,
            re.IGNORECASE,
        )
        known_names = {c.source_name.lower() for c in context_citations}
        for claim in specific_claims:
            words = re.findall(r"\b[A-Z]\w+\b", claim)
            for word in words:
                if word.lower() not in known_names and len(word) > 2:
                    warnings.append({
                        "type": "unknown_reference",
                        "term": word,
                        "context": claim[:100],
                    })
        return warnings
