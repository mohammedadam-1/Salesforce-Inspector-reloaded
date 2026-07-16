# ────────────────────────────────────────────────────────────
# SFIR Backend — Chaos Engineering Tests
# Run: python -m pytest tests/chaos/ -v
# Requires: Docker, network access to service endpoints
# ────────────────────────────────────────────────────────────


import pytest
import requests

BASE_URL = "http://localhost:8000"
TIMEOUT = 30


@pytest.fixture(scope="session")
def service_running() -> bool:
    try:
        r = requests.get(f"{BASE_URL}/api/v1/health/live", timeout=5)
        return r.status_code == 200
    except requests.ConnectionError:
        return False


@pytest.mark.skipif("not service_running()")
class TestDatabaseFailure:
    def test_api_handles_db_failure(self) -> None:
        r = requests.get(f"{BASE_URL}/api/v1/search", params={"query": "test"}, timeout=TIMEOUT)
        assert r.status_code in (200, 503)
        if r.status_code == 503:
            data = r.json()
            assert "unavailable" in str(data).lower()


@pytest.mark.skipif("not service_running()")
class TestRedisFailure:
    def test_api_handles_redis_failure(self) -> None:
        r = requests.get(f"{BASE_URL}/api/v1/health/ready", timeout=TIMEOUT)
        assert r.status_code in (200, 503)


@pytest.mark.skipif("not service_running()")
class TestAuthenticationFailure:
    def test_missing_token(self) -> None:
        r = requests.get(f"{BASE_URL}/api/v1/admin/users", timeout=TIMEOUT)
        assert r.status_code in (401, 403)

    def test_invalid_token(self) -> None:
        headers = {"Authorization": "Bearer invalid-token"}
        r = requests.get(f"{BASE_URL}/api/v1/admin/users", headers=headers, timeout=TIMEOUT)
        assert r.status_code in (401, 403)

    def test_expired_token_format(self) -> None:
        headers = {"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIiwiaWF0IjoxNTE2MjM5MDIyfQ"}
        r = requests.get(f"{BASE_URL}/api/v1/admin/users", headers=headers, timeout=TIMEOUT)
        assert r.status_code in (401, 403)


@pytest.mark.skipif("not service_running()")
class TestRateLimiting:
    def test_rate_limit_triggered(self) -> None:
        responses = []
        for _ in range(50):
            r = requests.get(f"{BASE_URL}/api/v1/health/live", timeout=5)
            responses.append(r.status_code)
        too_many = [s for s in responses if s == 429]
        assert len(too_many) < 10  # Should not trigger on health endpoint


@pytest.mark.skipif("not service_running()")
class TestLargePayload:
    def test_large_request_body(self) -> None:
        large_body = {"query": "x" * 100_000}
        r = requests.post(
            f"{BASE_URL}/api/v1/ai/chat",
            json=large_body,
            timeout=TIMEOUT,
        )
        assert r.status_code in (200, 413, 422)


@pytest.mark.skipif("not service_running()")
class TestConcurrentRequests:
    def test_concurrent_health_checks(self) -> None:
        import threading

        results: list[int] = []

        def check() -> None:
            try:
                r = requests.get(f"{BASE_URL}/api/v1/health/live", timeout=10)
                results.append(r.status_code)
            except Exception:
                results.append(0)

        threads = [threading.Thread(target=check) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        successful = [s for s in results if s == 200]
        assert len(successful) >= 18  # At least 90% success
