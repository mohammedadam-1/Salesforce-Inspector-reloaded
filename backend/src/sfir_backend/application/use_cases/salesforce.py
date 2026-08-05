import contextlib
import uuid

import structlog

from sfir_backend.application.dto.metadata_sync import StartSyncRequest
from sfir_backend.application.dto.salesforce import (
    SalesforceCallbackRequest,
    SalesforceConnectionResponse,
    SalesforceConnectRequest,
    SalesforceConnectResponse,
    SalesforceHealthResponse,
)
from sfir_backend.application.use_cases.metadata_sync import SyncCoordinator
from sfir_backend.application.use_cases.organization import _OWNER_PERMISSIONS
from sfir_backend.domain.entities.audit_log import AuditLogEntry
from sfir_backend.domain.entities.oauth_session import OAuthSession
from sfir_backend.domain.entities.org_member import OrgMember
from sfir_backend.domain.entities.role import Role
from sfir_backend.domain.entities.salesforce_connection import (
    SalesforceConnection,
)
from sfir_backend.domain.repositories.audit_log_repo import IAuditLogRepository
from sfir_backend.domain.repositories.oauth_session_repo import (
    IOAuthSessionRepository,
)
from sfir_backend.domain.repositories.org_member_repo import IOrgMemberRepository
from sfir_backend.domain.repositories.organization_repo import (
    IOrganizationRepository,
)
from sfir_backend.domain.repositories.role_repo import IRoleRepository
from sfir_backend.domain.repositories.salesforce_repos import (
    ISalesforceConnectionRepository,
)
from sfir_backend.domain.value_objects.salesforce import (
    SalesforceEnvironment,
)
from sfir_backend.infrastructure.salesforce.client import SalesforceClient
from sfir_backend.infrastructure.salesforce.oauth import (
    SalesforceOAuthService,
)
from sfir_backend.infrastructure.security.encryption import EncryptionService
from sfir_backend.shared.exceptions.application import (
    ConflictError,
    InvalidOAuthStateError,
)
from sfir_backend.shared.exceptions.domain import EntityNotFoundError

logger = structlog.get_logger(__name__)


