import base64
import hashlib
import secrets
import urllib.parse

import httpx
import structlog

from sfir_backend.config.settings import Settings
from sfir_backend.domain.value_objects.salesforce import (
    SALESFORCE_LOGIN_URLS,
    SalesforceEnvironment,
)

logger = structlog.get_logger(__name__)


class SalesforceOAuthError(Exception):
    pass


class SalesforceOAuthService:
    """OAuth 2.0 Authorization Code flow with PKCE.

    The backend handles the entire OAuth flow.
    The Chrome Extension never sees Salesforce credentials.
    """

    def __init__(self, settings: Settings) -> None:
        self._client_id = settings.salesforce_client_id or ""
        self._client_secret = (
            settings.salesforce_client_secret.get_secret_value()
            if settings.salesforce_client_secret else ""
        )
        self._redirect_uri = settings.salesforce_redirect_uri or ""
        self._default_api_version = settings.salesforce_default_api_version

    def _get_login_url(self, environment: SalesforceEnvironment) -> str:
        base = SALESFORCE_LOGIN_URLS.get(environment, "https://login.salesforce.com")
        return base

    def generate_pkce_pair(self) -> dict[str, str]:
        code_verifier = secrets.token_urlsafe(64)[:128]
        code_challenge = hashlib.sha256(
            code_verifier.encode("ascii"),
        ).digest()
        code_challenge_b64 = (
            base64.urlsafe_b64encode(code_challenge).decode("ascii").rstrip("=")
        )
        return {
            "code_verifier": code_verifier,
            "code_challenge": code_challenge_b64,
        }

    def build_authorization_url(
        self,
        environment: SalesforceEnvironment,
        state: str,
        code_challenge: str,
    ) -> str:
        login_url = self._get_login_url(environment)
        params = {
            "response_type": "code",
            "client_id": self._client_id,
            "redirect_uri": self._redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "scope": " ".join([
                "api",
                "id",
                "web",
                "refresh_token",
                "offline_access",
            ]),
        }
        return f"{login_url}/services/oauth2/authorize?{urllib.parse.urlencode(params)}"

    async def exchange_code_for_tokens(
        self,
        code: str,
        code_verifier: str,
        environment: SalesforceEnvironment = SalesforceEnvironment.PRODUCTION,
    ) -> dict:
        login_url = self._get_login_url(environment)
        data = {
            "grant_type": "authorization_code",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "redirect_uri": self._redirect_uri,
            "code": code,
            "code_verifier": code_verifier,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{login_url}/services/oauth2/token",
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if response.status_code != 200:
            error_body = response.text
            logger.error(
                "salesforce_oauth_exchange_failed",
                status_code=response.status_code,
                error=error_body,
            )
            raise SalesforceOAuthError(
                f"Failed to exchange authorization code: {error_body}",
            )

        return response.json()

    async def refresh_access_token(
        self,
        refresh_token: str,
        environment: SalesforceEnvironment = SalesforceEnvironment.PRODUCTION,
    ) -> dict:
        login_url = self._get_login_url(environment)
        data = {
            "grant_type": "refresh_token",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "refresh_token": refresh_token,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{login_url}/services/oauth2/token",
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if response.status_code != 200:
            error_body = response.text
            logger.error(
                "salesforce_token_refresh_failed",
                status_code=response.status_code,
                error=error_body,
            )
            raise SalesforceOAuthError(
                f"Failed to refresh token: {error_body}",
            )

        return response.json()

    async def revoke_token(
        self,
        refresh_token: str,
        environment: SalesforceEnvironment = SalesforceEnvironment.PRODUCTION,
    ) -> bool:
        login_url = self._get_login_url(environment)
        data = {
            "token": refresh_token,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{login_url}/services/oauth2/revoke",
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        return response.status_code == 200

    @staticmethod
    def generate_state() -> str:
        return secrets.token_urlsafe(32)

    def get_default_api_version(self) -> str:
        return self._default_api_version

    def validate_environment(self, environment: str) -> SalesforceEnvironment:
        try:
            return SalesforceEnvironment(environment)
        except ValueError:
            raise ValueError(f"Invalid Salesforce environment: {environment}") from None
