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
from sfir_backend.domain.entities.audit_log import AuditLogEntry
from sfir_backend.domain.entities.salesforce_connection import (
    SalesforceConnection,
)
from sfir_backend.domain.repositories.audit_log_repo import IAuditLogRepository
from sfir_backend.domain.repositories.organization_repo import (
    IOrganizationRepository,
)
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
from sfir_backend.shared.exceptions.application import ConflictError
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
    ) -> None:
        self._connection_repo = connection_repo
        self._org_repo = org_repo
        self._audit_log_repo = audit_log_repo
        self._oauth_service = oauth_service
        self._encryption_service = encryption_service
        self._sync_coordinator = sync_coordinator

    async def initiate_connect(
        self,
        request: SalesforceConnectRequest,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> SalesforceConnectResponse:
        environment = self._oauth_service.validate_environment(request.environment)

        existing = await self._connection_repo.get_by_org_and_user(
            organization_id, user_id,
        )
        if existing and existing.is_active:
            raise ConflictError(
                "An active Salesforce connection already exists for this org",
            )

        state = self._oauth_service.generate_state()
        pkce = self._oauth_service.generate_pkce_pair()

        auth_url = self._oauth_service.build_authorization_url(
            environment=environment,
            state=state,
            code_challenge=pkce["code_challenge"],
        )

        return SalesforceConnectResponse(
            authorization_url=auth_url,
            state=state,
            code_verifier=pkce["code_verifier"],
            environment=request.environment,
        )

    async def handle_callback(
        self,
        request: SalesforceCallbackRequest,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        ip_address: str = "",
    ) -> SalesforceConnectionResponse:
        environment = self._oauth_service.validate_environment(request.environment)

        token_response = await self._oauth_service.exchange_code_for_tokens(
            code=request.code,
            code_verifier=request.code_verifier,
            environment=environment,
        )

        access_token = token_response.get("access_token", "")
        refresh_token = token_response.get("refresh_token", "")
        instance_url = token_response.get("instance_url", "")
        id_parts = token_response.get("id", "").split("/")
        sf_org_id = id_parts[-2] if len(id_parts) >= 2 else ""
        username = token_response.get("username", "")

        if not access_token or not instance_url:
            raise ValueError("Invalid token response from Salesforce")

        access_encrypted = self._encryption_service.encrypt(access_token)
        refresh_encrypted = (
            self._encryption_service.encrypt(refresh_token) if refresh_token else ""
        )

        existing = await self._connection_repo.get_by_org_and_user(
            organization_id, user_id,
        )

        if existing:
            connection = existing
            connection.mark_connected(
                access_token_encrypted=access_encrypted,
                refresh_token_encrypted=refresh_encrypted,
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
            )
            await self._connection_repo.save(connection)

        await self._audit_log_repo.save(AuditLogEntry.create(
            action="salesforce.connected",
            resource_type="salesforce_connection",
            resource_id=str(connection.id),
            user_id=user_id,
            organization_id=organization_id,
            details={"environment": request.environment, "org_id": sf_org_id},
            ip_address=ip_address,
        ))

        logger.info(
            "salesforce_connection_established",
            connection_id=str(connection.id),
            org_id=sf_org_id,
            environment=request.environment,
        )

        if self._sync_coordinator:
            try:
                sync_req = StartSyncRequest(
                    connection_id=connection.id, sync_type="full",
                )
                await self._sync_coordinator.start_sync(
                    sync_req, organization_id, user_id,
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
            organization_id, user_id,
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
                    decrypted_refresh, environment=environment,
                )
            except Exception:
                logger.warning(
                    "salesforce_token_revoke_failed",
                    connection_id=str(connection.id),
                )

        await self._audit_log_repo.save(AuditLogEntry.create(
            action="salesforce.disconnected",
            resource_type="salesforce_connection",
            resource_id=str(connection.id),
            user_id=user_id,
            organization_id=organization_id,
            ip_address=ip_address,
        ))

    async def get_status(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> SalesforceConnectionResponse | None:
        connection = await self._connection_repo.get_by_org_and_user(
            organization_id, user_id,
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
            organization_id, user_id,
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

    def _to_response(
        self, connection: SalesforceConnection,
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
