import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.domain.entities.salesforce_connection import (
    SalesforceConnection,
)
from sfir_backend.domain.repositories.salesforce_repos import (
    ISalesforceConnectionRepository,
)
from sfir_backend.domain.value_objects.salesforce import (
    SalesforceConnectionStatus,
    SalesforceEnvironment,
)
from sfir_backend.infrastructure.persistence.models.salesforce_connection import (
    SalesforceConnectionModel,
)


class SalesforceConnectionRepository(ISalesforceConnectionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(
        self, connection_id: uuid.UUID,
    ) -> SalesforceConnection | None:
        result = await self._session.get(SalesforceConnectionModel, connection_id)
        return self._to_domain(result) if result else None

    async def get_by_org_and_user(
        self, org_id: uuid.UUID, user_id: uuid.UUID,
    ) -> SalesforceConnection | None:
        result = await self._session.execute(
            select(SalesforceConnectionModel)
            .where(SalesforceConnectionModel.organization_id == org_id)
            .where(SalesforceConnectionModel.user_id == user_id)
            .where(SalesforceConnectionModel.is_active.is_(True)),
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def list_by_organization(
        self, org_id: uuid.UUID,
    ) -> list[SalesforceConnection]:
        result = await self._session.execute(
            select(SalesforceConnectionModel)
            .where(SalesforceConnectionModel.organization_id == org_id),
        )
        return [self._to_domain(m) for m in result.scalars().all()]

    async def list_by_user(self, user_id: uuid.UUID) -> list[SalesforceConnection]:
        result = await self._session.execute(
            select(SalesforceConnectionModel)
            .where(SalesforceConnectionModel.user_id == user_id),
        )
        return [self._to_domain(m) for m in result.scalars().all()]

    async def list_active_by_organization(
        self, org_id: uuid.UUID,
    ) -> list[SalesforceConnection]:
        result = await self._session.execute(
            select(SalesforceConnectionModel)
            .where(SalesforceConnectionModel.organization_id == org_id)
            .where(SalesforceConnectionModel.is_active.is_(True)),
        )
        return [self._to_domain(m) for m in result.scalars().all()]

    async def save(self, connection: SalesforceConnection) -> SalesforceConnection:
        model = SalesforceConnectionModel(
            id=connection.id,
            organization_id=connection.organization_id,
            user_id=connection.user_id,
            environment=connection.environment.value,
            instance_url=connection.instance_url,
            org_id=connection.org_id,
            username=connection.username,
            api_version=connection.api_version,
            status=connection.status.value,
            access_token_encrypted=connection.access_token_encrypted,
            refresh_token_encrypted=connection.refresh_token_encrypted,
            token_expires_at=connection.token_expires_at,
            last_successful_sync_at=connection.last_successful_sync_at,
            last_failed_sync_at=connection.last_failed_sync_at,
            error_message=connection.error_message,
            is_active=connection.is_active,
            created_at=connection.created_at,
            updated_at=connection.updated_at,
        )
        self._session.add(model)
        await self._session.flush()
        return connection

    async def update(self, connection: SalesforceConnection) -> SalesforceConnection:
        model = await self._session.get(SalesforceConnectionModel, connection.id)
        if not model:
            raise ValueError(f"Connection {connection.id} not found")
        model.environment = connection.environment.value
        model.instance_url = connection.instance_url
        model.org_id = connection.org_id
        model.username = connection.username
        model.api_version = connection.api_version
        model.status = connection.status.value
        model.access_token_encrypted = connection.access_token_encrypted
        model.refresh_token_encrypted = connection.refresh_token_encrypted
        model.token_expires_at = connection.token_expires_at
        model.last_successful_sync_at = connection.last_successful_sync_at
        model.last_failed_sync_at = connection.last_failed_sync_at
        model.error_message = connection.error_message
        model.is_active = connection.is_active
        model.updated_at = connection.updated_at
        await self._session.flush()
        return connection

    async def delete(self, connection_id: uuid.UUID) -> None:
        await self._session.execute(
            update(SalesforceConnectionModel)
            .where(SalesforceConnectionModel.id == connection_id)
            .values(is_active=False),
        )
        await self._session.flush()

    def _to_domain(self, model: SalesforceConnectionModel) -> SalesforceConnection:
        return SalesforceConnection(
            id=model.id,
            organization_id=model.organization_id,
            user_id=model.user_id,
            environment=SalesforceEnvironment(model.environment),
            instance_url=model.instance_url,
            org_id=model.org_id,
            username=model.username,
            api_version=model.api_version,
            status=SalesforceConnectionStatus(model.status),
            access_token_encrypted=model.access_token_encrypted,
            refresh_token_encrypted=model.refresh_token_encrypted,
            token_expires_at=model.token_expires_at,
            last_successful_sync_at=model.last_successful_sync_at,
            last_failed_sync_at=model.last_failed_sync_at,
            error_message=model.error_message,
            is_active=model.is_active,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
