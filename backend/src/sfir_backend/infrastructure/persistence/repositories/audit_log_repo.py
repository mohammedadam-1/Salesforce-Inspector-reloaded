import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.domain.entities.audit_log import AuditLogEntry
from sfir_backend.domain.repositories.audit_log_repo import IAuditLogRepository
from sfir_backend.infrastructure.persistence.models.audit_log import AuditLogModel


class AuditLogRepository(IAuditLogRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, entry: AuditLogEntry) -> AuditLogEntry:
        model = AuditLogModel(
            id=entry.id,
            user_id=entry.user_id,
            organization_id=entry.organization_id,
            action=entry.action,
            resource_type=entry.resource_type,
            resource_id=entry.resource_id,
            details=entry.details,
            ip_address=entry.ip_address,
            created_at=entry.created_at,
        )
        self._session.add(model)
        await self._session.flush()
        await self._session.commit()
        return entry

    async def list_by_org(
        self,
        org_id: uuid.UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLogEntry]:
        result = await self._session.execute(
            select(AuditLogModel)
            .where(AuditLogModel.organization_id == org_id)
            .order_by(AuditLogModel.created_at.desc())
            .limit(limit)
            .offset(offset),
        )
        return [self._to_domain(m) for m in result.scalars().all()]

    async def list_by_user(
        self,
        user_id: uuid.UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLogEntry]:
        result = await self._session.execute(
            select(AuditLogModel)
            .where(AuditLogModel.user_id == user_id)
            .order_by(AuditLogModel.created_at.desc())
            .limit(limit)
            .offset(offset),
        )
        return [self._to_domain(m) for m in result.scalars().all()]

    async def count_by_org(
        self,
        org_id: uuid.UUID,
        since: datetime | None = None,
    ) -> int:
        query = select(func.count()).select_from(AuditLogModel).where(
            AuditLogModel.organization_id == org_id,
        )
        if since:
            query = query.where(AuditLogModel.created_at >= since)
        result = await self._session.execute(query)
        return result.scalar() or 0

    def _to_domain(self, model: AuditLogModel) -> AuditLogEntry:
        return AuditLogEntry(
            id=model.id,
            user_id=model.user_id,
            organization_id=model.organization_id,
            action=model.action,
            resource_type=model.resource_type,
            resource_id=model.resource_id,
            details=model.details,
            ip_address=model.ip_address,
            created_at=model.created_at,
        )
