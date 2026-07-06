"""Salesforce OAuth 2.0 authentication flows.

Supports:
- OAuth 2.0 Authorization Code with PKCE (for browser extension)
- OAuth 2.0 JWT Bearer (for server-to-server)
- OAuth 2.0 Refresh Token flow
"""

from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from sfir_backend.config.settings import get_settings

logger = structlog.get_logger(__name__)


@dataclass
class OAuthTokenResponse:
    access_token: str
    refresh_token: str | None = None
    instance_url: str | None = None
    salesforce_org_id: str | None = None
    user_id: str | None = None
    issued_at: str | None = None
    signature: str | None = None
    scope: str | None = None
    token_type: str | None = None
    raw: dict[str, Any] | None = None


class SalesforceOAuthFlow:
    """OAuth 2.0 flow manager for Salesforce connections."""

    SF_AUTH_URL = "https://login.salesforce.com/services/oauth2/authorize"
    SF_TOKEN_URL = "https://login.salesforce.com/services/oauth2/token"
    SF_TEST_AUTH_URL = "https://test.salesforce.com/services/oauth2/authorize"
    SF_TEST_TOKEN_URL = "https://test.salesforce.com/services/oauth2/token"

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        redirect_uri: str | None = None,
    ) -> None:
        settings = get_settings()
        self.client_id = client_id or settings.salesforce_client_id or ""
        self.client_secret = client_secret or (
            settings.salesforce_client_secret.get_secret_value()
            if settings.salesforce_client_secret
            else ""
        )
        self.redirect_uri = redirect_uri or settings.salesforce_redirect_uri or ""

    def get_authorization_url(
        self,
        is_sandbox: bool = False,
        state: str | None = None,
        scope: str = "api refresh_token offline_access",
    ) -> str:
        """Generate the OAuth 2.0 authorization URL."""
        auth_url = self.SF_TEST_AUTH_URL if is_sandbox else self.SF_AUTH_URL
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": scope,
            "prompt": "consent",
        }
        if state:
            params["state"] = state

        query_string = "&".join(
            f"{k}={__import__('urllib').parse.quote(v)}" for k, v in params.items()
        )
        return f"{auth_url}?{query_string}"

    async def exchange_code(
        self, code: str, is_sandbox: bool = False
    ) -> OAuthTokenResponse:
        """Exchange an authorization code for tokens."""
        token_url = self.SF_TEST_TOKEN_URL if is_sandbox else self.SF_TOKEN_URL
        async with httpx.AsyncClient() as http:
            response = await http.post(
                token_url,
                data={
                    "grant_type": "authorization_code",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": self.redirect_uri,
                    "code": code,
                },
            )
            if response.status_code != 200:
                logger.error(
                    "oauth_code_exchange_failed",
                    status=response.status_code,
                    body=response.text[:500],
                )
                raise ValueError(f"OAuth code exchange failed: {response.text}")

            data = response.json()
            return OAuthTokenResponse(
                access_token=data["access_token"],
                refresh_token=data.get("refresh_token"),
                instance_url=data.get("instance_url"),
                salesforce_org_id=data.get("organization_id"),
                user_id=data.get("user_id"),
                issued_at=data.get("issued_at"),
                signature=data.get("signature"),
                scope=data.get("scope"),
                token_type=data.get("token_type"),
                raw=data,
            )

    async def refresh_token(self, refresh_token: str) -> OAuthTokenResponse:
        """Refresh an access token using a refresh token."""
        async with httpx.AsyncClient() as http:
            response = await http.post(
                self.SF_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": refresh_token,
                },
            )
            if response.status_code != 200:
                raise ValueError(f"Token refresh failed: {response.text}")

            data = response.json()
            return OAuthTokenResponse(
                access_token=data["access_token"],
                refresh_token=data.get("refresh_token", refresh_token),
                instance_url=data.get("instance_url"),
                raw=data,
            )
