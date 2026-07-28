from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class ResponseCacheEntry:
    def __init__(
        self,
        key: str,
        value: Any,
        ttl_seconds: int = 300,
    ) -> None:
        self.key = key
        self.value = value
        self.created_at = time.monotonic()
        self.ttl_seconds = ttl_seconds
        self.access_count = 0

    @property
    def is_expired(self) -> bool:
        return (time.monotonic() - self.created_at) > self.ttl_seconds

    def record_access(self) -> None:
        self.access_count += 1


class ResponseCache:
    def __init__(self, default_ttl: int = 300, max_entries: int = 1000) -> None:
        self._cache: dict[str, ResponseCacheEntry] = {}
        self._default_ttl = default_ttl
        self._max_entries = max_entries
        self._hits = 0
        self._misses = 0

    @staticmethod
    def build_key(prefix: str, *args: Any, **kwargs: Any) -> str:
        raw = f"{prefix}:{json.dumps(args, sort_keys=True)}:{json.dumps(kwargs, sort_keys=True)}"
        return hashlib.sha256(raw.encode()).hexdigest()

    async def get(self, key: str) -> Any | None:
        entry = self._cache.get(key)
        if entry is None:
            self._misses += 1
            return None
        if entry.is_expired:
            self._cache.pop(key, None)
            self._misses += 1
            return None
        entry.record_access()
        self._hits += 1
        return entry.value

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> None:
        self._evict_if_needed()
        self._cache[key] = ResponseCacheEntry(
            key=key,
            value=value,
            ttl_seconds=self._default_ttl if ttl_seconds is None else ttl_seconds,
        )

    async def invalidate(self, key: str) -> None:
        self._cache.pop(key, None)

    async def invalidate_prefix(self, prefix: str) -> None:
        keys_to_remove = [k for k in self._cache if k.startswith(prefix)]
        for k in keys_to_remove:
            self._cache.pop(k, None)

    async def clear(self) -> None:
        self._cache.clear()

    def _evict_if_needed(self) -> None:
        if len(self._cache) < self._max_entries:
            return
        sorted_entries = sorted(
            self._cache.items(),
            key=lambda x: x[1].access_count,
        )
        to_remove = len(self._cache) - self._max_entries + self._max_entries // 10
        for key, _ in sorted_entries[:to_remove]:
            self._cache.pop(key, None)

    def stats(self) -> dict[str, Any]:
        return {
            "size": len(self._cache),
            "max_entries": self._max_entries,
            "hits": self._hits,
            "misses": self._misses,
            "hit_ratio": self._hits / (self._hits + self._misses + 1),
        }
