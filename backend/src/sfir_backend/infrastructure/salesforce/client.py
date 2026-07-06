"""Salesforce HTTP client with retry, rate limiting, and session management.

Supports:
- REST API
- Tooling API
- Metadata API
- Composite API
- Bulk API 2.0
- OAuth 2.0 JWT Bearer & Refresh Token flows
"""

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import Enum
from typing import Any
from urllib.parse import urljoin

import httpx
import structlog

from sfir_backend.config.settings import get_settings

logger = structlog.get_logger(__name__)


class ApiFamily(Enum):
    REST = "rest"
    TOOLING = "tooling"
    METADATA = "metadata"
    COMPOSITE = "composite"
    BULK = "bulk"
    UI = "ui"
    SOAP = "soap"
    AUTH = "auth"


@dataclass
class SalesforceResponse:
    status_code: int
    data: Any
    headers: dict[str, str]
    api_family: ApiFamily
    endpoint: str
    duration_ms: int
    rate_limit_remaining: int | None = None


class SalesforceAuthError(Exception):
    pass


class SalesforceRateLimitError(Exception):
    pass


class SalesforceClientError(Exception):
    def __init__(self, message: str, status_code: int, response_data: Any = None):
        self.status_code = status_code
        self.response_data = response_data
        super().__init__(message)