class SalesforceUseCase:
    def __init__(
        self,
        connection_repo: ISalesforceConnectionRepository,
        org_repo: IOrganizationRepository,
        audit_log_repo: IAuditLogRepository,
        oauth_service: SalesforceOAuthService,
        encryption_service: EncryptionService,
        sync_coordinator: SyncCoordinator | None = None,
        oauth_session_repo: IOAuthSessionRepository | None = None,
        org_member_repo: IOrgMemberRepository | None = None,
        role_repo: IRoleRepository | None = None,
    ) -> None:
        self._connection_repo = connection_repo
        self._org_repo = org_repo
        self._audit_log_repo = audit_log_repo
        self._oauth_service = oauth_service
        self._encryption_service = encryption_service
        self._sync_coordinator = sync_coordinator
        self._oauth_session_repo = oauth_session_repo
        self._org_member_repo = org_member_repo
        self._role_repo = role_repo

    async def initiate_connect(
        self,
        request: SalesforceConnectRequest,
        organization_id: uuid.UUID | None,
        user_id: uuid.UUID,
    ) -> SalesforceConnectResponse:
        if self._oauth_session_repo is None:
            raise InvalidOAuthStateError("OAuth session store not configured")

        environment = self._oauth_service.validate_environment(request.environment)

        if organization_id is not None:
            existing = await self._connection_repo.get_by_org_and_user(
                organization_id,
                user_id,
            )
            if existing and existing.is_active:
                raise ConflictError(
                    "An active Salesforce connection already exists for this org",
                )

        state = self._oauth_service.generate_state()
        pkce = self._oauth_service.generate_pkce_pair()

        session = OAuthSession.create(
            state=state,
            code_verifier=pkce["code_verifier"],
            user_id=user_id,
            organization_id=organization_id,
            environment=environment,
        )
        await self._oauth_session_repo.create(session)

        auth_url = self._oauth_service.build_authorization_url(
            environment=environment,
            state=state,
            code_challenge=pkce["code_challenge"],
        )

        return SalesforceConnectResponse(
            authorization_url=auth_url,
            environment=request.environment,
        )

    async def handle_callback(
        self,
        request: SalesforceCallbackRequest,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        ip_address: str = "",
    ) -> SalesforceConnectionResponse:
        if self._oauth_session_repo is None:
            raise InvalidOAuthStateError("OAuth session store not configured")

        environment = self._oauth_service.validate_environment(request.environment)

        # Consume the session (single-use) before any token exchange. A failed
        # exchange never restores the session: the client must start over.
        session = await self._oauth_session_repo.get_and_consume(
            request.state,
            environment,
        )
        if session is None:
            raise InvalidOAuthStateError(
                "Invalid, expired, or already-used OAuth state.",
            )
        session.validate(environment)

        # Identity (user) and PKCE verifier come from the server-side session,
        # never from browser-supplied values or the route's JWT context.
        user_id = session.user_id
        code_verifier = session.code_verifier

        token_response = await self._oauth_service.exchange_code_for_tokens(
            code=request.code,
            code_verifier=code_verifier,
            environment=environment,
        )

        access_token = token_response.get("access_token", "")
        refresh_token = token_response.get("refresh_token", "")
        instance_url = token_response.get("instance_url", "")
        id_parts = token_response.get("id", "").split("/")
        sf_org_id = id_parts[-2] if len(id_parts) >= 2 else ""
        username = token_response.get("username", "")
        expires_in = int(token_response.get("expires_in") or 3600)

        if not access_token or not instance_url:
            raise ValueError("Invalid token response from Salesforce")
        if not sf_org_id or len(sf_org_id) not in (15, 18) or not sf_org_id.isalnum():
            raise ValueError(
                "Invalid token response from Salesforce: missing org id",
            )

        access_encrypted = self._encryption_service.encrypt(access_token)
        refresh_encrypted = self._encryption_service.encrypt(refresh_token) if refresh_token else ""

        # Workspace resolution: the Salesforce org id is the immutable tenant
        # identifier. The backend Organization is resolved ONLY by this value
        # — never by organization name, instance URL, username, or email.
        org_name, org_type = await self._fetch_org_info(
            instance_url=instance_url,
            access_token=access_token,
        )
        org, workspace_created = await self._org_repo.find_or_create_by_salesforce_org_id(
            salesforce_org_id=sf_org_id,
            salesforce_org_name=org_name or f"Salesforce Org {sf_org_id}",
            instance_url=instance_url,
            organization_type=org_type or "Unknown",
            owner_id=user_id,
            slug=f"sf-{sf_org_id.lower()}",
        )
        organization_id = org.id
        if workspace_created:
            logger.info(
                "workspace_provisioned",
                organization_id=str(organization_id),
                salesforce_org_id=sf_org_id,
            )
        await self._ensure_owner_membership(
            organization_id=organization_id,
            user_id=user_id,
        )

        existing = await self._connection_repo.get_by_org_and_user(
            organization_id,
            user_id,
        )
        if not existing:
            existing = await self._connection_repo.get_inactive_by_org_and_user(
                organization_id,
                user_id,
            )

        if existing:
            connection = existing
            connection.mark_connected(
                access_token_encrypted=access_encrypted,
                refresh_token_encrypted=refresh_encrypted,
                expires_in=expires_in,
            )
            connection.instance_url = instance_url
            connection.org_id = sf_org_id
            connection.username = username
            await self._connection_repo.update(connection)
        else:
            connection = SalesforceConnection.create(
                organization_id=organization_id,
                user_id=user_id,
                environment=environment,
                instance_url=instance_url,
                org_id=sf_org_id,
                username=username,
            )
            connection.mark_connected(
                access_token_encrypted=access_encrypted,
                refresh_token_encrypted=refresh_encrypted,
                expires_in=expires_in,
            )
            await self._connection_repo.save(connection)

        if workspace_created:
            await self._audit_log_repo.save(
                AuditLogEntry.create(
                    action="workspace.provisioned",
                    resource_type="organization",
                    resource_id=str(organization_id),
                    user_id=user_id,
                    organization_id=organization_id,
                    details={
                        "salesforce_org_id": sf_org_id,
                        "salesforce_org_name": org.salesforce_org_name,
                        "organization_type": org.organization_type,
                        "instance_url": org.instance_url,
                        "owner_membership": True,
                    },
                    ip_address=ip_address,
                )
            )

        await self._audit_log_repo.save(
            AuditLogEntry.create(
                action="salesforce.connected",
                resource_type="salesforce_connection",
                resource_id=str(connection.id),
                user_id=user_id,
                organization_id=organization_id,
                details={"environment": request.environment, "org_id": sf_org_id},
                ip_address=ip_address,
            )
        )

        logger.info(
            "salesforce_connection_established",
            connection_id=str(connection.id),
            org_id=sf_org_id,
            environment=request.environment,
        )

        if self._sync_coordinator:
            try:
                sync_req = StartSyncRequest(
                    connection_id=connection.id,
                    sync_type="full",
                )
                await self._sync_coordinator.start_sync(
                    sync_req,
                    organization_id,
                    user_id,
                )
                logger.info(
                    "initial_sync_started",
                    connection_id=str(connection.id),
                )
            except Exception as sync_err:
                logger.warning(
                    "initial_sync_failed_to_start",
                    connection_id=str(connection.id),
                    error=str(sync_err),
                )

        return self._to_response(connection)

    async def disconnect(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        ip_address: str = "",
    ) -> None:
        connection = await self._connection_repo.get_by_org_and_user(
            organization_id,
            user_id,
        )
        if not connection:
            raise EntityNotFoundError("SalesforceConnection", str(organization_id))

        decrypted_refresh = ""
        if connection.refresh_token_encrypted:
            with contextlib.suppress(Exception):
                decrypted_refresh = self._encryption_service.decrypt(
                    connection.refresh_token_encrypted,
                )

        connection.mark_disconnected()
        await self._connection_repo.update(connection)

        if decrypted_refresh:
            try:
                environment = SalesforceEnvironment(connection.environment.value)
                await self._oauth_service.revoke_token(
                    decrypted_refresh,
                    environment=environment,
                )
            except Exception:
                logger.warning(
                    "salesforce_token_revoke_failed",
                    connection_id=str(connection.id),
                )

        await self._audit_log_repo.save(
            AuditLogEntry.create(
                action="salesforce.disconnected",
                resource_type="salesforce_connection",
                resource_id=str(connection.id),
                user_id=user_id,
                organization_id=organization_id,
                ip_address=ip_address,
            )
        )

    async def get_status(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> SalesforceConnectionResponse | None:
        connection = await self._connection_repo.get_by_org_and_user(
            organization_id,
            user_id,
        )
        if not connection:
            return None
        return self._to_response(connection)

    async def check_health(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> SalesforceHealthResponse:
        connection = await self._connection_repo.get_by_org_and_user(
            organization_id,
            user_id,
        )
        if not connection:
            raise EntityNotFoundError("SalesforceConnection", str(organization_id))

        try:
            access_token = self._encryption_service.decrypt(
                connection.access_token_encrypted,
            )
        except Exception:
            return SalesforceHealthResponse(
                connection_id=connection.id,
                status=connection.status.value,
                is_token_valid=False,
                error_message="Failed to decrypt access token",
            )

        try:
            client = SalesforceClient(
                instance_url=connection.instance_url,
                api_version=connection.api_version,
            )
            client.set_access_token(access_token)

            limits = await client.get_limits()
            org_info = await client.rest("/sobjects/Organization/describe")

            connection.last_successful_sync_at = None
            await self._connection_repo.update(connection)

            await client.close()

            return SalesforceHealthResponse(
                connection_id=connection.id,
                status=connection.status.value,
                is_token_valid=True,
                limits=limits,
                org_info=org_info,
            )
        except Exception as exc:
            connection.mark_failed(str(exc))
            await self._connection_repo.update(connection)

            return SalesforceHealthResponse(
                connection_id=connection.id,
                status=connection.status.value,
                is_token_valid=False,
                error_message=str(exc),
            )

    async def _fetch_org_info(
        self,
        *,
        instance_url: str,
        access_token: str,
    ) -> tuple[str, str]:
        """Best-effort org name/type from the Organization sobject.

        The Salesforce org id (canonical tenant key) comes from the token
        response itself; name/type are descriptive only, so any failure
        degrades to empty strings (caller falls back to stable values)
        instead of failing the callback.
        """
        client = SalesforceClient(
            instance_url=instance_url,
            api_version=self._oauth_service.get_default_api_version(),
        )
        try:
            client.set_access_token(access_token)
            records = await client.query(
                "SELECT Id, Name, OrganizationType FROM Organization LIMIT 1",
            )
            if records:
                record = records[0]
                return (
                    str(record.get("Name") or ""),
                    str(record.get("OrganizationType") or ""),
                )
        except Exception as exc:
            logger.warning(
                "workspace_org_info_fetch_failed",
                error=str(exc),
            )
        finally:
            await client.close()
        return "", ""

    async def _ensure_owner_membership(
        self,
        *,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Idempotently grant the authenticated user OWNER membership.

        The workspace owner is the SFIR user who completed the OAuth flow;
        a pre-existing membership (e.g. reconnect after disconnect) is left
        untouched.
        """
        if self._org_member_repo is None:
            raise InvalidOAuthStateError("Org membership store not configured")
        if self._role_repo is None:
            raise InvalidOAuthStateError("Role store not configured")

        existing = await self._org_member_repo.get_by_user_and_org(
            user_id,
            organization_id,
        )
        if existing:
            return

        owner_role = await self._role_repo.get_by_slug("owner")
        if not owner_role:
            owner_role = Role.create_system(
                "Owner",
                "owner",
                "Full system access",
            )
            await self._role_repo.save(owner_role)
            await self._role_repo.set_permissions_for_role(
                owner_role.id,
                list(_OWNER_PERMISSIONS),
            )

        member = OrgMember.create(
            organization_id=organization_id,
            user_id=user_id,
            role_id=owner_role.id,
            is_default=True,
        )
        await self._org_member_repo.save(member)

    def _to_response(
        self,
        connection: SalesforceConnection,
    ) -> SalesforceConnectionResponse:
        return SalesforceConnectionResponse(
            id=connection.id,
            organization_id=connection.organization_id,
            environment=connection.environment.value,
            instance_url=connection.instance_url,
            org_id=connection.org_id,
            username=connection.username,
            api_version=connection.api_version,
            status=connection.status.value,
            is_active=connection.is_active,
            error_message=connection.error_message,
            last_successful_sync_at=connection.last_successful_sync_at,
            last_failed_sync_at=connection.last_failed_sync_at,
            created_at=connection.created_at,
        )
