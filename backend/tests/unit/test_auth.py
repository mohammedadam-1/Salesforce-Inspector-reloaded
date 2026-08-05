"""Tests for authentication use case and security services."""

import uuid
from datetime import UTC

import pytest

from sfir_backend.application.dto.auth import (
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
)
from sfir_backend.application.use_cases.auth import AuthUseCase
from sfir_backend.config.settings import Settings
from sfir_backend.domain.entities.user import User
from sfir_backend.domain.repositories import (
    IUserRepository,
)
from sfir_backend.domain.value_objects.email import Email
from sfir_backend.infrastructure.security.jwt import JWTService
from sfir_backend.infrastructure.security.password import PasswordService
from sfir_backend.shared.exceptions.application import (
    AuthenticationFailedError,
    ConflictError,
)


class FakeUserRepo(IUserRepository):
    def __init__(self) -> None:
        self._users: dict[uuid.UUID, User] = {}
        self._emails: dict[str, User] = {}

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return self._users.get(user_id)

    async def get_by_email(self, email: Email) -> User | None:
        return self._emails.get(str(email))

    async def email_exists(self, email: Email) -> bool:
        return str(email) in self._emails

    async def save(self, user: User) -> User:
        self._users[user.id] = user
        self._emails[str(user.email)] = user
        return user

    async def update(self, user: User) -> User:
        self._users[user.id] = user
        self._emails[str(user.email)] = user
        return user

    async def update_login_attempts(
        self, user_id: uuid.UUID, attempts: int,
    ) -> None:
        if user_id in self._users:
            self._users[user_id].login_attempts = attempts


class FakeRepo(dict):
    pass


async def _make_auth_use_case() -> AuthUseCase:
    settings = Settings(environment="testing")
    from sfir_backend.domain.repositories.audit_log_repo import IAuditLogRepository
    from sfir_backend.domain.repositories.org_member_repo import IOrgMemberRepository
    from sfir_backend.domain.repositories.organization_repo import (
        IOrganizationRepository,
    )
    from sfir_backend.domain.repositories.refresh_token_repo import (
        IRefreshTokenRepository,
    )
    from sfir_backend.domain.repositories.role_repo import IRoleRepository
    from sfir_backend.domain.repositories.session_repo import ISessionRepository

    class FakeOrgRepo(IOrganizationRepository):
        async def get_by_id(self, org_id): return None
        async def get_by_slug(self, slug): return None
        async def get_by_salesforce_org_id(self, salesforce_org_id): return None
        async def list_by_user(self, user_id): return []
        async def save(self, org): return org
        async def update(self, org): return org
        async def delete(self, org_id): return None
        async def slug_exists(self, slug): return False

    class FakeMemberRepo(IOrgMemberRepository):
        def __init__(self):
            self.members = []
        async def get_by_id(self, mid): return None
        async def get_by_user_and_org(self, uid, oid): return None
        async def list_by_user(self, uid): return []
        async def list_by_org(self, oid): return []
        async def save(self, m):
            self.members.append(m)
            return m
        async def update(self, m): return m
        async def set_default(self, uid, oid): return None

    class FakeSessionRepo(ISessionRepository):
        async def get_by_id(self, sid): return None
        async def list_active_by_user(self, uid): return []
        async def save(self, s): return s
        async def revoke(self, sid): return None
        async def revoke_all_for_user(self, uid): return None

    class FakeRefreshRepo(IRefreshTokenRepository):
        def __init__(self):
            self.tokens = {}
        async def get_by_id(self, tid): return None
        async def get_by_token_hash(self, h): return self.tokens.get(h)
        async def save(self, t):
            self.tokens[t.token_hash] = t
            return t
        async def revoke(self, tid): return None
        async def revoke_all_for_user(self, uid): return None

    class FakeRoleRepo(IRoleRepository):
        async def get_by_id(self, rid): return None
        async def get_by_slug(self, slug): return None
        async def list_system_roles(self): return []
        async def list_by_org(self, oid): return []
        async def save(self, r): return r
        async def get_permissions_for_role(self, rid): return set()
        async def set_permissions_for_role(self, rid, perms): return None

    class FakeAuditRepo(IAuditLogRepository):
        async def save(self, e): return e
        async def list_by_org(self, oid, limit=100, offset=0): return []
        async def list_by_user(self, uid, limit=100, offset=0): return []
        async def count_by_org(self, oid, since=None): return 0

    return AuthUseCase(
        user_repo=FakeUserRepo(),
        org_repo=FakeOrgRepo(),
        org_member_repo=FakeMemberRepo(),
        session_repo=FakeSessionRepo(),
        refresh_token_repo=FakeRefreshRepo(),
        role_repo=FakeRoleRepo(),
        audit_log_repo=FakeAuditRepo(),
        password_service=PasswordService(),
        jwt_service=JWTService(settings),
    )


class TestPasswordService:
    def test_hash_and_verify(self) -> None:
        pwd = "SecureP@ss123!"
        hashed = PasswordService.hash_password(pwd)
        assert hashed != pwd
        assert PasswordService.verify_password(pwd, hashed)

    def test_wrong_password(self) -> None:
        hashed = PasswordService.hash_password("correct")
        assert not PasswordService.verify_password("wrong", hashed)

    def test_generate_token(self) -> None:
        token = PasswordService.generate_token()
        assert len(token) == 64
        assert isinstance(token, str)


