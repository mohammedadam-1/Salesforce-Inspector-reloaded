"""Tests for Salesforce OAuth, client, encryption, and connection use case."""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from sfir_backend.application.dto.salesforce import (
    SalesforceCallbackRequest,
    SalesforceConnectRequest,
)
from sfir_backend.application.use_cases.salesforce import SalesforceUseCase
from sfir_backend.config.settings import Settings
from sfir_backend.domain.entities.salesforce_connection import SalesforceConnection
from sfir_backend.domain.repositories.audit_log_repo import IAuditLogRepository
from sfir_backend.domain.repositories.organization_repo import IOrganizationRepository
from sfir_backend.domain.repositories.salesforce_repos import (
    ISalesforceConnectionRepository,
)
from sfir_backend.domain.value_objects.salesforce import (
    SalesforceConnectionStatus,
    SalesforceEnvironment,
)
from sfir_backend.infrastructure.salesforce.client import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    SalesforceAuthError,
    SalesforceClient,
)
from sfir_backend.infrastructure.salesforce.oauth import (
    SalesforceOAuthError,
    SalesforceOAuthService,
)
from sfir_backend.infrastructure.security.encryption import EncryptionService
from sfir_backend.shared.exceptions.application import ConflictError
from sfir_backend.shared.exceptions.domain import EntityNotFoundError

# ---------------------------------------------------------------------------
# EncryptionService
# ---------------------------------------------------------------------------

class TestEncryptionService:
    def setup_method(self) -> None:
        settings = Settings(environment="testing", encryption_key="test-encryption-key-32chr")
        self.service = EncryptionService(settings)

    def test_encrypt_decrypt_round_trip(self) -> None:
        plain = "some-sensitive-token-value-12345"
        encrypted = self.service.encrypt(plain)
        assert encrypted != plain
        decrypted = self.service.decrypt(encrypted)
        assert decrypted == plain

    def test_encrypt_empty_string(self) -> None:
        encrypted = self.service.encrypt("")
        decrypted = self.service.decrypt(encrypted)
        assert decrypted == ""

    def test_decrypt_invalid_ciphertext_raises(self) -> None:
        import binascii
        with pytest.raises((binascii.Error, ValueError)):
            self.service.decrypt("invalid-ciphertext")

    def test_different_keys_produce_different_ciphertexts(self) -> None:
        s1 = EncryptionService(
            Settings(environment="testing", encryption_key="key-one-12345678901234"),
        )
        s2 = EncryptionService(
            Settings(environment="testing", encryption_key="key-two-12345678901234"),
        )
        c1 = s1.encrypt("hello")
        c2 = s2.encrypt("hello")
        assert c1 != c2


# ---------------------------------------------------------------------------
# SalesforceOAuthService
# ---------------------------------------------------------------------------

