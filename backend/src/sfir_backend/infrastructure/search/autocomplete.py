from __future__ import annotations

from collections import Counter

from sfir_backend.infrastructure.search.index import SearchIndex


class AutocompleteService:
    def __init__(self, search_index: SearchIndex) -> None:
        self._index = search_index
        self._recent_queries: list[str] = []
        self._popular_queries: Counter[str] = Counter()
        self._max_recent: int = 50

    def suggest(self, prefix: str, limit: int = 10) -> list[str]:
        if not prefix or not prefix.strip():
            return self._popular_suggestions(limit)
        prefix = prefix.strip().lower()
        index_suggestions = self._index.suggest(prefix, limit)
        popular = [q for q in self._popular_queries if q.lower().startswith(prefix)]
        popular.sort(key=lambda q: -self._popular_queries[q])
        seen: set[str] = set()
        result: list[str] = []
        for item in index_suggestions:
            if item not in seen:
                seen.add(item)
                result.append(item)
        for item in popular:
            if len(result) >= limit:
                break
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result[:limit]

    def _popular_suggestions(self, limit: int) -> list[str]:
        return [q for q, _ in self._popular_queries.most_common(limit)]

    def record_search(self, query: str, result_count: int = 0) -> None:  # noqa: ARG002
        q = query.strip().lower()
        if not q:
            return
        self._popular_queries[q] += 1
        if q in self._recent_queries:
            self._recent_queries.remove(q)
        self._recent_queries.insert(0, q)
        if len(self._recent_queries) > self._max_recent:
            self._recent_queries.pop()

    def recent_searches(self, limit: int = 10) -> list[str]:
        return self._recent_queries[:limit]

    def clear(self) -> None:
        self._recent_queries.clear()
        self._popular_queries.clear()
