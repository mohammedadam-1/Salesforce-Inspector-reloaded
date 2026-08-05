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
from sfir_backend.domain.entities.oauth_session import OAuthSession
from sfir_backend.domain.entities.org_member import OrgMember
from sfir_backend.domain.entities.organization import Organization
from sfir_backend.domain.entities.role import Role
from sfir_backend.domain.entities.salesforce_connection import SalesforceConnection
from sfir_backend.domain.repositories.audit_log_repo import IAuditLogRepository
from sfir_backend.domain.repositories.oauth_session_repo import (
    IOAuthSessionRepository,
)
from sfir_backend.domain.repositories.org_member_repo import IOrgMemberRepository
from sfir_backend.domain.repositories.organization_repo import IOrganizationRepository
from sfir_backend.domain.repositories.role_repo import IRoleRepository
from sfir_backend.domain.repositories.salesforce_repos import (
    ISalesforceConnectionRepository,
)
from sfir_backend.domain.value_objects.salesforce import (
    SalesforceConnectionStatus,
    SalesforceEnvironment,
)
from sfir_backend.domain.value_objects.user_status import (
    OrganizationStatus,
    OrgMemberStatus,
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
from sfir_backend.shared.exceptions.application import (
    ConflictError,
    InvalidOAuthStateError,
)
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
    @pytest.mark.asyncio
    async def test_closed_by_default(self) -> None:
        cb = CircuitBreaker()
        assert not cb._open

    @pytest.mark.asyncio
    async def test_success_resets_failures(self) -> None:
        cb = CircuitBreaker(failure_threshold=2)

        async def fail() -> None:
            raise ValueError("fail")

        async def ok() -> str:
            return "ok"

        with pytest.raises(ValueError):
            await cb.call(fail())
        assert cb._failures == 1
        await cb.call(ok())
        assert cb._failures == 0

    @pytest.mark.asyncio
    async def test_opens_after_threshold(self) -> None:
        cb = CircuitBreaker(failure_threshold=3)

        async def fail() -> None:
            raise ValueError("fail")

        for _ in range(3):
            with pytest.raises(ValueError):
                await cb.call(fail())
        assert cb._open

    @pytest.mark.asyncio
    async def test_rejects_when_open(self) -> None:
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=60.0)

        async def fail() -> None:
            raise ValueError("fail")

        async def ok() -> str:
            return "ok"

        with pytest.raises(ValueError):
            await cb.call(fail())
        with pytest.raises(CircuitBreakerOpenError):
            await cb.call(ok())

    @pytest.mark.asyncio
    async def test_recovers_after_timeout(self) -> None:
        import time
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)

        async def fail() -> None:
            raise ValueError("fail")

        async def ok() -> str:
            return "ok"

        with pytest.raises(ValueError):
            await cb.call(fail())
        assert cb._open
        time.sleep(0.02)
        await cb.call(ok())
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

    async def get_inactive_by_org_and_user(
        self, org_id: uuid.UUID, user_id: uuid.UUID,
    ) -> SalesforceConnection | None:
        conn = self._org_user.get((org_id, user_id))
        return conn if conn and not conn.is_active else None

    async def list_by_organization(self, org_id: uuid.UUID) -> list[SalesforceConnection]:
        return [c for c in self._connections.values() if c.organization_id == org_id]

    async def list_by_user(self, user_id: uuid.UUID) -> list[SalesforceConnection]:
        return [c for c in self._connections.values() if c.user_id == user_id]

    async def list_active_by_organization(
        self, org_id: uuid.UUID,
    ) -> list[SalesforceConnection]:
        return [c for c in self._connections.values()
                if c.organization_id == org_id and c.is_active]

    async def list_active(self) -> list[SalesforceConnection]:
        return [c for c in self._connections.values() if c.is_active]

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
    def __init__(self) -> None:
        self._orgs: dict[uuid.UUID, Organization] = {}

    async def get_by_id(self, org_id):
        return self._orgs.get(org_id)

    async def get_by_slug(self, slug):
        return next((o for o in self._orgs.values() if o.slug == slug), None)

    async def get_by_salesforce_org_id(self, salesforce_org_id):
        return next(
            (o for o in self._orgs.values()
             if o.salesforce_org_id == salesforce_org_id),
            None,
        )

    async def find_or_create_by_salesforce_org_id(
        self, *, salesforce_org_id, salesforce_org_name,
        instance_url, organization_type, owner_id, slug,
    ):
        existing = await self.get_by_salesforce_org_id(salesforce_org_id)
        if existing:
            return existing, False
        org = Organization.create_workspace(
            salesforce_org_id=salesforce_org_id,
            salesforce_org_name=salesforce_org_name,
            instance_url=instance_url,
            organization_type=organization_type,
            owner_id=owner_id,
            slug=slug,
        )
        self._orgs[org.id] = org
        return org, True

    async def list_by_user(self, user_id):
        return [o for o in self._orgs.values() if o.owner_id == user_id]

    async def save(self, org):
        self._orgs[org.id] = org
        return org

    async def update(self, org):
        self._orgs[org.id] = org
        return org

    async def delete(self, org_id):
        self._orgs.pop(org_id, None)

    async def slug_exists(self, slug):
        return any(o.slug == slug for o in self._orgs.values())


