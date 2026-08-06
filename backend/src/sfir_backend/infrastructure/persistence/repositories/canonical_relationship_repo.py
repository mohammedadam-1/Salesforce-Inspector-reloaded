"""SQLAlchemy-backed canonical relationship repository.

The canonical relationship store is the upsert-correct system of record for
typed, directional edges between canonical metadata documents: one row per
(tenant, source identity, target identity, relationship type), written
conflict-free so concurrent workers never duplicate rows, and only ever
soft-deleted.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.domain.entities.canonical_relationship import (
    CanonicalRelationship,
    CanonicalRelationshipType,
    CanonicalRelationshipUpsertResult,
)
from sfir_backend.domain.repositories.canonical_relationship_repo import (
    ICanonicalRelationshipRepository,
)
from sfir_backend.infrastructure.persistence.models.canonical_relationship import (
    CanonicalRelationshipModel,
)


def _to_entity(model: CanonicalRelationshipModel) -> CanonicalRelationship:
    return CanonicalRelationship(
        id=model.id,
        organization_id=model.organization_id,
        source_identity=model.source_identity,
        source_api_name=model.source_api_name,
        source_type=model.source_type,
        target_identity=model.target_identity,
        target_api_name=model.target_api_name,
        target_type=model.target_type,
        relationship_type=CanonicalRelationshipType(model.relationship_type),
        version=model.version,
        previous_version=model.previous_version,
        created_at=model.created_at,
        updated_at=model.updated_at,
        deleted_at=model.deleted_at,
        last_sync_job_id=model.last_sync_job_id,
    )


class SQLAlchemyCanonicalRelationshipRepository(ICanonicalRelationshipRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_batch(
        self,
        organization_id: uuid.UUID,
        relationships: list[CanonicalRelationship],
    ) -> CanonicalRelationshipUpsertResult:
        if not relationships:
            return CanonicalRelationshipUpsertResult()

        existing = await self._session.execute(
            select(CanonicalRelationshipModel).where(
                CanonicalRelationshipModel.organization_id == organization_id,
                CanonicalRelationshipModel.source_identity.in_(
                    {r.source_identity for r in relationships},
                ),
                CanonicalRelationshipModel.target_identity.in_(
                    {r.target_identity for r in relationships},
                ),
            ),
        )
        current = {
            (
                row.source_identity,
                row.target_identity,
                row.relationship_type,
            ): row
            for row in existing.scalars()
        }

        result = CanonicalRelationshipUpsertResult()
        for rel in relationships:
            key = (rel.source_identity, rel.target_identity, rel.relationship_type.value)
            row = current.get(key)
            if row is not None and not row.deleted and not rel.is_deleted:
                result.skipped += 1
                continue
            if row is None:
                if rel.is_deleted:
                    result.soft_deleted += 1
                else:
                    result.created += 1
                self._session.add(
                    CanonicalRelationshipModel(
                        id=rel.id,
                        organization_id=organization_id,
                        source_identity=rel.source_identity,
                        source_api_name=rel.source_api_name,
                        source_type=rel.source_type,
                        target_identity=rel.target_identity,
                        target_api_name=rel.target_api_name,
                        target_type=rel.target_type,
                        relationship_type=rel.relationship_type.value,
                        version=rel.version,
                        previous_version=rel.previous_version,
                        deleted=rel.is_deleted,
                        created_at=rel.created_at,
                        updated_at=rel.updated_at,
                        deleted_at=rel.deleted_at,
                        last_sync_job_id=rel.last_sync_job_id,
                    ),
                )
            elif rel.is_deleted:
                result.soft_deleted += 1
                row.deleted = True
                row.deleted_at = rel.deleted_at or datetime.now(UTC)
                row.updated_at = datetime.now(UTC)
                if rel.last_sync_job_id is not None:
                    row.last_sync_job_id = rel.last_sync_job_id
            else:
                result.updated += 1
                row.deleted = False
                row.deleted_at = None
                row.version = row.version + 1
                row.previous_version = row.version - 1
                row.updated_at = datetime.now(UTC)
                if rel.last_sync_job_id is not None:
                    row.last_sync_job_id = rel.last_sync_job_id
        try:
            await self._session.flush()
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            return await self.upsert_batch(organization_id, relationships)
        return result

    async def soft_delete_missing_for_source(
        self,
        organization_id: uuid.UUID,
        source_identity: str,
        seen_edges: set[tuple[str, str]],
        *,
        sync_job_id: uuid.UUID | None = None,
    ) -> int:
        result = await self._session.execute(
            select(CanonicalRelationshipModel).where(
                CanonicalRelationshipModel.organization_id == organization_id,
                CanonicalRelationshipModel.source_identity == source_identity,
                CanonicalRelationshipModel.deleted.is_(False),
            ),
        )
        now = datetime.now(UTC)
        deleted = 0
        for row in result.scalars():
            edge = (row.target_identity, row.relationship_type)
            if edge in seen_edges:
                continue
            row.deleted = True
            row.deleted_at = now
            row.updated_at = now
            if sync_job_id is not None:
                row.last_sync_job_id = sync_job_id
            deleted += 1
        if deleted:
            await self._session.flush()
            await self._session.commit()
        return deleted

    async def soft_delete_by_source_identities(
        self,
        organization_id: uuid.UUID,
        source_identities: set[str],
        *,
        sync_job_id: uuid.UUID | None = None,
    ) -> int:
        if not source_identities:
            return 0
        result = await self._session.execute(
            select(CanonicalRelationshipModel).where(
                CanonicalRelationshipModel.organization_id == organization_id,
                CanonicalRelationshipModel.source_identity.in_(source_identities),
                CanonicalRelationshipModel.deleted.is_(False),
            ),
        )
        now = datetime.now(UTC)
        deleted = 0
        for row in result.scalars():
            row.deleted = True
            row.deleted_at = now
            row.updated_at = now
            if sync_job_id is not None:
                row.last_sync_job_id = sync_job_id
            deleted += 1
        if deleted:
            await self._session.flush()
            await self._session.commit()
        return deleted

    async def list_by_source(
        self,
        organization_id: uuid.UUID,
        source_identity: str,
    ) -> list[CanonicalRelationship]:
        result = await self._session.execute(
            select(CanonicalRelationshipModel)
            .where(CanonicalRelationshipModel.organization_id == organization_id)
            .where(CanonicalRelationshipModel.source_identity == source_identity)
            .order_by(CanonicalRelationshipModel.target_api_name),
        )
        return [_to_entity(row) for row in result.scalars()]

    async def list_active(
        self,
        organization_id: uuid.UUID,
        *,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[CanonicalRelationship]:
        result = await self._session.execute(
            select(CanonicalRelationshipModel)
            .where(CanonicalRelationshipModel.organization_id == organization_id)
            .where(CanonicalRelationshipModel.deleted.is_(False))
            .order_by(CanonicalRelationshipModel.source_api_name)
            .limit(limit)
            .offset(offset),
        )
        return [_to_entity(row) for row in result.scalars()]

    async def count_by_organization(
        self,
        organization_id: uuid.UUID,
    ) -> int:
        result = await self._session.execute(
            select(func.count(CanonicalRelationshipModel.id))
            .where(CanonicalRelationshipModel.organization_id == organization_id),
        )
        return int(result.scalar_one())