class TestSalesforceOAuthService:
    def setup_method(self) -> None:
        self.settings = Settings(
            environment="testing",
            salesforce_client_id="test-client-id",
            salesforce_client_secret="test-client-secret",
            salesforce_redirect_uri="http://localhost:8000/api/v1/salesforce/callback",
        )
        self.service = SalesforceOAuthService(self.settings)

    def test_generate_pkce_pair_returns_verifier_and_challenge(self) -> None:
        pkce = self.service.generate_pkce_pair()
        assert "code_verifier" in pkce
        assert "code_challenge" in pkce
        assert len(pkce["code_verifier"]) <= 128
        assert len(pkce["code_verifier"]) >= 43
        assert pkce["code_challenge"] != pkce["code_verifier"]

    def test_generate_pkce_pair_challenge_is_urlsafe(self) -> None:
        pkce = self.service.generate_pkce_pair()
        import re
        assert re.match(r"^[A-Za-z0-9\-_]+$", pkce["code_challenge"])

    def test_build_authorization_url_includes_required_params(self) -> None:
        state = "test-state-value"
        challenge = "test-code-challenge"
        url = self.service.build_authorization_url(
            environment=SalesforceEnvironment.PRODUCTION,
            state=state,
            code_challenge=challenge,
        )
        assert url.startswith("https://login.salesforce.com/services/oauth2/authorize")
        assert "response_type=code" in url
        assert f"state={state}" in url
        assert f"code_challenge={challenge}" in url
        assert "code_challenge_method=S256" in url
        assert "client_id=test-client-id" in url
        expected_redirect = "redirect_uri=http%3A%2F%2Flocalhost%3A8000"
        assert expected_redirect in url
        assert "%2Fapi%2Fv1%2Fsalesforce%2Fcallback" in url
        assert "scope=api" in url
        assert "refresh_token" in url
        assert "offline_access" in url

    def test_build_authorization_url_sandbox(self) -> None:
        url = self.service.build_authorization_url(
            environment=SalesforceEnvironment.SANDBOX,
            state="s", code_challenge="c",
        )
        assert url.startswith("https://test.salesforce.com")

    @pytest.mark.asyncio
    async def test_exchange_code_for_tokens_success(self) -> None:
        token_response = {
            "access_token": "00D-access-token",
            "refresh_token": "5AEP-refresh-token",
            "instance_url": "https://na1.salesforce.com",
            "id": "https://login.salesforce.com/id/00Dorg/005user",
            "username": "test@example.com",
        }
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = token_response
        mock_response.text = json.dumps(token_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await self.service.exchange_code_for_tokens(
                code="auth-code", code_verifier="verifier",
            )

        assert result["access_token"] == "00D-access-token"
        assert result["refresh_token"] == "5AEP-refresh-token"
        assert result["instance_url"] == "https://na1.salesforce.com"

    @pytest.mark.asyncio
    async def test_exchange_code_for_tokens_failure(self) -> None:
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 400
        mock_response.text = '{"error":"invalid_grant"}'

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            with pytest.raises(SalesforceOAuthError, match="Failed to exchange"):
                await self.service.exchange_code_for_tokens(
                    code="bad", code_verifier="bad",
                )

    @pytest.mark.asyncio
    async def test_refresh_access_token_success(self) -> None:
        token_response = {
            "access_token": "new-access-token",
            "instance_url": "https://na1.salesforce.com",
        }
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = token_response
        mock_response.text = json.dumps(token_response)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await self.service.refresh_access_token(
                refresh_token="old-refresh-token",
            )

        assert result["access_token"] == "new-access-token"

    @pytest.mark.asyncio
    async def test_refresh_access_token_failure(self) -> None:
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 400
        mock_response.text = '{"error":"invalid_grant"}'

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            with pytest.raises(SalesforceOAuthError, match="Failed to refresh"):
                await self.service.refresh_access_token(
                    refresh_token="bad-token",
                )

    @pytest.mark.asyncio
    async def test_revoke_token_returns_true_on_success(self) -> None:
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await self.service.revoke_token(refresh_token="token")
            assert result is True

    @pytest.mark.asyncio
    async def test_revoke_token_returns_false_on_failure(self) -> None:
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 400

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await self.service.revoke_token(refresh_token="token")
            assert result is False

    def test_generate_state_returns_urlsafe_string(self) -> None:
        state = SalesforceOAuthService.generate_state()
        assert len(state) > 16
        import re
        assert re.match(r"^[A-Za-z0-9\-_]+$", state)

    def test_validate_environment_valid(self) -> None:
        env = self.service.validate_environment("production")
        assert env == SalesforceEnvironment.PRODUCTION
        env = self.service.validate_environment("sandbox")
        assert env == SalesforceEnvironment.SANDBOX

    def test_validate_environment_invalid(self) -> None:
        with pytest.raises(ValueError, match="Invalid Salesforce environment"):
            self.service.validate_environment("invalid-env")

    def test_get_default_api_version(self) -> None:
        version = self.service.get_default_api_version()
        assert version == self.settings.salesforce_default_api_version


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------

class TestCircuitBreaker:
    def test_closed_by_default(self) -> None:
        cb = CircuitBreaker()
        assert not cb._open

    def test_success_resets_failures(self) -> None:
        cb = CircuitBreaker(failure_threshold=2)
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        assert cb._failures == 1
        cb.call(lambda: "ok")
        assert cb._failures == 0

    def test_opens_after_threshold(self) -> None:
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            with pytest.raises(ValueError):
                cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        assert cb._open

    def test_rejects_when_open(self) -> None:
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=60.0)
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        with pytest.raises(CircuitBreakerOpenError):
            cb.call(lambda: "should not execute")

    def test_recovers_after_timeout(self) -> None:
        import time
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)
        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
        assert cb._open
        time.sleep(0.02)
        cb.call(lambda: "recovered")
        assert not cb._open


