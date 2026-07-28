import asyncio
import time

import httpx
import structlog

logger = structlog.get_logger(__name__)


class CircuitBreakerOpenError(Exception):
    pass


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._failures = 0
        self._last_failure_time = 0.0
        self._open = False

    async def call(self, coro):
        if self._open:
            if time.monotonic() - self._last_failure_time > self._recovery_timeout:
                self._open = False
                self._failures = 0
            else:
                raise CircuitBreakerOpenError(
                    "Circuit breaker is open. Too many failures.",
                )
        try:
            result = await coro
            self._failures = 0
            return result
        except Exception as exc:
            self._failures += 1
            self._last_failure_time = time.monotonic()
            if self._failures >= self._failure_threshold:
                self._open = True
            raise exc


class SalesforceClient:
    """Base HTTP client for Salesforce APIs.

    Supports automatic retries, backoff, circuit breaker,
    and automatic token refresh.
    """

    def __init__(
        self,
        instance_url: str,
        api_version: str,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout_seconds: int = 60,
    ) -> None:
        self._instance_url = instance_url.rstrip("/")
        self._api_version = api_version
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._timeout = httpx.Timeout(timeout_seconds)
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=True,
        )
        self._circuit_breaker = CircuitBreaker()

    def set_access_token(self, token: str) -> None:
        self._client.headers["Authorization"] = f"Bearer {token}"

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: object,
    ) -> httpx.Response:
        url = f"{self._instance_url}{path}"
        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                response = await self._circuit_breaker.call(
                    self._client.request(method, url, **kwargs),
                )
                if response.status_code in (401, 403):
                    raise SalesforceAuthError("Token expired or invalid")
                response.raise_for_status()
                return response
            except CircuitBreakerOpenError:
                raise
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_error = exc
                logger.warning(
                    "salesforce_request_failed",
                    method=method, path=path, attempt=attempt,
                    error=str(exc),
                )
                if attempt < self._max_retries:
                    await asyncio.sleep(self._retry_delay * (2 ** attempt))
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    retry_after = int(exc.response.headers.get("Retry-After", "30"))
                    raise SalesforceRateLimitError(
                        f"Rate limited; retry after {retry_after}s",
                        retry_after=retry_after,
                    ) from exc
                if exc.response.status_code >= 500 and attempt < self._max_retries:
                    last_error = exc
                    await asyncio.sleep(self._retry_delay * (2 ** attempt))
                else:
                    raise
            except SalesforceAuthError:
                raise

        raise last_error or httpx.RequestError("Max retries exceeded")

    async def rest(self, path: str, **kwargs: object) -> dict:
        full_path = f"/services/data/v{self._api_version}{path}"
        response = await self._request("GET", full_path, **kwargs)
        return response.json()

    async def rest_post(self, path: str, json_data: dict | None = None) -> dict:
        full_path = f"/services/data/v{self._api_version}{path}"
        response = await self._request("POST", full_path, json=json_data or {})
        return response.json()

    async def query(self, soql: str) -> list[dict]:
        import urllib.parse

        path = f"/query?q={urllib.parse.quote(soql)}"
        records: list[dict] = []
        while path:
            response = await self.rest(path)
            records.extend(response.get("records", []))
            path = response.get("nextRecordsUrl")
        return records

    async def metadata(self, path: str, **kwargs: object) -> dict:
        full_path = f"/services/Soap/m/{self._api_version}{path}"
        return await self.rest(full_path, **kwargs)

    async def tooling(self, path: str, **kwargs: object) -> dict:
        full_path = f"/services/data/v{self._api_version}/tooling{path}"
        return await self.rest(full_path, **kwargs)

    async def get_limits(self) -> dict:
        return await self.rest("/limits")

    async def get_versions(self) -> list[dict]:
        response = await self._client.get(
            f"{self._instance_url}/services/data/",
        )
        return response.json()

    async def close(self) -> None:
        await self._client.aclose()


class SalesforceAuthError(Exception):
    pass


class SalesforceRateLimitError(Exception):
    def __init__(self, message: str, retry_after: int = 30) -> None:
        super().__init__(message)
        self.retry_after = retry_after
