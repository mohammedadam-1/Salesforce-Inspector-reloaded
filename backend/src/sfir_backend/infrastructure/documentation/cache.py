from __future__ import annotations

import time

from sfir_backend.domain.documentation.models import CacheEntry, DocumentationPage


class DocumentationCache:
    def __init__(self, default_ttl: int = 300) -> None:
        self._store: dict[str, CacheEntry] = {}
        self._default_ttl = default_ttl

    def get(self, key: str) -> DocumentationPage | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        if entry.page is None:
            return None
        age = time.time() - entry.created_at.timestamp()
        if age > entry.ttl_seconds:
            del self._store[key]
            return None
        return entry.page

    def set(
        self,
        key: str,
        page: DocumentationPage,
        ttl: int | None = None,
    ) -> None:
        raw = page.model_dump_json()
        self._store[key] = CacheEntry(
            key=key,
            page=page,
            ttl_seconds=ttl or self._default_ttl,
            size_bytes=len(raw.encode("utf-8")),
        )

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def invalidate_by_type(self, component_type: str) -> int:
        keys = [
            k for k, v in self._store.items()
            if v.page and v.page.component_type == component_type
        ]
        for k in keys:
            del self._store[k]
        return len(keys)

    def clear(self) -> None:
        self._store.clear()

    def size(self) -> int:
        return len(self._store)

    def total_bytes(self) -> int:
        return sum(e.size_bytes for e in self._store.values())

    def keys(self) -> list[str]:
        return list(self._store.keys())