# ---------------------------------------------------------------------------
# SalesforceClient
# ---------------------------------------------------------------------------

class TestSalesforceClient:
    @pytest.mark.asyncio
    async def test_set_access_token_sets_header(self) -> None:
        client = SalesforceClient("https://na1.salesforce.com", "62.0")
        client.set_access_token("my-token")
        assert client._client.headers["Authorization"] == "Bearer my-token"
        await client.close()

    @pytest.mark.asyncio
    async def test_rest_success(self) -> None:
        client = SalesforceClient("https://na1.salesforce.com", "62.0")
        client._client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"totalSize": 1, "records": []}
        client._client.request.return_value = mock_resp

        result = await client.rest("/query?q=SELECT+Id+FROM+Account")
        assert result["totalSize"] == 1
        await client.close()

    @pytest.mark.asyncio
    async def test_rest_retries_on_timeout(self) -> None:
        client = SalesforceClient(
            "https://na1.salesforce.com", "62.0",
            max_retries=2, retry_delay=0.01,
        )
        client._client = AsyncMock(spec=httpx.AsyncClient)
        client._client.request.side_effect = [
            httpx.TimeoutException("timeout", request=None),
            MagicMock(status_code=200, json=lambda: {"ok": True}),
        ]

        result = await client.rest("/query")
        assert result == {"ok": True}
        await client.close()

    @pytest.mark.asyncio
    async def test_rest_raises_on_auth_error(self) -> None:
        client = SalesforceClient("https://na1.salesforce.com", "62.0")
        client._client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 401
        client._client.request.return_value = mock_resp

        with pytest.raises(SalesforceAuthError):
            await client.rest("/query")
        await client.close()

    @pytest.mark.asyncio
    async def test_rest_raises_on_4xx(self) -> None:
        client = SalesforceClient("https://na1.salesforce.com", "62.0")
        client._client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 404
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_resp,
        )
        client._client.request.return_value = mock_resp

        with pytest.raises(httpx.HTTPStatusError):
            await client.rest("/nonexistent")
        await client.close()

    @pytest.mark.asyncio
    async def test_rest_exhausts_retries_on_5xx(self) -> None:
        client = SalesforceClient(
            "https://na1.salesforce.com", "62.0",
            max_retries=2, retry_delay=0.01,
        )
        client._client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 503
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Service Unavailable", request=MagicMock(), response=mock_resp,
        )
        client._client.request.return_value = mock_resp

        with pytest.raises(httpx.HTTPStatusError):
            await client.rest("/query")
        await client.close()

    @pytest.mark.asyncio
    async def test_query_returns_all_records(self) -> None:
        client = SalesforceClient("https://na1.salesforce.com", "62.0")
        real_client = AsyncMock(spec=httpx.AsyncClient)

        page1_resp = MagicMock(spec=httpx.Response)
        page1_resp.status_code = 200
        page1_resp.json.return_value = {
            "totalSize": 3,
            "records": [{"Id": "001"}],
            "nextRecordsUrl": "/query/next-page",
        }

        page2_resp = MagicMock(spec=httpx.Response)
        page2_resp.status_code = 200
        page2_resp.json.return_value = {
            "totalSize": 3,
            "records": [{"Id": "002"}, {"Id": "003"}],
        }

        real_client.request.side_effect = [page1_resp, page2_resp]
        client._client = real_client

        records = await client.query("SELECT Id FROM Account")
        assert len(records) == 3
        assert records[0]["Id"] == "001"
        assert records[2]["Id"] == "003"
        await client.close()

    @pytest.mark.asyncio
    async def test_metadata_and_tooling(self) -> None:
        client = SalesforceClient("https://na1.salesforce.com", "62.0")
        client._client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"success": True}
        client._client.request.return_value = mock_resp

        meta = await client.metadata("/describeGlobal")
        assert meta["success"] is True

        tool = await client.tooling("/query")
        assert tool["success"] is True
        await client.close()

    @pytest.mark.asyncio
    async def test_get_limits(self) -> None:
        client = SalesforceClient("https://na1.salesforce.com", "62.0")
        client._client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"DailyApiRequests": {"Max": 50000, "Remaining": 49000}}
        client._client.request.return_value = mock_resp

        limits = await client.get_limits()
        assert limits["DailyApiRequests"]["Remaining"] == 49000
        await client.close()

    @pytest.mark.asyncio
    async def test_get_versions(self) -> None:
        client = SalesforceClient("https://na1.salesforce.com", "62.0")
        client._client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.return_value = [{"version": "62.0"}, {"version": "61.0"}]
        client._client.get.return_value = mock_resp

        versions = await client.get_versions()
        assert len(versions) == 2
        await client.close()

    @pytest.mark.asyncio
    async def test_close(self) -> None:
        client = SalesforceClient("https://na1.salesforce.com", "62.0")
        client._client = AsyncMock(spec=httpx.AsyncClient)
        await client.close()
        client._client.aclose.assert_awaited_once()


