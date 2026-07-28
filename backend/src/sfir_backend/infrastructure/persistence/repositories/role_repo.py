import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.domain.entities.role import Role
from sfir_backend.domain.repositories.role_repo import IRoleRepository
from sfir_backend.infrastructure.persistence.models.permission import PermissionModel
from sfir_backend.infrastructure.persistence.models.role import RoleModel


class RoleRepository(IRoleRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, role_id: uuid.UUID) -> Role | None:
        result = await self._session.get(RoleModel, role_id)
        return self._to_domain(result) if result else None

    async def get_by_slug(self, slug: str) -> Role | None:
        result = await self._session.execute(
            select(RoleModel).where(RoleModel.slug == slug),
        )
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def list_system_roles(self) -> list[Role]:
        result = await self._session.execute(
            select(RoleModel).where(RoleModel.is_system.is_(True)),
        )
        return [self._to_domain(m) for m in result.scalars().all()]

    async def list_by_org(self, org_id: uuid.UUID) -> list[Role]:
        result = await self._session.execute(
            select(RoleModel)
            .where(
                (RoleModel.organization_id == org_id)
                | (RoleModel.is_system.is_(True)),
            )
        )
        return [self._to_domain(m) for m in result.scalars().all()]

    async def save(self, role: Role) -> Role:
        model = RoleModel(
            id=role.id,
            name=role.name,
            slug=role.slug,
            description=role.description,
            is_system=role.is_system,
            organization_id=role.organization_id,
            created_at=role.created_at,
            updated_at=role.updated_at,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.commit()
        return role

    async def get_permissions_for_role(self, role_id: uuid.UUID) -> set[str]:
        result = await self._session.execute(
            select(PermissionModel.permission_slug)
            .where(PermissionModel.role_id == role_id),
        )
        return set(result.scalars().all())

    async def set_permissions_for_role(
        self, role_id: uuid.UUID, permissions: list[str],
    ) -> None:
        await self._session.execute(
            delete(PermissionModel).where(PermissionModel.role_id == role_id),
        )
        if permissions:
            models = [
                PermissionModel(
                    id=uuid.uuid4(),
                    role_id=role_id,
                    permission_slug=slug,
                )
                for slug in permissions
            ]
            self._session.add_all(models)
        await self._session.flush()
        await self._session.commit()

    def _to_domain(self, model: RoleModel) -> Role:
        return Role(
            id=model.id,
            name=model.name,
            slug=model.slug,
            description=model.description,
            is_system=model.is_system,
            organization_id=model.organization_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
