from __future__ import annotations

from typing import Any

from sfir_backend.domain.graph.models import Graph


class GraphCacheCoordinator:
    def __init__(self) -> None:
        self._cache: dict[str, Graph] = {}
        self._max_cached: int = 10

    def get(self, key: str) -> Graph | None:
        return self._cache.get(key)

    def set(self, key: str, graph: Graph) -> None:
        if len(self._cache) >= self._max_cached:
            oldest = next(iter(self._cache))
            del self._cache[oldest]
        self._cache[key] = graph

    def invalidate(self, key: str) -> None:
        self._cache.pop(key, None)

    def clear(self) -> None:
        self._cache.clear()

    @property
    def cached_keys(self) -> list[str]:
        return list(self._cache.keys())

    @property
    def cache_size(self) -> int:
        return len(self._cache)

    def get_stats(self) -> dict[str, Any]:
        return {
            "cached_graphs": self.cache_size,
            "max_cached": self._max_cached,
            "keys": self.cached_keys,
        }