# ---------------------------------------------------------------------------
# Fake repositories for use case tests
# ---------------------------------------------------------------------------

class FakeSalesforceConnectionRepo(ISalesforceConnectionRepository):
    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, SalesforceConnection] = {}
        self._org_user: dict[tuple[uuid.UUID, uuid.UUID], SalesforceConnection] = {}

    async def get_by_id(self, connection_id: uuid.UUID) -> SalesforceConnection | None:
        return self._connections.get(connection_id)

    async def get_by_org_and_user(
        self, org_id: uuid.UUID, user_id: uuid.UUID,
    ) -> SalesforceConnection | None:
        return self._org_user.get((org_id, user_id))

    async def list_by_organization(self, org_id: uuid.UUID) -> list[SalesforceConnection]:
        return [c for c in self._connections.values() if c.organization_id == org_id]

    async def list_by_user(self, user_id: uuid.UUID) -> list[SalesforceConnection]:
        return [c for c in self._connections.values() if c.user_id == user_id]

    async def list_active_by_organization(
        self, org_id: uuid.UUID,
    ) -> list[SalesforceConnection]:
        return [c for c in self._connections.values()
                if c.organization_id == org_id and c.is_active]

    async def save(self, connection: SalesforceConnection) -> SalesforceConnection:
        self._connections[connection.id] = connection
        self._org_user[(connection.organization_id, connection.user_id)] = connection
        return connection

    async def update(self, connection: SalesforceConnection) -> SalesforceConnection:
        self._connections[connection.id] = connection
        self._org_user[(connection.organization_id, connection.user_id)] = connection
        return connection

    async def delete(self, connection_id: uuid.UUID) -> None:
        conn = self._connections.pop(connection_id, None)
        if conn:
            key = (conn.organization_id, conn.user_id)
            if self._org_user.get(key) is conn:
                del self._org_user[key]


class FakeOrgRepo(IOrganizationRepository):
    async def get_by_id(self, org_id): return None
    async def get_by_slug(self, slug): return None
    async def list_by_user(self, user_id): return []
    async def save(self, org): return org
    async def update(self, org): return org
    async def delete(self, org_id): return None
    async def slug_exists(self, slug): return False


class FakeAuditRepo(IAuditLogRepository):
    def __init__(self):
        self.entries = []

    async def save(self, entry):
        self.entries.append(entry)
        return entry

    async def list_by_org(self, oid, limit=100, offset=0): return []
    async def list_by_user(self, uid, limit=100, offset=0): return []
    async def count_by_org(self, oid, since=None): return 0


# ---------------------------------------------------------------------------
# SalesforceUseCase
# ---------------------------------------------------------------------------

