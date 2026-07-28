import uuid
from sfir_backend.domain.ai.models import AIFeature
from sfir_backend.infrastructure.llm.ai_cache import AICache


class TestAICache:
    def setup_method(self) -> None:
        self.cache = AICache(default_ttl=3600)

    def test_set_and_get(self) -> None:
        key = "test-key"
        self.cache.set(key, "cached response")
        entry = self.cache.get(key)
        assert entry is not None
        assert entry.response == "cached response"

    def test_get_miss(self) -> None:
        entry = self.cache.get("nonexistent")
        assert entry is None

    def test_hit_count(self) -> None:
        key = "hit-test"
        self.cache.set(key, "data")
        self.cache.get(key)
        self.cache.get(key)
        entry = self.cache.get(key)
        assert entry is not None
        assert entry.hit_count == 3

    def test_invalidate(self) -> None:
        key = "invalidate-test"
        self.cache.set(key, "data")
        assert self.cache.invalidate(key) is True
        assert self.cache.get(key) is None

    def test_invalidate_nonexistent(self) -> None:
        assert self.cache.invalidate("missing") is False

    def test_invalidate_by_organization(self) -> None:
        org_id = uuid.uuid4()
        key1 = f"org:{org_id}:key1"
        key2 = f"org:{org_id}:key2"
        key3 = "other:key"
        self.cache.set(key1, "data1")
        self.cache.set(key2, "data2")
        self.cache.set(key3, "data3")
        count = self.cache.invalidate_by_organization(org_id)
        assert count == 2
        assert self.cache.get(key1) is None
        assert self.cache.get(key3) is not None

    def test_clear(self) -> None:
        self.cache.set("k1", "v1")
        self.cache.set("k2", "v2")
        self.cache.clear()
        assert self.cache.statistics()["size"] == 0

    def test_statistics(self) -> None:
        self.cache.set("k", "v")
        self.cache.get("k")
        self.cache.get("missing")
        stats = self.cache.statistics()
        assert stats["size"] == 1
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_ratio"] == 0.5

    def test_get_or_compute_cache_hit(self) -> None:
        import uuid as _uuid
        org_id = _uuid.uuid4()
        content, citations, usage, cached = self.cache.get_or_compute(
            AIFeature.QUESTION_ANSWERING,
            "test query",
            org_id,
            lambda: ("computed", [], type("TU", (), {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "estimated_cost": 0.0})()),
        )
        # First call computes
        assert not cached
        # Second call should hit cache
        content2, _, _, cached2 = self.cache.get_or_compute(
            AIFeature.QUESTION_ANSWERING,
            "test query",
            org_id,
            lambda: ("should not be called", [], type("TU", (), {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "estimated_cost": 0.0})()),
        )
        assert cached2