class SalesforceClient:
    """Async HTTP client for Salesforce APIs with automatic auth and retry."""

    BASE_URL_TEMPLATES = {
        ApiFamily.REST: "{instance_url}/services/data/v{api_version}",
        ApiFamily.TOOLING: "{instance_url}/services/data/v{api_version}/tooling",
        ApiFamily.METADATA: "{instance_url}/services/Soap/m/{api_version}",
        ApiFamily.COMPOSITE: "{instance_url}/services/data/v{api_version}/composite",
        ApiFamily.BULK: "{instance_url}/services/data/v{api_version}/jobs/ingest",
        ApiFamily.UI: "{instance_url}/services/ui-api/{api_version}",
    }

    def __init__(
        self,
        instance_url: str,
        api_version: str = "62.0",
        access_token: str | None = None,
        refresh_token: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        self.instance_url = instance_url.rstrip("/")
        self.api_version = api_version
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._client_id = client_id
        self._client_secret = client_secret

        settings = get_settings()
        self._max_retries = settings.salesforce_max_retries
        self._retry_delay = settings.salesforce_retry_delay
        self._rate_limit_pct = settings.salesforce_rate_limit_percentage

        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=30.0),
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=50),
        )
        self._lock = asyncio.Lock()
        self._token_refreshing = False
        self._org_limits: dict[str, int] = {}

    async def close(self) -> None:
        await self._http.aclose()

    @property
    def is_authenticated(self) -> bool:
        return self._access_token is not None

    def _build_url(self, api_family: ApiFamily, path: str = "") -> str:
        template = self.BASE_URL_TEMPLATES.get(api_family)
        if template:
            base = template.format(
                instance_url=self.instance_url, api_version=self.api_version
            )
        else:
            base = self.instance_url
        return urljoin(base + "/", path.lstrip("/"))

    def _get_headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "SFIR-Backend/0.1.0",
        }
        if extra:
            headers.update(extra)
        return headers

    async def _refresh_access_token(self) -> str:
        """Refresh the OAuth access token using the refresh token."""
        if not self._refresh_token or not self._client_id or not self._client_secret:
            raise SalesforceAuthError(
                "Cannot refresh token: missing refresh_token, client_id, or client_secret"
            )

        async with self._lock:
            if self._token_refreshing:
                await asyncio.sleep(1)
                return self._access_token or ""
            self._token_refreshing = True

        try:
            token_url = urljoin(self.instance_url + "/", "services/oauth2/token")
            response = await self._http.post(
                token_url,
                data={
                    "grant_type": "refresh_token",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "refresh_token": self._refresh_token,
                },
            )
            if response.status_code != 200:
                raise SalesforceAuthError(
                    f"Token refresh failed: {response.status_code} {response.text}"
                )

            data = response.json()
            self._access_token = data["access_token"]
            logger.info("salesforce_token_refreshed")
            return self._access_token or ""
        finally:
            self._token_refreshing = False

    async def _handle_rate_limit(self, response: httpx.Response) -> None:
        """Handle Salesforce rate limiting with exponential backoff."""
        retry_after = response.headers.get("Sforce-Limit-Info", "")
        if "API-Request-Limit-Per-Rolling-Period" in retry_after:
            limit_info = retry_after.split(";")
            for info in limit_info:
                if "Remaining" in info:
                    remaining = int(info.split("=")[-1])
                    if remaining < 10:
                        wait = 60
                        logger.warning(
                            "salesforce_rate_limit_critical",
                            remaining=remaining,
                            wait_seconds=wait,
                        )
                        await asyncio.sleep(wait)
                        return

        if response.status_code == 429:
            retry_after_sec = int(response.headers.get("Retry-After", "5"))
            logger.warning(
                "salesforce_rate_limited",
                retry_after_seconds=retry_after_sec,
            )
            raise SalesforceRateLimitError(
                f"Rate limited by Salesforce. Retry after {retry_after_sec}s"
            )

    async def _extract_limits(self, response: httpx.Response) -> None:
        limit_info = response.headers.get("Sforce-Limit-Info", "")
        if limit_info:
            parts = limit_info.split(";")
            for part in parts:
                if "=" in part:
                    key, val = part.split("=")
                    self._org_limits[key.strip()] = int(val)

    async def request(
        self,
        api_family: ApiFamily,
        method: str,
        path: str = "",
        params: dict[str, Any] | None = None,
        json_data: Any = None,
        headers: dict[str, str] | None = None,
        retry_count: int = 0,
    ) -> SalesforceResponse:
        """Make an HTTP request to a Salesforce API with retry and auth."""
        url = self._build_url(api_family, path)
        request_headers = self._get_headers(headers)

        start = time.monotonic()
        try:
            response = await self._http.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                headers=request_headers,
            )

            duration = int((time.monotonic() - start) * 1000)
            await self._extract_limits(response)

            # Handle 401 - token expired, refresh and retry
            if response.status_code == 401 and self._refresh_token:
                if retry_count < 1:
                    await self._refresh_access_token()
                    return await self.request(
                        api_family, method, path, params, json_data, headers, retry_count + 1
                    )
                raise SalesforceAuthError(
                    f"Authentication failed after token refresh: {response.text}"
                )

            # Handle rate limiting
            await self._handle_rate_limit(response)

            # Handle errors
            if response.status_code >= 400:
                error_data = self._parse_error(response)
                raise SalesforceClientError(
                    message=error_data.get("message", response.text),
                    status_code=response.status_code,
                    response_data=error_data,
                )

            rate_limit_remaining = self._org_limits.get("API-Request-Limit-Per-Rolling-Period-Remaining")
            return SalesforceResponse(
                status_code=response.status_code,
                data=response.json() if response.text else None,
                headers=dict(response.headers),
                api_family=api_family,
                endpoint=path,
                duration_ms=duration,
                rate_limit_remaining=rate_limit_remaining,
            )

        except httpx.TimeoutException:
            if retry_count < self._max_retries:
                wait = self._retry_delay * (2 ** retry_count)
                logger.warning(
                    "salesforce_timeout_retry",
                    retry=retry_count + 1,
                    wait_seconds=wait,
                )
                await asyncio.sleep(wait)
                return await self.request(
                    api_family, method, path, params, json_data, headers, retry_count + 1
                )
            raise SalesforceClientError(
                message=f"Request timed out after {self._max_retries} retries",
                status_code=504,
            )

        except httpx.HTTPError as e:
            raise SalesforceClientError(
                message=f"HTTP error: {e}", status_code=502
            )

    def _parse_error(self, response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
            if isinstance(data, list):
                return data[0] if data else {"message": response.text}
            if isinstance(data, dict):
                return data
        except (ValueError, KeyError):
            pass
        return {"message": response.text[:500]}

    # --- Convenience methods ---

    async def rest(
        self,
        method: str,
        path: str = "",
        **kwargs,
    ) -> SalesforceResponse:
        return await self.request(ApiFamily.REST, method, path, **kwargs)

    async def tooling(
        self,
        method: str,
        path: str = "",
        **kwargs,
    ) -> SalesforceResponse:
        return await self.request(ApiFamily.TOOLING, method, path, **kwargs)

    async def composite(
        self,
        subrequests: list[dict],
        all_or_none: bool = False,
        collate_subrequests: bool = True,
    ) -> SalesforceResponse:
        payload = {
            "allOrNone": all_or_none,
            "collateSubrequests": collate_subrequests,
            "compositeRequest": subrequests,
        }
        return await self.request(
            ApiFamily.COMPOSITE, "POST", "", json_data=payload
        )

    async def bulk_query(
        self,
        soql: str,
        operation: str = "query",
        content_type: str = "CSV",
        column_delimiter: str = "COMMA",
    ) -> SalesforceResponse:
        payload = {
            "operation": operation,
            "query": soql,
            "contentType": content_type,
            "columnDelimiter": column_delimiter,
        }
        return await self.request(
            ApiFamily.BULK, "POST", "", json_data=payload
        )

    async def describe_global(self) -> SalesforceResponse:
        return await self.rest("GET", "sobjects/")

    async def describe_sobject(self, sobject_name: str) -> SalesforceResponse:
        return await self.rest("GET", f"sobjects/{sobject_name}/describe/")

    async def query(self, soql: str) -> SalesforceResponse:
        return await self.rest("GET", "query/", params={"q": soql})

    async def query_tooling(self, soql: str) -> SalesforceResponse:
        return await self.tooling("GET", "query/", params={"q": soql})

    async def get_limits(self) -> SalesforceResponse:
        return await self.rest("GET", "limits/")

    async def get_api_versions(self) -> SalesforceResponse:
        return await self._http.get(
            urljoin(self.instance_url + "/", "services/data/")
        )

    @classmethod
    async def authenticate_with_password(
        cls,
        instance_url: str,
        username: str,
        password: str,
        client_id: str,
        client_secret: str,
        api_version: str = "62.0",
    ) -> "SalesforceClient":
        """Authenticate using OAuth 2.0 Password Grant flow."""
        async with httpx.AsyncClient() as http:
            token_url = urljoin(instance_url + "/", "services/oauth2/token")
            response = await http.post(
                token_url,
                data={
                    "grant_type": "password",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "username": username,
                    "password": password,
                },
            )
            if response.status_code != 200:
                raise SalesforceAuthError(
                    f"Password auth failed: {response.status_code} {response.text}"
                )
            data = response.json()
            return cls(
                instance_url=data.get("instance_url", instance_url),
                api_version=api_version,
                access_token=data["access_token"],
                refresh_token=data.get("refresh_token"),
                client_id=client_id,
                client_secret=client_secret,
            )

    @classmethod
    async def authenticate_with_jwt(
        cls,
        instance_url: str,
        client_id: str,
        jwt_token: str,
        api_version: str = "62.0",
    ) -> "SalesforceClient":
        """Authenticate using OAuth 2.0 JWT Bearer flow."""
        async with httpx.AsyncClient() as http:
            token_url = urljoin(instance_url + "/", "services/oauth2/token")
            response = await http.post(
                token_url,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": jwt_token,
                    "client_id": client_id,
                },
            )
            if response.status_code != 200:
                raise SalesforceAuthError(
                    f"JWT auth failed: {response.status_code} {response.text}"
                )
            data = response.json()
            return cls(
                instance_url=data.get("instance_url", instance_url),
                api_version=api_version,
                access_token=data["access_token"],
                refresh_token=data.get("refresh_token"),
                client_id=client_id,
            )
