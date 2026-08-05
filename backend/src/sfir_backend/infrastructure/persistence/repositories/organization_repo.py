import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.domain.entities.organization import Organization
from sfir_backend.domain.repositories.organization_repo import IOrganizationRepository
from sfir_backend.domain.value_objects.user_status import OrganizationStatus
from sfir_backend.infrastructure.persistence.models.organization import OrganizationModel


class OrganizationRepository(IOrganizationRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, org_id: uuid.UUID) -> Organization | None:
        result = await self._session.get(OrganizationModel, org_id)
        return self._to_domain(result) if result else None

    async def get_by_slug(self, slug: str) -> Organization | None:
        result = await self._session.execute(
            select(OrganizationModel).where(OrganizationModel.slug == slug),
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def get_by_salesforce_org_id(
        self,
        salesforce_org_id: str,
    ) -> Organization | None:
        result = await self._session.execute(
            select(OrganizationModel).where(
                OrganizationModel.salesforce_org_id == salesforce_org_id,
            ),
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def list_by_user(self, user_id: uuid.UUID) -> list[Organization]:
        from sfir_backend.infrastructure.persistence.models.org_member import (
            OrgMemberModel,
        )

        result = await self._session.execute(
            select(OrganizationModel)
            .join(OrgMemberModel)
            .where(OrgMemberModel.user_id == user_id)
            .where(OrgMemberModel.status == "active"),
        )
        return [self._to_domain(m) for m in result.scalars().all()]

    async def save(self, org: Organization) -> Organization:
        model = OrganizationModel(
            id=org.id,
            name=org.name,
            slug=org.slug,
            description=org.description,
            owner_id=org.owner_id,
            status=org.status.value,
            settings=org.settings,
            salesforce_org_id=org.salesforce_org_id,
            salesforce_org_name=org.salesforce_org_name,
            instance_url=org.instance_url,
            organization_type=org.organization_type,
            created_at=org.created_at,
            updated_at=org.updated_at,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.commit()
        return org

    async def update(self, org: Organization) -> Organization:
        model = await self._session.get(OrganizationModel, org.id)
        if not model:
            raise ValueError(f"Organization {org.id} not found for update")
        model.name = org.name
        model.slug = org.slug
        model.description = org.description
        model.status = org.status.value
        model.settings = org.settings
        model.salesforce_org_id = org.salesforce_org_id
        model.salesforce_org_name = org.salesforce_org_name
        model.instance_url = org.instance_url
        model.organization_type = org.organization_type
        model.updated_at = org.updated_at
        await self._session.flush()
        await self._session.commit()
        return org

    async def delete(self, org_id: uuid.UUID) -> None:
        model = await self._session.get(OrganizationModel, org_id)
        if model:
            await self._session.delete(model)
            await self._session.flush()
            await self._session.commit()

    async def slug_exists(self, slug: str) -> bool:
        result = await self._session.execute(
            select(OrganizationModel.id).where(OrganizationModel.slug == slug).limit(1),
        )
        return result.scalar_one_or_none() is not None

    def _to_domain(self, model: OrganizationModel) -> Organization:
        return Organization(
            id=model.id,
            name=model.name,
            slug=model.slug,
            description=model.description,
            owner_id=model.owner_id,
            status=OrganizationStatus(model.status),
            settings=model.settings if model.settings is not None else {},
            salesforce_org_id=model.salesforce_org_id,
            salesforce_org_name=model.salesforce_org_name,
            instance_url=model.instance_url,
            organization_type=model.organization_type,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