class TestSalesforceUseCase:
    def setup_method(self) -> None:
        self.settings = Settings(
            environment="testing",
            salesforce_client_id="test-client-id",
            salesforce_client_secret="test-secret",
            salesforce_redirect_uri="http://localhost:8000/callback",
            encryption_key="test-encryption-key-32chr!",
        )
        self.connection_repo = FakeSalesforceConnectionRepo()
        self.org_repo = FakeOrgRepo()
        self.audit_repo = FakeAuditRepo()
        self.oauth = SalesforceOAuthService(self.settings)
        self.encryption = EncryptionService(self.settings)
        self.use_case = SalesforceUseCase(
            connection_repo=self.connection_repo,
            org_repo=self.org_repo,
            audit_log_repo=self.audit_repo,
            oauth_service=self.oauth,
            encryption_service=self.encryption,
        )
        self.org_id = uuid.uuid4()
        self.user_id = uuid.uuid4()

    @pytest.mark.asyncio
    async def test_initiate_connect_success(self) -> None:
        request = SalesforceConnectRequest(environment="production")
        response = await self.use_case.initiate_connect(request, self.org_id, self.user_id)

        assert response.authorization_url.startswith("https://login.salesforce.com")
        assert "response_type=code" in response.authorization_url
        assert len(response.state) > 0
        assert len(response.code_verifier) > 0
        assert response.environment == "production"

    @pytest.mark.asyncio
    async def test_initiate_connect_conflict_when_active_exists(self) -> None:
        existing = SalesforceConnection.create(
            organization_id=self.org_id,
            user_id=self.user_id,
            environment=SalesforceEnvironment.PRODUCTION,
            instance_url="https://na1.salesforce.com",
            org_id="00Dxxx",
            username="test@example.com",
        )
        await self.connection_repo.save(existing)

        request = SalesforceConnectRequest(environment="production")
        with pytest.raises(ConflictError, match="already exists"):
            await self.use_case.initiate_connect(request, self.org_id, self.user_id)

    @pytest.mark.asyncio
    async def test_initiate_connect_allows_reconnect_after_disconnect(self) -> None:
        existing = SalesforceConnection.create(
            organization_id=self.org_id,
            user_id=self.user_id,
            environment=SalesforceEnvironment.PRODUCTION,
            instance_url="https://na1.salesforce.com",
            org_id="00Dxxx",
            username="test@example.com",
        )
        existing.mark_disconnected()
        await self.connection_repo.save(existing)

        request = SalesforceConnectRequest(environment="sandbox")
        response = await self.use_case.initiate_connect(request, self.org_id, self.user_id)
        assert response.authorization_url.startswith("https://test.salesforce.com")

    @pytest.mark.asyncio
    async def test_handle_callback_new_connection(self) -> None:
        token_response = {
            "access_token": "00D-access-token",
            "refresh_token": "5AEP-refresh-token",
            "instance_url": "https://na1.salesforce.com",
            "id": "https://login.salesforce.com/id/00Dorg123/005user456",
            "username": "user@example.com",
        }

        with patch.object(self.oauth, "exchange_code_for_tokens", return_value=token_response):
            request = SalesforceCallbackRequest(
                code="auth-code",
                state="state",
                code_verifier="verifier",
                environment="production",
            )
            response = await self.use_case.handle_callback(
                request, self.org_id, self.user_id, ip_address="127.0.0.1",
            )

        assert response.org_id == "00Dorg123"
        assert response.username == "user@example.com"
        assert response.instance_url == "https://na1.salesforce.com"
        assert response.status == "connected"
        assert response.is_active is True
        assert response.organization_id == self.org_id
        assert len(self.audit_repo.entries) == 1
        assert self.audit_repo.entries[0].action == "salesforce.connected"

    @pytest.mark.asyncio
    async def test_handle_callback_updates_existing_connection(self) -> None:
        existing = SalesforceConnection.create(
            organization_id=self.org_id,
            user_id=self.user_id,
            environment=SalesforceEnvironment.PRODUCTION,
            instance_url="https://old.salesforce.com",
            org_id="00Dold",
            username="old@example.com",
        )
        await self.connection_repo.save(existing)

        token_response = {
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "instance_url": "https://new.salesforce.com",
            "id": "https://login.salesforce.com/id/00Dnew/005newuser",
            "username": "new@example.com",
        }

        with patch.object(self.oauth, "exchange_code_for_tokens", return_value=token_response):
            request = SalesforceCallbackRequest(
                code="new-code", state="s", code_verifier="v", environment="production",
            )
            response = await self.use_case.handle_callback(
                request, self.org_id, self.user_id,
            )

        assert response.org_id == "00Dnew"
        assert response.username == "new@example.com"
        assert response.instance_url == "https://new.salesforce.com"
        assert response.id == existing.id

    @pytest.mark.asyncio
    async def test_handle_callback_missing_refresh_token(self) -> None:
        token_response = {
            "access_token": "00D-only-access",
            "instance_url": "https://na1.salesforce.com",
            "id": "https://login.salesforce.com/id/00Dorg/005user",
            "username": "no-refresh@example.com",
        }

        with patch.object(self.oauth, "exchange_code_for_tokens", return_value=token_response):
            request = SalesforceCallbackRequest(
                code="c", state="s", code_verifier="v", environment="production",
            )
            response = await self.use_case.handle_callback(
                request, self.org_id, self.user_id,
            )

        assert response.status == "connected"

    @pytest.mark.asyncio
    async def test_handle_callback_missing_access_token_raises(self) -> None:
        with patch.object(self.oauth, "exchange_code_for_tokens", return_value={}):
            request = SalesforceCallbackRequest(
                code="c", state="s", code_verifier="v", environment="production",
            )
            with pytest.raises(ValueError, match="Invalid token response"):
                await self.use_case.handle_callback(request, self.org_id, self.user_id)

    @pytest.mark.asyncio
    async def test_disconnect_success(self) -> None:
        conn = SalesforceConnection.create(
            organization_id=self.org_id,
            user_id=self.user_id,
            environment=SalesforceEnvironment.PRODUCTION,
            instance_url="https://na1.salesforce.com",
            org_id="00Dorg",
            username="user@example.com",
        )
        conn.mark_connected(
            access_token_encrypted=self.encryption.encrypt("token"),
            refresh_token_encrypted=self.encryption.encrypt("refresh"),
        )
        await self.connection_repo.save(conn)

        with patch.object(self.oauth, "revoke_token", return_value=True):
            await self.use_case.disconnect(self.org_id, self.user_id, ip_address="10.0.0.1")

        updated = await self.connection_repo.get_by_org_and_user(self.org_id, self.user_id)
        assert updated is not None
        assert updated.status == SalesforceConnectionStatus.DISCONNECTED
        assert updated.access_token_encrypted == ""
        assert updated.refresh_token_encrypted == ""
        assert len(self.audit_repo.entries) == 1
        assert self.audit_repo.entries[0].action == "salesforce.disconnected"

    @pytest.mark.asyncio
    async def test_disconnect_not_found_raises(self) -> None:
        with pytest.raises(EntityNotFoundError):
            await self.use_case.disconnect(self.org_id, self.user_id)

    @pytest.mark.asyncio
    async def test_disconnect_handles_revoke_failure_gracefully(self) -> None:
        conn = SalesforceConnection.create(
            organization_id=self.org_id,
            user_id=self.user_id,
            environment=SalesforceEnvironment.PRODUCTION,
            instance_url="https://na1.salesforce.com",
            org_id="00Dorg",
            username="u@e.com",
        )
        conn.mark_connected(
            access_token_encrypted=self.encryption.encrypt("tok"),
            refresh_token_encrypted=self.encryption.encrypt("ref"),
        )
        await self.connection_repo.save(conn)

        with patch.object(self.oauth, "revoke_token", side_effect=Exception("revoke failed")):
            await self.use_case.disconnect(self.org_id, self.user_id)

        updated = await self.connection_repo.get_by_org_and_user(self.org_id, self.user_id)
        assert updated.status == SalesforceConnectionStatus.DISCONNECTED

    @pytest.mark.asyncio
    async def test_get_status_returns_connection(self) -> None:
        conn = SalesforceConnection.create(
            organization_id=self.org_id,
            user_id=self.user_id,
            environment=SalesforceEnvironment.PRODUCTION,
            instance_url="https://na1.salesforce.com",
            org_id="00Dorg",
            username="u@e.com",
        )
        await self.connection_repo.save(conn)

        response = await self.use_case.get_status(self.org_id, self.user_id)
        assert response is not None
        assert response.org_id == "00Dorg"
        assert response.status == "pending"

    @pytest.mark.asyncio
    async def test_get_status_returns_none_when_no_connection(self) -> None:
        response = await self.use_case.get_status(self.org_id, self.user_id)
        assert response is None

    @pytest.mark.asyncio
    async def test_check_health_success(self) -> None:
        conn = SalesforceConnection.create(
            organization_id=self.org_id,
            user_id=self.user_id,
            environment=SalesforceEnvironment.PRODUCTION,
            instance_url="https://na1.salesforce.com",
            org_id="00Dorg",
            username="u@e.com",
        )
        conn.mark_connected(
            access_token_encrypted=self.encryption.encrypt("valid-token"),
            refresh_token_encrypted="",
        )
        await self.connection_repo.save(conn)

        with (
            patch("sfir_backend.application.use_cases.salesforce.SalesforceClient") as MockClient,
        ):
            mock_instance = MagicMock(spec=SalesforceClient)
            mock_instance.get_limits = AsyncMock(return_value={
                "DailyApiRequests": {"Max": 50000, "Remaining": 49000},
            })
            mock_instance.rest = AsyncMock(return_value={
                "attributes": {"type": "Organization"},
                "Name": "Test Org",
            })
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            response = await self.use_case.check_health(self.org_id, self.user_id)

        assert response.is_token_valid is True
        assert response.status == "connected"
        assert response.limits["DailyApiRequests"]["Remaining"] == 49000

    @pytest.mark.asyncio
    async def test_check_health_decrypt_failure(self) -> None:
        conn = SalesforceConnection.create(
            organization_id=self.org_id,
            user_id=self.user_id,
            environment=SalesforceEnvironment.PRODUCTION,
            instance_url="https://na1.salesforce.com",
            org_id="00Dorg",
            username="u@e.com",
        )
        conn.access_token_encrypted = "corrupted-ciphertext"
        await self.connection_repo.save(conn)

        response = await self.use_case.check_health(self.org_id, self.user_id)
        assert response.is_token_valid is False
        assert "Failed to decrypt" in response.error_message

    @pytest.mark.asyncio
    async def test_check_health_api_failure(self) -> None:
        conn = SalesforceConnection.create(
            organization_id=self.org_id,
            user_id=self.user_id,
            environment=SalesforceEnvironment.PRODUCTION,
            instance_url="https://na1.salesforce.com",
            org_id="00Dorg",
            username="u@e.com",
        )
        conn.mark_connected(
            access_token_encrypted=self.encryption.encrypt("token"),
            refresh_token_encrypted="",
        )
        await self.connection_repo.save(conn)

        with (
            patch("sfir_backend.application.use_cases.salesforce.SalesforceClient") as MockClient,
        ):
            mock_instance = MagicMock(spec=SalesforceClient)
            mock_instance.get_limits = AsyncMock(side_effect=httpx.HTTPStatusError(
                "401 Unauthorized", request=MagicMock(),
                response=MagicMock(status_code=401),
            ))
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            response = await self.use_case.check_health(self.org_id, self.user_id)

        assert response.is_token_valid is False
        assert "401" in response.error_message

    @pytest.mark.asyncio
    async def test_check_health_no_connection_raises(self) -> None:
        with pytest.raises(EntityNotFoundError):
            await self.use_case.check_health(uuid.uuid4(), uuid.uuid4())

    @pytest.mark.asyncio
    async def test_check_health_skipped_without_token_encrypted(self) -> None:
        conn = SalesforceConnection.create(
            organization_id=self.org_id,
            user_id=self.user_id,
            environment=SalesforceEnvironment.PRODUCTION,
            instance_url="https://na1.salesforce.com",
            org_id="00Dorg",
            username="u@e.com",
        )
        await self.connection_repo.save(conn)

        response = await self.use_case.check_health(self.org_id, self.user_id)
        assert response.is_token_valid is False
        assert "Failed to decrypt" in response.error_message
