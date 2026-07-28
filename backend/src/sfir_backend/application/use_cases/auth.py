import uuid
from datetime import UTC, datetime, timedelta

from sfir_backend.application.dto.auth import (
    CurrentUserResponse,
    LoginRequest,
    LoginResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    RegisterRequest,
)
from sfir_backend.domain.entities.audit_log import AuditLogEntry
from sfir_backend.domain.entities.refresh_token import RefreshToken
from sfir_backend.domain.entities.session import Session
from sfir_backend.domain.entities.user import User
from sfir_backend.domain.repositories import (
    IAuditLogRepository,
    IOrganizationRepository,
    IOrgMemberRepository,
    IRefreshTokenRepository,
    IRoleRepository,
    ISessionRepository,
    IUserRepository,
)
from sfir_backend.domain.value_objects.email import Email
from sfir_backend.infrastructure.security.jwt import JWTService
from sfir_backend.infrastructure.security.password import PasswordService
from sfir_backend.shared.exceptions.application import (
    AuthenticationFailedError,
    ConflictError,
)
from sfir_backend.shared.exceptions.domain import ValidationError


class AuthUseCase:
    def __init__(
        self,
        user_repo: IUserRepository,
        org_repo: IOrganizationRepository,
        org_member_repo: IOrgMemberRepository,
        session_repo: ISessionRepository,
        refresh_token_repo: IRefreshTokenRepository,
        role_repo: IRoleRepository,
        audit_log_repo: IAuditLogRepository,
        password_service: PasswordService,
        jwt_service: JWTService,
    ) -> None:
        self._user_repo = user_repo
        self._org_repo = org_repo
        self._org_member_repo = org_member_repo
        self._session_repo = session_repo
        self._refresh_token_repo = refresh_token_repo
        self._role_repo = role_repo
        self._audit_log_repo = audit_log_repo
        self._password_service = password_service
        self._jwt_service = jwt_service

    async def register(self, request: RegisterRequest) -> LoginResponse:
        try:
            email = Email(request.email)
        except ValueError:
            raise ValidationError("Invalid email format")
        if await self._user_repo.email_exists(email):
            raise ConflictError("Email already registered")

        password_hash = self._password_service.hash_password(request.password)
        user = User.create(
            email=str(email),
            password_hash=password_hash,
            display_name=request.display_name,
        )
        await self._user_repo.save(user)

        await self._audit_log_repo.save(AuditLogEntry.create(
            action="user.registered",
            resource_type="user",
            resource_id=str(user.id),
            details={"email": str(email)},
        ))

        return await self._create_login_response(user)

    async def login(self, request: LoginRequest) -> LoginResponse:
        try:
            email = Email(request.email)
        except ValueError:
            raise AuthenticationFailedError("Invalid email or password")
        user = await self._user_repo.get_by_email(email)
        if not user:
            raise AuthenticationFailedError("Invalid email or password")

        if not user.can_login:
            raise AuthenticationFailedError("Account is locked or disabled")

        if not self._password_service.verify_password(
            request.password, user.password_hash,
        ):
            user.record_failed_login()
            if user.login_attempts >= 5:
                user.lock()
            await self._user_repo.update(user)
            raise AuthenticationFailedError("Invalid email or password")

        user.record_login()
        await self._user_repo.update(user)

        await self._audit_log_repo.save(AuditLogEntry.create(
            action="user.login",
            resource_type="user",
            resource_id=str(user.id),
            user_id=user.id,
            ip_address=request.ip_address,
        ))

        return await self._create_login_response(
            user, ip_address=request.ip_address, user_agent=request.user_agent,
        )

    async def logout(self, user_id: uuid.UUID) -> None:
        await self._refresh_token_repo.revoke_all_for_user(user_id)
        await self._session_repo.revoke_all_for_user(user_id)

        await self._audit_log_repo.save(AuditLogEntry.create(
            action="user.logout",
            resource_type="user",
            resource_id=str(user_id),
            user_id=user_id,
        ))

    async def refresh(self, request: RefreshTokenRequest) -> RefreshTokenResponse:
        token_hash = self._jwt_service.hash_token(request.refresh_token)
        stored = await self._refresh_token_repo.get_by_token_hash(token_hash)
        if not stored or stored.is_revoked or stored.is_expired:
            raise AuthenticationFailedError("Invalid or expired refresh token")

        stored.revoke()
        await self._refresh_token_repo.revoke(stored.id)

        user = await self._user_repo.get_by_id(stored.user_id)
        if not user:
            raise AuthenticationFailedError("User not found")

        raw_token, token_id, expires_at = self._jwt_service.create_refresh_token()
        new_stored = RefreshToken(
            id=uuid.UUID(token_id),
            user_id=user.id,
            token_hash=self._jwt_service.hash_token(raw_token),
            expires_at=expires_at,
        )
        await self._refresh_token_repo.save(new_stored)

        org_id = None
        memberships = await self._org_member_repo.list_by_user(user.id)
        if memberships:
            default = next((m for m in memberships if m.is_default), memberships[0])
            org_id = default.organization_id

        access_token = self._jwt_service.create_access_token(
            user_id=user.id,
            organization_id=org_id,
        )

        return RefreshTokenResponse(
            access_token=access_token,
            refresh_token=raw_token,
            expires_in=self._jwt_service.get_access_token_expire_minutes() * 60,
        )

    async def get_current_user(
        self,
        user_id: uuid.UUID,
        org_id: uuid.UUID | None = None,
    ) -> CurrentUserResponse:
        user = await self._user_repo.get_by_id(user_id)
        if not user:
            raise AuthenticationFailedError("User not found")

        permissions: set[str] = set()
        org_name: str | None = None

        if org_id:
            membership = await self._org_member_repo.get_by_user_and_org(
                user_id, org_id,
            )
            if membership:
                org = await self._org_repo.get_by_id(org_id)
                if org:
                    org_name = org.name
                permissions = await self._role_repo.get_permissions_for_role(
                    membership.role_id,
                )

        return CurrentUserResponse(
            user_id=user.id,
            email=str(user.email),
            display_name=user.display_name,
            status=user.status.value,
            email_verified=user.email_verified_at is not None,
            last_login_at=user.last_login_at,
            current_organization_id=org_id,
            current_organization_name=org_name,
            permissions=list(permissions),
        )

    async def _create_login_response(
        self,
        user: User,
        ip_address: str = "",
        user_agent: str = "",
    ) -> LoginResponse:
        raw_token, token_id, expires_at = self._jwt_service.create_refresh_token()
        stored_token = RefreshToken(
            id=uuid.UUID(token_id),
            user_id=user.id,
            token_hash=self._jwt_service.hash_token(raw_token),
            expires_at=expires_at,
        )
        await self._refresh_token_repo.save(stored_token)

        org_id: uuid.UUID | None = None
        org_name: str | None = None
        role_slug: str | None = None
        permissions: set[str] = set()

        memberships = await self._org_member_repo.list_by_user(user.id)
        if memberships:
            default = next(
                (m for m in memberships if m.is_default), memberships[0],
            )
            org_id = default.organization_id
            org = await self._org_repo.get_by_id(org_id)
            if org:
                org_name = org.name
            role = await self._role_repo.get_by_id(default.role_id)
            if role:
                role_slug = role.slug
                permissions = await self._role_repo.get_permissions_for_role(
                    default.role_id,
                )

        session_expires = datetime.now(UTC) + timedelta(days=7)
        session = Session.create(
            user_id=user.id,
            organization_id=org_id,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=session_expires,
        )
        session.refresh_token_id = stored_token.id
        await self._session_repo.save(session)

        access_token = self._jwt_service.create_access_token(
            user_id=user.id,
            organization_id=org_id,
            role_slug=role_slug or "",
            permissions=permissions,
        )

        return LoginResponse(
            user_id=user.id,
            email=str(user.email),
            display_name=user.display_name,
            access_token=access_token,
            refresh_token=raw_token,
            expires_in=self._jwt_service.get_access_token_expire_minutes() * 60,
            organization_id=org_id,
            organization_name=org_name,
            role_slug=role_slug,
        )