class FakeMemberRepo(IOrgMemberRepository):
    def __init__(self) -> None:
        self._members: list[OrgMember] = []

    async def get_by_id(self, member_id):
        return next((m for m in self._members if m.id == member_id), None)

    async def get_by_user_and_org(self, user_id, org_id):
        return next(
            (m for m in self._members
             if m.user_id == user_id and m.organization_id == org_id),
            None,
        )

    async def list_by_user(self, user_id):
        return [m for m in self._members if m.user_id == user_id]

    async def list_by_org(self, org_id):
        return [m for m in self._members if m.organization_id == org_id]

    async def save(self, member):
        self._members.append(member)
        return member

    async def update(self, member):
        return member

    async def set_default(self, user_id, org_id):
        return None


class FakeRoleRepo(IRoleRepository):
    def __init__(self) -> None:
        self._roles: dict[uuid.UUID, Role] = {}

    async def get_by_id(self, role_id):
        return self._roles.get(role_id)

    async def get_by_slug(self, slug):
        return next((r for r in self._roles.values() if r.slug == slug), None)

    async def list_system_roles(self):
        return [r for r in self._roles.values() if r.is_system]

    async def list_by_org(self, org_id):
        return []

    async def save(self, role):
        self._roles[role.id] = role
        return role

    async def get_permissions_for_role(self, role_id):
        return set()

    async def set_permissions_for_role(self, role_id, permissions):
        return None


class FakeAuditRepo(IAuditLogRepository):
    def __init__(self):
        self.entries = []

    async def save(self, entry):
        self.entries.append(entry)
        return entry

    async def list_by_org(self, oid, limit=100, offset=0): return []
    async def list_by_user(self, uid, limit=100, offset=0): return []
    async def count_by_org(self, oid, since=None): return 0


