"""SQLAlchemy-backed search index repository.

The search index store persists one searchable document per graph node
identity per tenant. Rows are idempotently upserted (a row already
reflecting the document's state is skipped), only ever soft-deleted, and
versioned so reactivations are observable. Queries are exact, prefix, or
fuzzy (substring), always case-insensitive, namespace-aware, and ranked
by match quality, reference count, then relationship score.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.domain.entities.search_document import (
    SearchDocument,
    SearchUpsertResult,
)
from sfir_backend.domain.repositories.search_index_repo import (
    ISearchIndexRepository,
)
from sfir_backend.infrastructure.persistence.models.search_document import (
    SearchIndexDocumentModel,
)

_MAX_LIMIT = 200
_FIELD_COLUMN = {
    "api_name": SearchIndexDocumentModel.api_name,
    "developer_name": SearchIndexDocumentModel.developer_name,
    "display_name": SearchIndexDocumentModel.display_name,
    "namespace": SearchIndexDocumentModel.namespace,
    "metadata_type": SearchIndexDocumentModel.metadata_type,
    "object": SearchIndexDocumentModel.object_api_name,
    "content": SearchIndexDocumentModel.content,
}


def _to_entity(model: SearchIndexDocumentModel) -> SearchDocument:
    return SearchDocument(
        id=model.id,
        organization_id=model.organization_id,
        identity=model.identity,
        metadata_type=model.metadata_type,
        api_name=model.api_name,
        developer_name=model.developer_name,
        display_name=model.display_name,
        namespace=model.namespace,
        content=model.content,
        object_api_name=model.object_api_name,
        parent_identities=list(model.parent_identities or []),
        child_identities=list(model.child_identities or []),
        reference_identities=list(model.reference_identities or []),
        relationship_types=list(model.relationship_types or []),
        reference_count=model.reference_count,
        relationship_score=model.relationship_score,
        version=model.version,
        previous_version=model.previous_version,
        created_at=model.created_at,
        updated_at=model.updated_at,
        deleted_at=model.deleted_at,
        last_sync_job_id=model.last_sync_job_id,
    )


def _row_matches(row: SearchIndexDocumentModel, doc: SearchDocument) -> bool:
    return (
        row.metadata_type == doc.metadata_type
        and row.api_name == doc.api_name
        and row.developer_name == doc.developer_name
        and row.display_name == doc.display_name
        and row.namespace == doc.namespace
        and row.content == doc.content
        and row.object_api_name == doc.object_api_name
        and list(row.parent_identities or []) == doc.parent_identities
        and list(row.child_identities or []) == doc.child_identities
        and list(row.reference_identities or []) == doc.reference_identities
        and list(row.relationship_types or []) == doc.relationship_types
        and row.reference_count == doc.reference_count
        and row.relationship_score == doc.relationship_score
        and not row.deleted
    )


class SQLAlchemySearchIndexRepository(ISearchIndexRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_batch(
        self,
        organization_id: uuid.UUID,
        documents: list[SearchDocument],
    ) -> SearchUpsertResult:
        if not documents:
            return SearchUpsertResult()

        existing = await self._session.execute(
            select(SearchIndexDocumentModel).where(
                SearchIndexDocumentModel.organization_id == organization_id,
                SearchIndexDocumentModel.identity.in_(
                    [d.identity for d in documents],
                ),
            ),
        )
        current = {row.identity: row for row in existing.scalars()}

        result = SearchUpsertResult()
        for doc in documents:
            row = current.get(doc.identity)
            if row is None:
                if doc.is_deleted:
                    result.soft_deleted += 1
                else:
                    result.created += 1
                self._session.add(
                    SearchIndexDocumentModel(
                        id=doc.id,
                        organization_id=organization_id,
                        identity=doc.identity,
                        metadata_type=doc.metadata_type,
                        api_name=doc.api_name,
                        developer_name=doc.developer_name,
                        display_name=doc.display_name,
                        namespace=doc.namespace,
                        content=doc.content,
                        object_api_name=doc.object_api_name,
                        parent_identities=doc.parent_identities,
                        child_identities=doc.child_identities,
                        reference_identities=doc.reference_identities,
                        relationship_types=doc.relationship_types,
                        reference_count=doc.reference_count,
                        relationship_score=doc.relationship_score,
                        version=doc.version,
                        previous_version=doc.previous_version,
                        deleted=doc.is_deleted,
                        created_at=doc.created_at,
                        updated_at=doc.updated_at,
                        deleted_at=doc.deleted_at,
                        last_sync_job_id=doc.last_sync_job_id,
                    ),
                )
            elif doc.is_deleted:
                if row.deleted:
                    result.skipped += 1
                else:
                    result.soft_deleted += 1
                    row.deleted = True
                    row.deleted_at = doc.deleted_at or datetime.now(UTC)
                    row.updated_at = datetime.now(UTC)
                    if doc.last_sync_job_id is not None:
                        row.last_sync_job_id = doc.last_sync_job_id
            elif _row_matches(row, doc):
                result.skipped += 1
            else:
                result.updated += 1
                if row.deleted:
                    row.previous_version = row.version
                    row.version = row.version + 1
                row.deleted = False
                row.deleted_at = None
                row.metadata_type = doc.metadata_type
                row.api_name = doc.api_name
                row.developer_name = doc.developer_name
                row.display_name = doc.display_name
                row.namespace = doc.namespace
                row.content = doc.content
                row.object_api_name = doc.object_api_name
                row.parent_identities = doc.parent_identities
                row.child_identities = doc.child_identities
                row.reference_identities = doc.reference_identities
                row.relationship_types = doc.relationship_types
                row.reference_count = doc.reference_count
                row.relationship_score = doc.relationship_score
                row.updated_at = datetime.now(UTC)
                if doc.last_sync_job_id is not None:
                    row.last_sync_job_id = doc.last_sync_job_id
        try:
            await self._session.flush()
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            return await self.upsert_batch(organization_id, documents)
        return result

    async def soft_delete_by_identities(
        self,
        organization_id: uuid.UUID,
        identities: set[str],
        *,
        sync_job_id: uuid.UUID | None = None,
    ) -> int:
        if not identities:
            return 0
        result = await self._session.execute(
            select(SearchIndexDocumentModel).where(
                SearchIndexDocumentModel.organization_id == organization_id,
                SearchIndexDocumentModel.identity.in_(identities),
                SearchIndexDocumentModel.deleted.is_(False),
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

    async def search(
        self,
        organization_id: uuid.UUID,
        query: str,
        *,
        mode: str = "fuzzy",
        fields: set[str] | None = None,
        metadata_type: str | None = None,
        namespace: str | None = None,
        relationship_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[SearchDocument]:
        query = query.strip()
        if not query:
            return []
        limit = min(max(limit, 1), _MAX_LIMIT)
        mode = mode if mode in ("exact", "prefix", "fuzzy") else "fuzzy"
        selected = (
            fields if fields else set(_FIELD_COLUMN)
        ) & set(_FIELD_COLUMN)
        if not selected:
            selected = set(_FIELD_COLUMN)

        q = query.lower()
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        match_conditions = []
        for field_name in selected:
            column = _FIELD_COLUMN[field_name]
            if mode == "exact":
                match_conditions.append(func.lower(column) == q)
            elif mode == "prefix":
                match_conditions.append(
                    func.lower(column).like(escaped + "%", escape="\\"),
                )
            else:
                match_conditions.append(
                    func.lower(column).like("%" + escaped + "%", escape="\\"),
                )

        conditions = [
            SearchIndexDocumentModel.organization_id == organization_id,
            SearchIndexDocumentModel.deleted.is_(False),
            or_(*match_conditions),
        ]
        if metadata_type is not None:
            conditions.append(SearchIndexDocumentModel.metadata_type == metadata_type)
        if namespace is not None:
            conditions.append(SearchIndexDocumentModel.namespace == namespace)
        if relationship_type is not None:
            conditions.append(
                SearchIndexDocumentModel.relationship_types.contains(
                    [relationship_type],
                ),
            )

        rank = case(
            (func.lower(SearchIndexDocumentModel.api_name) == q, 0),
            (func.lower(SearchIndexDocumentModel.developer_name) == q, 1),
            (func.lower(SearchIndexDocumentModel.display_name) == q, 2),
            else_=3,
        )
        result = await self._session.execute(
            select(SearchIndexDocumentModel)
            .where(*conditions)
            .order_by(
                rank,
                SearchIndexDocumentModel.reference_count.desc(),
                SearchIndexDocumentModel.relationship_score.desc(),
                SearchIndexDocumentModel.api_name,
            )
            .limit(limit)
            .offset(offset),
        )
        return [_to_entity(row) for row in result.scalars()]

    async def get_by_identity(
        self,
        organization_id: uuid.UUID,
        identity: str,
    ) -> SearchDocument | None:
        result = await self._session.execute(
            select(SearchIndexDocumentModel).where(
                SearchIndexDocumentModel.organization_id == organization_id,
                SearchIndexDocumentModel.identity == identity,
            ),
        )
        row = result.scalar_one_or_none()
        return _to_entity(row) if row else None

    async def list_active(
        self,
        organization_id: uuid.UUID,
        *,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[SearchDocument]:
        result = await self._session.execute(
            select(SearchIndexDocumentModel)
            .where(
                SearchIndexDocumentModel.organization_id == organization_id,
                SearchIndexDocumentModel.deleted.is_(False),
            )
            .order_by(SearchIndexDocumentModel.api_name)
            .limit(limit)
            .offset(offset),
        )
        return [_to_entity(row) for row in result.scalars()]

    async def count_by_organization(
        self,
        organization_id: uuid.UUID,
    ) -> int:
        result = await self._session.execute(
            select(func.count(SearchIndexDocumentModel.id)).where(
                SearchIndexDocumentModel.organization_id == organization_id,
            ),
        )
        return int(result.scalar_one())