class TestJWTService:
    def setup_method(self) -> None:
        settings = Settings(environment="testing")
        self.jwt = JWTService(settings)

    def test_create_access_token(self) -> None:
        uid = uuid.uuid4()
        token = self.jwt.create_access_token(user_id=uid)
        payload = self.jwt.decode_access_token(token)
        assert payload["sub"] == str(uid)
        assert payload["type"] == "access"

    def test_access_token_with_org(self) -> None:
        uid = uuid.uuid4()
        oid = uuid.uuid4()
        token = self.jwt.create_access_token(
            user_id=uid, organization_id=oid, role_slug="admin",
            permissions={"org:manage", "users:manage"},
        )
        payload = self.jwt.decode_access_token(token)
        assert payload["org"] == str(oid)
        assert payload["role"] == "admin"
        assert "org:manage" in payload["permissions"]

    def test_expired_token_raises(self) -> None:
        from datetime import datetime, timedelta

        from jose import jwt

        uid = uuid.uuid4()
        settings = Settings(environment="testing")
        secret = settings.jwt_secret_key.get_secret_value()
        expired = jwt.encode(
            {
                "sub": str(uid),
                "type": "access",
                "exp": datetime.now(UTC) - timedelta(hours=1),
                "iss": self.jwt._issuer,
            },
            secret,
            algorithm="HS256",
        )
        with pytest.raises(ValueError, match="has expired"):
            self.jwt.decode_access_token(expired)

    def test_wrong_token_type(self) -> None:
        uid = uuid.uuid4()
        settings = Settings(environment="testing")
        secret = settings.jwt_secret_key.get_secret_value()
        from datetime import datetime, timedelta

        from jose import jwt

        bad = jwt.encode(
            {
                "sub": str(uid),
                "type": "refresh",
                "exp": datetime.now(UTC) + timedelta(hours=1),
                "iss": self.jwt._issuer,
            },
            secret,
            algorithm="HS256",
        )
        with pytest.raises(ValueError, match="Invalid token type"):
            self.jwt.decode_access_token(bad)

    def test_hash_token(self) -> None:
        raw = "some-refresh-token-value"
        h1 = JWTService.hash_token(raw)
        h2 = JWTService.hash_token(raw)
        assert h1 == h2
        assert h1 != raw


class TestAuthUseCase:
    @pytest.mark.asyncio
    async def test_register_success(self) -> None:
        auth = await _make_auth_use_case()
        result = await auth.register(RegisterRequest(
            email="test@example.com",
            password="StrongP@ss1",
            display_name="Test User",
        ))
        assert result.email == "test@example.com"
        assert result.user_id is not None
        assert result.access_token is not None
        assert result.refresh_token is not None

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self) -> None:
        auth = await _make_auth_use_case()
        await auth.register(RegisterRequest(
            email="dup@example.com", password="StrongP@ss1", display_name="U1",
        ))
        with pytest.raises(ConflictError):
            await auth.register(RegisterRequest(
                email="dup@example.com", password="StrongP@ss2", display_name="U2",
            ))

    @pytest.mark.asyncio
    async def test_login_success(self) -> None:
        auth = await _make_auth_use_case()
        await auth.register(RegisterRequest(
            email="login@example.com", password="StrongP@ss1", display_name="Login",
        ))
        result = await auth.login(LoginRequest(
            email="login@example.com", password="StrongP@ss1",
        ))
        assert result.email == "login@example.com"
        assert result.access_token is not None

    @pytest.mark.asyncio
    async def test_login_wrong_password(self) -> None:
        auth = await _make_auth_use_case()
        await auth.register(RegisterRequest(
            email="wrong@example.com", password="CorrectP@ss1", display_name="W",
        ))
        with pytest.raises(AuthenticationFailedError):
            await auth.login(LoginRequest(
                email="wrong@example.com", password="WrongP@ss1",
            ))

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self) -> None:
        auth = await _make_auth_use_case()
        with pytest.raises(AuthenticationFailedError):
            await auth.login(LoginRequest(
                email="nobody@example.com", password="SomeP@ss1",
            ))

    @pytest.mark.asyncio
    async def test_refresh_token_rotation(self) -> None:
        auth = await _make_auth_use_case()
        register_result = await auth.register(RegisterRequest(
            email="rotate@example.com", password="StrongP@ss1", display_name="R",
        ))
        refresh_result = await auth.refresh(RefreshTokenRequest(
            refresh_token=register_result.refresh_token,
        ))
        assert refresh_result.access_token is not None
        assert refresh_result.refresh_token is not None
        assert refresh_result.refresh_token != register_result.refresh_token

    @pytest.mark.asyncio
    async def test_refresh_with_invalid_token(self) -> None:
        auth = await _make_auth_use_case()
        with pytest.raises(AuthenticationFailedError):
            await auth.refresh(RefreshTokenRequest(refresh_token="invalid-token"))
