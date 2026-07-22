from __future__ import annotations

import time
from typing import Any

from sfir_backend.domain.search.models import (
    SearchDocument,
    SearchQuery,
    SearchResponse,
    SearchResult,
)


class SearchResultFormatter:
    def format(
        self,
        scored: list[tuple[SearchDocument, float, list[str]]],
        query: SearchQuery,
        total_count: int,
        start_time: float,
        suggestions: list[str] | None = None,
    ) -> SearchResponse:
        offset = query.pagination.offset
        limit = query.pagination.limit
        page = offset // limit + 1 if limit > 0 else 1
        total_pages = (total_count + limit - 1) // limit if limit > 0 else 0

        page_items = scored[offset: offset + limit]
        results: list[SearchResult] = []
        for rank, (doc, score, matched_fields) in enumerate(page_items, start=offset + 1):
            results.append(
                SearchResult(
                    document=doc,
                    score=score,
                    rank=rank,
                    matched_fields=matched_fields,
                    highlights=self._build_highlights(doc, query),
                )
            )

        took_ms = (time.time() - start_time) * 1000.0

        return SearchResponse(
            results=results,
            total_count=total_count,
            page=page,
            page_size=limit,
            total_pages=total_pages,
            query=query.raw_query,
            took_ms=round(took_ms, 2),
            suggestions=suggestions or [],
        )

    def _build_highlights(
        self,
        doc: SearchDocument,
        query: SearchQuery,
    ) -> dict[str, str]:
        highlights: dict[str, str] = {}
        q = query.raw_query.lower().strip()
        if not q:
            return highlights
        for field_name in ("api_name", "label", "description"):
            value = getattr(doc, field_name, "") or ""
            if q in value.lower():
                idx = value.lower().index(q)
                start = max(0, idx - 20)
                end = min(len(value), idx + len(q) + 20)
                snippet = value[start:end]
                if start > 0:
                    snippet = "..." + snippet
                if end < len(value):
                    snippet = snippet + "..."
                highlights[field_name] = snippet
        return highlights

    def format_suggestions(
        self,
        suggestions: list[str],
        query: str = "",  # noqa: ARG002
    ) -> list[dict[str, Any]]:
        return [
            {"text": s, "type": "api_name" if "." in s else "metadata"}
            for s in suggestions
        ]
