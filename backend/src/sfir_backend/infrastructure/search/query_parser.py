from __future__ import annotations

import re
from typing import Any

from sfir_backend.domain.search.models import (
    SearchFilter,
    SearchPagination,
    SearchQuery,
    SearchSort,
)


class QueryParser:
    def parse(
        self,
        raw_query: str,
        filters: list[dict[str, Any]] | None = None,
        sort_field: str | None = None,
        sort_direction: str = "desc",
        offset: int = 0,
        limit: int = 20,
        metadata_types: list[str] | None = None,
        organization_id: str = "",
        namespace: str | None = None,
    ) -> SearchQuery:
        tokens: list[str] = []
        exact_phrases: list[str] = []
        exclude_tokens: list[str] = []
        exclude_words: set[str] = {"and", "or", "the", "a", "an", "in", "of", "for", "to"}

        raw = raw_query.strip()

        phrases = re.findall(r'"([^"]*)"', raw)
        exact_phrases.extend(p.strip() for p in phrases if p.strip())

        remaining = raw
        for p in phrases:
            remaining = remaining.replace(f'"{p}"', '')

        raw_tokens = re.findall(r"[^\s]+", remaining)
        i = 0
        while i < len(raw_tokens):
            token = raw_tokens[i]
            if token.upper() in ("AND", "OR", "NOT"):
                i += 1
                continue
            if token.startswith("-") or token.upper().startswith("NOT "):
                exclude = token[1:] if token.startswith("-") else token[4:]
                if exclude:
                    exclude_tokens.append(exclude.lower())
                i += 1
                continue
            normalized = token.lower().strip(",.!?;:")
            if normalized and normalized not in exclude_words:
                tokens.append(normalized)
            i += 1

        parsed_filters: list[SearchFilter] = []
        if filters:
            for f in filters:
                if isinstance(f, dict):
                    parsed_filters.append(SearchFilter(**f))
                elif isinstance(f, SearchFilter):
                    parsed_filters.append(f)

        sort = SearchSort(field=sort_field or "score", direction=sort_direction)

        return SearchQuery(
            raw_query=raw_query,
            tokens=tokens,
            exact_phrases=exact_phrases,
            exclude_tokens=exclude_tokens,
            filters=parsed_filters,
            sort=sort,
            pagination=SearchPagination(offset=offset, limit=min(limit, 100)),
            metadata_types=metadata_types or [],
            organization_id=organization_id,
            namespace=namespace,
        )

    def parse_saved_query(self, raw_query: str) -> list[str]:
        return list(set(re.findall(r"[a-zA-Z0-9_.*?]+", raw_query.lower())))
