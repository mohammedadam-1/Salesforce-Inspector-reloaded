import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.domain.entities.org_member import OrgMember
from sfir_backend.domain.repositories.org_member_repo import IOrgMemberRepository
from sfir_backend.domain.value_objects.user_status import OrgMemberStatus
from sfir_backend.infrastructure.persistence.models.org_member import OrgMemberModel


class OrgMemberRepository(IOrgMemberRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, member_id: uuid.UUID) -> OrgMember | None:
        result = await self._session.get(OrgMemberModel, member_id)
        return self._to_domain(result) if result else None

    async def get_by_user_and_org(
        self, user_id: uuid.UUID, org_id: uuid.UUID,
    ) -> OrgMember | None:
        result = await self._session.execute(
            select(OrgMemberModel)
            .where(OrgMemberModel.user_id == user_id)
            .where(OrgMemberModel.organization_id == org_id)
            .where(OrgMemberModel.status == "active"),
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def list_by_user(self, user_id: uuid.UUID) -> list[OrgMember]:
        result = await self._session.execute(
            select(OrgMemberModel)
            .where(OrgMemberModel.user_id == user_id)
            .where(OrgMemberModel.status == "active"),
        )
        return [self._to_domain(m) for m in result.scalars().all()]

    async def list_by_org(self, org_id: uuid.UUID) -> list[OrgMember]:
        result = await self._session.execute(
            select(OrgMemberModel).where(OrgMemberModel.organization_id == org_id),
        )
        return [self._to_domain(m) for m in result.scalars().all()]

    async def save(self, member: OrgMember) -> OrgMember:
        model = OrgMemberModel(
            id=member.id,
            organization_id=member.organization_id,
            user_id=member.user_id,
            role_id=member.role_id,
            status=member.status.value,
            is_default=member.is_default,
            created_at=member.created_at,
            updated_at=member.updated_at,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.commit()
        return member

    async def update(self, member: OrgMember) -> OrgMember:
        model = await self._session.get(OrgMemberModel, member.id)
        if not model:
            raise ValueError(f"OrgMember {member.id} not found for update")
        model.role_id = member.role_id
        model.status = member.status.value
        model.is_default = member.is_default
        model.updated_at = member.updated_at
        await self._session.flush()
        await self._session.commit()
        return member

    async def set_default(self, user_id: uuid.UUID, org_id: uuid.UUID) -> None:
        await self._session.execute(
            update(OrgMemberModel)
            .where(OrgMemberModel.user_id == user_id)
            .values(is_default=False),
        )
        await self._session.execute(
            update(OrgMemberModel)
            .where(OrgMemberModel.user_id == user_id)
            .where(OrgMemberModel.organization_id == org_id)
            .values(is_default=True),
        )
        await self._session.flush()
        await self._session.commit()

    def _to_domain(self, model: OrgMemberModel) -> OrgMember:
        return OrgMember(
            id=model.id,
            organization_id=model.organization_id,
            user_id=model.user_id,
            role_id=model.role_id,
            status=OrgMemberStatus(model.status),
            is_default=model.is_default,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
