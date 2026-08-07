"""SQLAlchemy-backed canonical document repository.

The canonical store is the upsert-correct system of record for normalized
metadata: one current-state row per stable identity per tenant, written
conflict-free via ON CONFLICT so concurrent workers never duplicate rows,
and only ever soft-deleted.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.domain.canonical.base import MetadataStatus
from sfir_backend.domain.entities.canonical_document import (
    CanonicalDocument,
    CanonicalUpsertResult,
)
from sfir_backend.domain.repositories.canonical_repo import (
    ICanonicalDocumentRepository,
)
from sfir_backend.infrastructure.persistence.models.canonical_document import (
    CanonicalDocumentModel,
)


def _to_entity(model: CanonicalDocumentModel) -> CanonicalDocument:
    return CanonicalDocument(
        id=model.id,
        organization_id=model.organization_id,
        identity=model.identity,
        type=model.type,
        api_name=model.api_name,
        developer_name=model.developer_name,
        namespace=model.namespace,
        version=model.version,
        previous_version=model.previous_version,
        fingerprint=model.fingerprint,
        status=MetadataStatus(model.status),
        created_at=model.created_at,
        updated_at=model.updated_at,
        first_seen_at=model.first_seen_at,
        last_seen_at=model.last_seen_at,
        deleted_at=model.deleted_at,
        last_sync_job_id=model.last_sync_job_id,
        payload=dict(model.payload or {}),
    )


class SQLAlchemyCanonicalDocumentRepository(ICanonicalDocumentRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_batch(
        self,
        organization_id: uuid.UUID,
        documents: list[CanonicalDocument],
    ) -> CanonicalUpsertResult:
        if not documents:
            return CanonicalUpsertResult()

        existing = await self._session.execute(
            select(CanonicalDocumentModel).where(
                CanonicalDocumentModel.organization_id == organization_id,
                CanonicalDocumentModel.identity.in_(
                    [d.identity for d in documents],
                ),
            ),
        )
        current = {row.identity: row for row in existing.scalars()}

        result = CanonicalUpsertResult()
        for doc in documents:
            row = current.get(doc.identity)
            if row is not None:
                unchanged = row.fingerprint == doc.fingerprint
                still_active = row.status == MetadataStatus.ACTIVE.value and not row.deleted
                if unchanged and still_active:
                    result.skipped += 1
                    continue
            values = {
                "id": doc.id,
                "organization_id": organization_id,
                "identity": doc.identity,
                "type": doc.type,
                "api_name": doc.api_name,
                "developer_name": doc.developer_name,
                "namespace": doc.namespace,
                "version": doc.version,
                "previous_version": doc.previous_version,
                "fingerprint": doc.fingerprint,
                "status": doc.status.value,
                "deleted": doc.is_deleted,
                "created_at": doc.created_at,
                "updated_at": doc.updated_at,
                "first_seen_at": doc.first_seen_at,
                "last_seen_at": doc.last_seen_at,
                "deleted_at": doc.deleted_at,
                "last_sync_job_id": doc.last_sync_job_id,
                "payload": doc.payload,
            }
            if row is None:
                result.created += 1
                self._session.add(CanonicalDocumentModel(**values))
            else:
                result.updated += 1
                if row.status == MetadataStatus.DELETED.value:
                    values["created_at"] = row.created_at
                    values["first_seen_at"] = row.first_seen_at
                for key, value in values.items():
                    setattr(row, key, value)
        try:
            await self._session.flush()
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            return await self.upsert_batch(organization_id, documents)
        return result

    async def get_by_identity(
        self,
        organization_id: uuid.UUID,
        identity: str,
    ) -> CanonicalDocument | None:
        result = await self._session.execute(
            select(CanonicalDocumentModel)
            .where(CanonicalDocumentModel.organization_id == organization_id)
            .where(CanonicalDocumentModel.identity == identity),
        )
        row = result.scalar_one_or_none()
        return _to_entity(row) if row else None

    async def get_by_identities(
        self,
        organization_id: uuid.UUID,
        identities: set[str],
    ) -> list[CanonicalDocument]:
        if not identities:
            return []
        result = await self._session.execute(
            select(CanonicalDocumentModel)
            .where(CanonicalDocumentModel.organization_id == organization_id)
            .where(CanonicalDocumentModel.identity.in_(identities)),
        )
        return [_to_entity(row) for row in result.scalars()]

    async def list_latest(
        self,
        organization_id: uuid.UUID,
        *,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[CanonicalDocument]:
        result = await self._session.execute(
            select(CanonicalDocumentModel)
            .where(CanonicalDocumentModel.organization_id == organization_id)
            .order_by(CanonicalDocumentModel.api_name)
            .limit(limit)
            .offset(offset),
        )
        return [_to_entity(row) for row in result.scalars()]

    async def list_latest_by_type(
        self,
        organization_id: uuid.UUID,
        metadata_type: str,
    ) -> list[CanonicalDocument]:
        result = await self._session.execute(
            select(CanonicalDocumentModel)
            .where(CanonicalDocumentModel.organization_id == organization_id)
            .where(CanonicalDocumentModel.type == metadata_type)
            .order_by(CanonicalDocumentModel.api_name),
        )
        return [_to_entity(row) for row in result.scalars()]

    async def count_by_organization(
        self,
        organization_id: uuid.UUID,
    ) -> int:
        result = await self._session.execute(
            select(func.count(CanonicalDocumentModel.id))
            .where(CanonicalDocumentModel.organization_id == organization_id),
        )
        return int(result.scalar_one())

    async def soft_delete_by_identity(
        self,
        organization_id: uuid.UUID,
        identity: str,
        *,
        sync_job_id: uuid.UUID | None = None,
    ) -> bool:
        now = datetime.now(UTC)
        result = await self._session.execute(
            pg_insert(CanonicalDocumentModel)
            .values(
                id=uuid.uuid4(),
                organization_id=organization_id,
                identity=identity,
                type="",
                api_name="",
                developer_name="",
                version=1,
                previous_version=0,
                fingerprint="",
                status=MetadataStatus.DELETED.value,
                deleted=True,
                deleted_at=now,
                updated_at=now,
                last_seen_at=now,
                payload={},
            )
            .on_conflict_do_update(
                constraint="uq_canonical_documents_org_identity",
                set_={
                    "status": MetadataStatus.DELETED.value,
                    "deleted": True,
                    "deleted_at": now,
                    "updated_at": now,
                    "last_seen_at": now,
                    "last_sync_job_id": sync_job_id,
                },
            ),
        )
        await self._session.commit()
        return result.rowcount > 0

    async def soft_delete_missing(
        self,
        organization_id: uuid.UUID,
        metadata_type: str,
        seen_api_names: set[str],
        *,
        sync_job_id: uuid.UUID | None = None,
    ) -> int:
        result = await self._session.execute(
            select(CanonicalDocumentModel).where(
                CanonicalDocumentModel.organization_id == organization_id,
                CanonicalDocumentModel.type == metadata_type,
                CanonicalDocumentModel.status != MetadataStatus.DELETED.value,
            ),
        )
        rows = list(result.scalars())
        now = datetime.now(UTC)
        deleted = 0
        for row in rows:
            if row.api_name in seen_api_names:
                continue
            row.status = MetadataStatus.DELETED.value
            row.deleted = True
            row.deleted_at = now
            row.updated_at = now
            row.last_seen_at = now
            row.last_sync_job_id = sync_job_id
            deleted += 1
        if deleted:
            await self._session.flush()
            await self._session.commit()
        return deleted