class FakeOAuthSessionRepo(IOAuthSessionRepository):
    """In-memory fake mirroring the Redis repo contract: single-use consume,
    environment mismatch raises, consumed sessions are gone."""

    def __init__(self) -> None:
        self._sessions: dict[str, OAuthSession] = {}

    async def create(self, session: OAuthSession) -> None:
        self._sessions[session.state] = session

    async def get_and_consume(
        self, state: str, environment: SalesforceEnvironment,
    ) -> OAuthSession | None:
        session = self._sessions.get(state)
        if session is None:
            return None
        if session.environment != environment:
            raise InvalidOAuthStateError("OAuth environment mismatch")
        del self._sessions[state]
        return session

    def count(self) -> int:
        return len(self._sessions)


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
        self.session_repo = FakeOAuthSessionRepo()
        self.member_repo = FakeMemberRepo()
        self.role_repo = FakeRoleRepo()
        self.oauth = SalesforceOAuthService(self.settings)
        self.encryption = EncryptionService(self.settings)
        self.use_case = SalesforceUseCase(
            connection_repo=self.connection_repo,
            org_repo=self.org_repo,
            audit_log_repo=self.audit_repo,
            oauth_service=self.oauth,
            encryption_service=self.encryption,
            oauth_session_repo=self.session_repo,
            org_member_repo=self.member_repo,
            role_repo=self.role_repo,
        )
        self.org_id = uuid.uuid4()
        self.user_id = uuid.uuid4()

    async def _seed_session(
        self,
        state: str = "state",
        code_verifier: str = "session-verifier",
        user_id: uuid.UUID | None = None,
        organization_id: uuid.UUID | None = None,
        environment: SalesforceEnvironment = SalesforceEnvironment.PRODUCTION,
        ttl_seconds: int = 600,
    ) -> OAuthSession:
        session = OAuthSession.create(
            state=state,
            code_verifier=code_verifier,
            user_id=user_id if user_id is not None else self.user_id,
            organization_id=(
                organization_id if organization_id is not None else self.org_id
            ),
            environment=environment,
            ttl_seconds=ttl_seconds,
        )
        await self.session_repo.create(session)
        return session

    def _valid_token_response(self, **overrides) -> dict:
        payload = {
            "access_token": "00D-access-token",
            "refresh_token": "5AEP-refresh-token",
            "instance_url": "https://na1.salesforce.com",
            "id": "https://login.salesforce.com/id/00D000000000AAA/005000000000BBB",
            "username": "user@example.com",
        }
        payload.update(overrides)
        return payload

    def _patch_org_info(
        self, records: list[dict] | None = None, query_error: Exception | None = None,
    ):
        mock_instance = MagicMock(spec=SalesforceClient)
        if query_error:
            mock_instance.query = AsyncMock(side_effect=query_error)
        else:
            mock_instance.query = AsyncMock(return_value=records or [])
        mock_instance.close = AsyncMock()
        return patch(
            "sfir_backend.application.use_cases.salesforce.SalesforceClient",
            return_value=mock_instance,
        )

    @pytest.mark.asyncio
    async def test_initiate_connect_success(self) -> None:
        request = SalesforceConnectRequest(environment="production")
        response = await self.use_case.initiate_connect(request, self.org_id, self.user_id)

        assert response.authorization_url.startswith("https://login.salesforce.com")
        assert "response_type=code" in response.authorization_url
        assert response.environment == "production"
        assert not hasattr(response, "state")
        assert not hasattr(response, "code_verifier")

        assert self.session_repo.count() == 1
        session = next(iter(self.session_repo._sessions.values()))
        assert session.user_id == self.user_id
        assert session.organization_id == self.org_id
        assert session.environment == SalesforceEnvironment.PRODUCTION
        assert session.code_verifier not in response.authorization_url
        assert f"state={session.state}" in response.authorization_url

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

        assert self.session_repo.count() == 0

    @pytest.mark.asyncio
    async def test_initiate_connect_without_org_creates_null_org_session(self) -> None:
        request = SalesforceConnectRequest(environment="production")
        response = await self.use_case.initiate_connect(request, None, self.user_id)

        assert response.authorization_url.startswith("https://login.salesforce.com")
        assert self.session_repo.count() == 1
        session = next(iter(self.session_repo._sessions.values()))
        assert session.user_id == self.user_id
        assert session.organization_id is None
        assert f"state={session.state}" in response.authorization_url

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
        assert not hasattr(response, "state")
        assert not hasattr(response, "code_verifier")
        assert self.session_repo.count() == 1

    @pytest.mark.asyncio
    async def test_initiate_connect_fails_closed_without_session_repo(self) -> None:
        use_case = SalesforceUseCase(
            connection_repo=self.connection_repo,
            org_repo=self.org_repo,
            audit_log_repo=self.audit_repo,
            oauth_service=self.oauth,
            encryption_service=self.encryption,
        )
        request = SalesforceConnectRequest(environment="production")
        with pytest.raises(InvalidOAuthStateError, match="not configured"):
            await use_case.initiate_connect(request, self.org_id, self.user_id)

    @pytest.mark.asyncio
    async def test_handle_callback_fails_closed_without_session_repo(self) -> None:
        use_case = SalesforceUseCase(
            connection_repo=self.connection_repo,
            org_repo=self.org_repo,
            audit_log_repo=self.audit_repo,
            oauth_service=self.oauth,
            encryption_service=self.encryption,
        )
        request = SalesforceCallbackRequest(
            code="c", state="s", code_verifier="v", environment="production",
        )
        with pytest.raises(InvalidOAuthStateError, match="not configured"):
            await use_case.handle_callback(request, self.org_id, self.user_id)

    @pytest.mark.asyncio
    async def test_handle_callback_new_connection(self) -> None:
        await self._seed_session(state="state", code_verifier="session-verifier")

        with (
            patch.object(self.oauth, "exchange_code_for_tokens",
                          return_value=self._valid_token_response()) as mock_exchange,
            self._patch_org_info(
                records=[{"Name": "Acme", "OrganizationType": "Enterprise"}],
            ),
        ):
            request = SalesforceCallbackRequest(
                code="auth-code",
                state="state",
                code_verifier="browser-verifier-should-be-ignored",
                environment="production",
            )
            response = await self.use_case.handle_callback(
                request, self.org_id, self.user_id, ip_address="127.0.0.1",
            )
            mock_exchange.assert_awaited_once_with(
                code="auth-code",
                code_verifier="session-verifier",
                environment=SalesforceEnvironment.PRODUCTION,
            )
        assert response.org_id == "00D000000000AAA"
        assert response.username == "user@example.com"
        assert response.instance_url == "https://na1.salesforce.com"
        assert response.status == "connected"
        assert response.is_active is True
        assert response.organization_id != self.org_id

        workspace = await self.org_repo.get_by_salesforce_org_id("00D000000000AAA")
        assert workspace is not None
        assert workspace.status == OrganizationStatus.PROVISIONING
        assert workspace.salesforce_org_name == "Acme"
        assert workspace.organization_type == "Enterprise"
        assert workspace.instance_url == "https://na1.salesforce.com"
        assert workspace.owner_id == self.user_id
        assert workspace.slug == "sf-00d000000000aaa"

        member = await self.member_repo.get_by_user_and_org(
            self.user_id, workspace.id,
        )
        assert member is not None
        assert member.status == OrgMemberStatus.ACTIVE
        assert member.is_default is True
        owner_role = await self.role_repo.get_by_slug("owner")
        assert owner_role is not None
        assert member.role_id == owner_role.id

        saved = await self.connection_repo.get_by_org_and_user(
            workspace.id, self.user_id,
        )
        assert saved is not None
        assert saved.org_id == "00D000000000AAA"
        assert len(self.audit_repo.entries) == 2
        actions = {e.action for e in self.audit_repo.entries}
        assert actions == {"workspace.provisioned", "salesforce.connected"}
        assert self.audit_repo.entries[0].user_id == self.user_id
        assert self.session_repo.count() == 0

    @pytest.mark.asyncio
    async def test_handle_callback_updates_existing_connection(self) -> None:
        workspace, _ = await self.org_repo.find_or_create_by_salesforce_org_id(
            salesforce_org_id="00D000000000NNN",
            salesforce_org_name="Old Corp",
            instance_url="https://old.salesforce.com",
            organization_type="Enterprise",
            owner_id=self.user_id,
            slug="sf-00d000000000nnn",
        )
        existing = SalesforceConnection.create(
            organization_id=workspace.id,
            user_id=self.user_id,
            environment=SalesforceEnvironment.PRODUCTION,
            instance_url="https://old.salesforce.com",
            org_id="00D000000000NNN",
            username="old@example.com",
        )
        await self.connection_repo.save(existing)
        await self._seed_session(state="s", code_verifier="session-verifier")

        with (
            patch.object(self.oauth, "exchange_code_for_tokens",
                          return_value=self._valid_token_response(
                              access_token="new-access-token",
                              refresh_token="new-refresh-token",
                              instance_url="https://new.salesforce.com",
                              id="https://login.salesforce.com/id/00D000000000NNN/005000000000NNN",
                              username="new@example.com",
                          )),
            self._patch_org_info(),
        ):
            request = SalesforceCallbackRequest(
                code="new-code", state="s", code_verifier="v", environment="production",
            )
            response = await self.use_case.handle_callback(
                request, self.org_id, self.user_id,
            )

        assert response.org_id == "00D000000000NNN"
        assert response.username == "new@example.com"
        assert response.instance_url == "https://new.salesforce.com"
        assert response.id == existing.id
        assert response.organization_id == workspace.id

        _, created = await self.org_repo.find_or_create_by_salesforce_org_id(
            salesforce_org_id="00D000000000NNN",
            salesforce_org_name="x",
            instance_url="x",
            organization_type="x",
            owner_id=self.user_id,
            slug="x",
        )
        assert created is False
        assert len(self.audit_repo.entries) == 1
        assert self.audit_repo.entries[0].action == "salesforce.connected"

    @pytest.mark.asyncio
    async def test_handle_callback_missing_refresh_token(self) -> None:
        await self._seed_session(state="s")

        with (
            patch.object(self.oauth, "exchange_code_for_tokens",
                          return_value=self._valid_token_response(
                              refresh_token=None,
                          )),
            self._patch_org_info(),
        ):
            request = SalesforceCallbackRequest(
                code="c", state="s", code_verifier="v", environment="production",
            )
            response = await self.use_case.handle_callback(
                request, self.org_id, self.user_id,
            )

        assert response.status == "connected"
        assert response.org_id == "00D000000000AAA"

    @pytest.mark.asyncio
    async def test_handle_callback_missing_access_token_raises(self) -> None:
        await self._seed_session(state="s")

        with patch.object(self.oauth, "exchange_code_for_tokens", return_value={}):
            request = SalesforceCallbackRequest(
                code="c", state="s", code_verifier="v", environment="production",
            )
            with pytest.raises(ValueError, match="Invalid token response"):
                await self.use_case.handle_callback(request, self.org_id, self.user_id)

        assert self.session_repo.count() == 0
        saved = await self.connection_repo.get_by_org_and_user(self.org_id, self.user_id)
        assert saved is None
        assert self.audit_repo.entries == []

    @pytest.mark.asyncio
    async def test_handle_callback_invalid_state_rejected(self) -> None:
        request = SalesforceCallbackRequest(
            code="c", state="never-issued-state", code_verifier="v",
            environment="production",
        )
        with pytest.raises(InvalidOAuthStateError, match="Invalid, expired"):
            await self.use_case.handle_callback(request, self.org_id, self.user_id)

    @pytest.mark.asyncio
    async def test_handle_callback_environment_mismatch_rejected(self) -> None:
        await self._seed_session(
            state="s", environment=SalesforceEnvironment.SANDBOX,
        )
        request = SalesforceCallbackRequest(
            code="c", state="s", code_verifier="v", environment="production",
        )
        with pytest.raises(InvalidOAuthStateError):
            await self.use_case.handle_callback(request, self.org_id, self.user_id)
        assert self.session_repo.count() == 1

    @pytest.mark.asyncio
    async def test_handle_callback_expired_session_rejected(self) -> None:
        await self._seed_session(state="s", ttl_seconds=-1)
        request = SalesforceCallbackRequest(
            code="c", state="s", code_verifier="v", environment="production",
        )
        with pytest.raises(InvalidOAuthStateError):
            await self.use_case.handle_callback(request, self.org_id, self.user_id)

    @pytest.mark.asyncio
    async def test_handle_callback_replay_rejected(self) -> None:
        await self._seed_session(state="s")
        request = SalesforceCallbackRequest(
            code="c", state="s", code_verifier="v", environment="production",
        )
        with patch.object(self.oauth, "exchange_code_for_tokens",
                          return_value=self._valid_token_response()):
            await self.use_case.handle_callback(request, self.org_id, self.user_id)

        with pytest.raises(InvalidOAuthStateError, match="already-used"):
            await self.use_case.handle_callback(request, self.org_id, self.user_id)

    @pytest.mark.asyncio
    async def test_handle_callback_failed_exchange_consumes_session(self) -> None:
        await self._seed_session(state="s")
        request = SalesforceCallbackRequest(
            code="c", state="s", code_verifier="v", environment="production",
        )
        with (
            patch.object(self.oauth, "exchange_code_for_tokens",
                          side_effect=SalesforceOAuthError("invalid_grant")),
            pytest.raises(SalesforceOAuthError),
        ):
            await self.use_case.handle_callback(request, self.org_id, self.user_id)

        assert self.session_repo.count() == 0
        saved = await self.connection_repo.get_by_org_and_user(self.org_id, self.user_id)
        assert saved is None
        assert self.audit_repo.entries == []

    @pytest.mark.asyncio
    async def test_handle_callback_resolves_workspace_by_salesforce_org_id_only(
        self,
    ) -> None:
        stale_session_org = uuid.uuid4()
        session_user = uuid.uuid4()
        await self._seed_session(
            state="s",
            user_id=session_user,
            organization_id=stale_session_org,
        )

        with (
            patch.object(self.oauth, "exchange_code_for_tokens",
                          return_value=self._valid_token_response()),
            self._patch_org_info(),
        ):
            request = SalesforceCallbackRequest(
                code="c", state="s", code_verifier="ignored", environment="production",
            )
            response = await self.use_case.handle_callback(
                request, uuid.uuid4(), uuid.uuid4(),
            )

        workspace = await self.org_repo.get_by_salesforce_org_id("00D000000000AAA")
        assert workspace is not None
        assert workspace.id != stale_session_org
        assert response.organization_id == workspace.id
        assert self.audit_repo.entries[0].user_id == session_user
        saved = await self.connection_repo.get_by_org_and_user(
            workspace.id, session_user,
        )
        assert saved is not None

    @pytest.mark.asyncio
    async def test_handle_callback_reuses_existing_workspace(self) -> None:
        workspace, created = await self.org_repo.find_or_create_by_salesforce_org_id(
            salesforce_org_id="00D000000000AAA",
            salesforce_org_name="Pre-existing Org",
            instance_url="https://na1.salesforce.com",
            organization_type="Enterprise",
            owner_id=self.user_id,
            slug="sf-00d000000000aaa",
        )
        assert created is True
        await self._seed_session(state="s", organization_id=None)

        with (
            patch.object(self.oauth, "exchange_code_for_tokens",
                          return_value=self._valid_token_response()),
            self._patch_org_info(),
        ):
            request = SalesforceCallbackRequest(
                code="c", state="s", code_verifier="v", environment="production",
            )
            response = await self.use_case.handle_callback(
                request, self.org_id, self.user_id,
            )

        assert response.organization_id == workspace.id
        assert len(self.audit_repo.entries) == 1
        assert self.audit_repo.entries[0].action == "salesforce.connected"
        members = await self.member_repo.list_by_org(workspace.id)
        assert len(members) == 1

    @pytest.mark.asyncio
    async def test_handle_callback_org_info_failure_falls_back(self) -> None:
        await self._seed_session(state="s")

        with (
            patch.object(self.oauth, "exchange_code_for_tokens",
                          return_value=self._valid_token_response()),
            self._patch_org_info(query_error=SalesforceAuthError("unauthorized")),
        ):
            request = SalesforceCallbackRequest(
                code="c", state="s", code_verifier="v", environment="production",
            )
            response = await self.use_case.handle_callback(
                request, self.org_id, self.user_id,
            )

        assert response.status == "connected"
        workspace = await self.org_repo.get_by_salesforce_org_id("00D000000000AAA")
        assert workspace is not None
        assert workspace.salesforce_org_name == "Salesforce Org 00D000000000AAA"
        assert workspace.organization_type == "Unknown"

    @pytest.mark.asyncio
    async def test_handle_callback_missing_org_id_raises(self) -> None:
        await self._seed_session(state="s")

        with patch.object(
            self.oauth, "exchange_code_for_tokens",
            return_value=self._valid_token_response(
                id="https://login.salesforce.com/id/",
            ),
        ):
            request = SalesforceCallbackRequest(
                code="c", state="s", code_verifier="v", environment="production",
            )
            with pytest.raises(ValueError, match="missing org id"):
                await self.use_case.handle_callback(request, self.org_id, self.user_id)

    @pytest.mark.asyncio
    async def test_handle_callback_queues_initial_sync(self) -> None:
        sync_coordinator = MagicMock()
        sync_coordinator.start_sync = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
        self.use_case._sync_coordinator = sync_coordinator
        await self._seed_session(state="s")

        with (
            patch.object(self.oauth, "exchange_code_for_tokens",
                          return_value=self._valid_token_response()),
            self._patch_org_info(),
        ):
            request = SalesforceCallbackRequest(
                code="c", state="s", code_verifier="v", environment="production",
            )
            await self.use_case.handle_callback(request, self.org_id, self.user_id)

        workspace = await self.org_repo.get_by_salesforce_org_id("00D000000000AAA")
        connection = await self.connection_repo.get_by_org_and_user(
            workspace.id, self.user_id,
        )
        sync_coordinator.start_sync.assert_awaited_once()
        call = sync_coordinator.start_sync.await_args
        assert call.args[0].connection_id == connection.id
        assert call.args[0].sync_type == "full"

    @pytest.mark.asyncio
    async def test_handle_callback_second_user_reuses_workspace(self) -> None:
        owner_user = uuid.uuid4()
        second_user = uuid.uuid4()
        workspace, created = await self.org_repo.find_or_create_by_salesforce_org_id(
            salesforce_org_id="00D000000000AAA",
            salesforce_org_name="Shared Org",
            instance_url="https://na1.salesforce.com",
            organization_type="Enterprise",
            owner_id=owner_user,
            slug="sf-00d000000000aaa",
        )
        assert created is True
        await self._seed_session(
            state="s", user_id=second_user, organization_id=None,
        )

        with (
            patch.object(self.oauth, "exchange_code_for_tokens",
                          return_value=self._valid_token_response(
                              username="second@example.com",
                          )),
            self._patch_org_info(),
        ):
            request = SalesforceCallbackRequest(
                code="c", state="s", code_verifier="v", environment="production",
            )
            response = await self.use_case.handle_callback(
                request, self.org_id, second_user,
            )

        assert response.organization_id == workspace.id
        assert response.username == "second@example.com"
        assert len(self.org_repo._orgs) == 1
        assert workspace.owner_id == owner_user
        assert workspace.salesforce_org_name == "Shared Org"

        members = await self.member_repo.list_by_org(workspace.id)
        assert len(members) == 1
        assert members[0].user_id == second_user
        assert members[0].is_default is True

        saved = await self.connection_repo.get_by_org_and_user(
            workspace.id, second_user,
        )
        assert saved is not None
        assert saved.username == "second@example.com"
        assert await self.connection_repo.get_by_org_and_user(
            workspace.id, owner_user,
        ) is None
        assert len(self.audit_repo.entries) == 1
        assert self.audit_repo.entries[0].action == "salesforce.connected"

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
