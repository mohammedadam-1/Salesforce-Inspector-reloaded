from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from sfir_backend.domain.ai.models import AIFeature, CacheEntry, Citation, TokenUsage

logger = structlog.get_logger(__name__)


class AICache:
    def __init__(self, default_ttl: int = 300) -> None:
        self._cache: dict[str, CacheEntry] = {}
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0

    def _make_key(
        self,
        feature: AIFeature,
        query: str,
        organization_id: uuid.UUID,
        model: str | None = None,
    ) -> str:
        raw = f"{feature.value}:{query.lower().strip()}:{organization_id}:{model or ''}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, key: str) -> CacheEntry | None:
        entry = self._cache.get(key)
        if not entry:
            self._misses += 1
            return None
        elapsed = (datetime.now(UTC) - entry.created_at).total_seconds()
        if elapsed > entry.ttl_seconds:
            del self._cache[key]
            self._misses += 1
            return None
        entry.hit_count += 1
        self._hits += 1
        return entry

    def set(
        self,
        key: str,
        response: str,
        citations: list[Citation] | None = None,
        token_usage: TokenUsage | None = None,
        ttl: int | None = None,
    ) -> None:
        self._cache[key] = CacheEntry(
            key=key,
            response=response,
            citations=citations or [],
            token_usage=token_usage or TokenUsage(),
            ttl_seconds=ttl or self._default_ttl,
        )

    def get_or_compute(
        self,
        feature: AIFeature,
        query: str,
        organization_id: uuid.UUID,
        compute_fn: Any,
        model: str | None = None,
        ttl: int | None = None,
    ) -> tuple[str, list[Citation], TokenUsage, bool]:
        key = self._make_key(feature, query, organization_id, model)
        cached = self.get(key)
        if cached:
            return cached.response, cached.citations, cached.token_usage, True

        content, citations, token_usage = compute_fn()
        self.set(key, content, citations, token_usage, ttl)
        return content, citations, token_usage, False

    def invalidate(self, key: str) -> bool:
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def invalidate_by_organization(self, organization_id: uuid.UUID) -> int:
        count = 0
        org_str = str(organization_id)
        keys_to_delete = [
            k for k, v in self._cache.items() if org_str in k
        ]
        for key in keys_to_delete:
            del self._cache[key]
            count += 1
        return count

    def clear(self) -> None:
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    def statistics(self) -> dict[str, Any]:
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_ratio": round(self._hits / total, 4) if total > 0 else 0.0,
        }
