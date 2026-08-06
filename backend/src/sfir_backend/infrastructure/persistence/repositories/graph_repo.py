"""SQLAlchemy-backed dependency graph repository.

The graph store persists nodes and edges derived from the canonical store:
one node per (tenant, identity), one edge per (tenant, source identity,
target identity, relationship type). Rows are idempotently upserted (a row
already matching the source document/relationship state is skipped), never
physically deleted, and versioned so reactivations are observable.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.domain.entities.canonical_relationship import (
    CanonicalRelationshipType,
)
from sfir_backend.domain.entities.graph_edge import GraphEdge
from sfir_backend.domain.entities.graph_node import GraphNode, GraphUpsertResult
from sfir_backend.domain.repositories.graph_repo import IGraphRepository
from sfir_backend.infrastructure.persistence.models.graph_edge import GraphEdgeModel
from sfir_backend.infrastructure.persistence.models.graph_node import GraphNodeModel


def _node_to_entity(model: GraphNodeModel) -> GraphNode:
    return GraphNode(
        id=model.id,
        organization_id=model.organization_id,
        identity=model.identity,
        type=model.type,
        api_name=model.api_name,
        namespace=model.namespace,
        document_version=model.document_version,
        document_fingerprint=model.document_fingerprint,
        version=model.version,
        previous_version=model.previous_version,
        created_at=model.created_at,
        updated_at=model.updated_at,
        deleted_at=model.deleted_at,
        last_sync_job_id=model.last_sync_job_id,
    )


def _edge_to_entity(model: GraphEdgeModel) -> GraphEdge:
    return GraphEdge(
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


class SQLAlchemyGraphRepository(IGraphRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_nodes(
        self,
        organization_id: uuid.UUID,
        nodes: list[GraphNode],
    ) -> GraphUpsertResult:
        if not nodes:
            return GraphUpsertResult()

        existing = await self._session.execute(
            select(GraphNodeModel).where(
                GraphNodeModel.organization_id == organization_id,
                GraphNodeModel.identity.in_([n.identity for n in nodes]),
            ),
        )
        current = {row.identity: row for row in existing.scalars()}

        result = GraphUpsertResult()
        for node in nodes:
            row = current.get(node.identity)
            if row is None:
                if node.is_deleted:
                    result.soft_deleted += 1
                else:
                    result.created += 1
                self._session.add(
                    GraphNodeModel(
                        id=node.id,
                        organization_id=organization_id,
                        identity=node.identity,
                        type=node.type,
                        api_name=node.api_name,
                        namespace=node.namespace,
                        document_version=node.document_version,
                        document_fingerprint=node.document_fingerprint,
                        version=node.version,
                        previous_version=node.previous_version,
                        deleted=node.is_deleted,
                        created_at=node.created_at,
                        updated_at=node.updated_at,
                        deleted_at=node.deleted_at,
                        last_sync_job_id=node.last_sync_job_id,
                    ),
                )
            elif node.is_deleted:
                if row.deleted:
                    result.skipped += 1
                else:
                    result.soft_deleted += 1
                    row.deleted = True
                    row.deleted_at = node.deleted_at or datetime.now(UTC)
                    row.updated_at = datetime.now(UTC)
                    if node.last_sync_job_id is not None:
                        row.last_sync_job_id = node.last_sync_job_id
            elif (
                not row.deleted
                and row.type == node.type
                and row.api_name == node.api_name
                and row.namespace == node.namespace
                and row.document_version == node.document_version
                and row.document_fingerprint == node.document_fingerprint
            ):
                result.skipped += 1
            else:
                result.updated += 1
                if row.deleted:
                    row.previous_version = row.version
                    row.version = row.version + 1
                row.deleted = False
                row.deleted_at = None
                row.type = node.type
                row.api_name = node.api_name
                row.namespace = node.namespace
                row.document_version = node.document_version
                row.document_fingerprint = node.document_fingerprint
                row.updated_at = datetime.now(UTC)
                if node.last_sync_job_id is not None:
                    row.last_sync_job_id = node.last_sync_job_id
        try:
            await self._session.flush()
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            return await self.upsert_nodes(organization_id, nodes)
        return result

    async def upsert_edges(
        self,
        organization_id: uuid.UUID,
        edges: list[GraphEdge],
    ) -> GraphUpsertResult:
        if not edges:
            return GraphUpsertResult()

        existing = await self._session.execute(
            select(GraphEdgeModel).where(
                GraphEdgeModel.organization_id == organization_id,
                GraphEdgeModel.source_identity.in_(
                    {e.source_identity for e in edges},
                ),
                GraphEdgeModel.target_identity.in_(
                    {e.target_identity for e in edges},
                ),
            ),
        )
        current = {
            (row.source_identity, row.target_identity, row.relationship_type): row
            for row in existing.scalars()
        }

        result = GraphUpsertResult()
        for edge in edges:
            key = (
                edge.source_identity,
                edge.target_identity,
                edge.relationship_type.value,
            )
            row = current.get(key)
            if row is None:
                if edge.is_deleted:
                    result.soft_deleted += 1
                else:
                    result.created += 1
                self._session.add(
                    GraphEdgeModel(
                        id=edge.id,
                        organization_id=organization_id,
                        source_identity=edge.source_identity,
                        source_api_name=edge.source_api_name,
                        source_type=edge.source_type,
                        target_identity=edge.target_identity,
                        target_api_name=edge.target_api_name,
                        target_type=edge.target_type,
                        relationship_type=edge.relationship_type.value,
                        version=edge.version,
                        previous_version=edge.previous_version,
                        deleted=edge.is_deleted,
                        created_at=edge.created_at,
                        updated_at=edge.updated_at,
                        deleted_at=edge.deleted_at,
                        last_sync_job_id=edge.last_sync_job_id,
                    ),
                )
            elif edge.is_deleted:
                if row.deleted:
                    result.skipped += 1
                else:
                    result.soft_deleted += 1
                    row.deleted = True
                    row.deleted_at = edge.deleted_at or datetime.now(UTC)
                    row.updated_at = datetime.now(UTC)
                    if edge.last_sync_job_id is not None:
                        row.last_sync_job_id = edge.last_sync_job_id
            elif (
                not row.deleted
                and row.source_api_name == edge.source_api_name
                and row.source_type == edge.source_type
                and row.target_api_name == edge.target_api_name
                and row.target_type == edge.target_type
            ):
                result.skipped += 1
            else:
                result.updated += 1
                if row.deleted:
                    row.previous_version = row.version
                    row.version = row.version + 1
                row.deleted = False
                row.deleted_at = None
                row.source_api_name = edge.source_api_name
                row.source_type = edge.source_type
                row.target_api_name = edge.target_api_name
                row.target_type = edge.target_type
                row.updated_at = datetime.now(UTC)
                if edge.last_sync_job_id is not None:
                    row.last_sync_job_id = edge.last_sync_job_id
        try:
            await self._session.flush()
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            return await self.upsert_edges(organization_id, edges)
        return result

    async def soft_delete_nodes(
        self,
        organization_id: uuid.UUID,
        identities: set[str],
        *,
        sync_job_id: uuid.UUID | None = None,
    ) -> int:
        if not identities:
            return 0
        result = await self._session.execute(
            select(GraphNodeModel).where(
                GraphNodeModel.organization_id == organization_id,
                GraphNodeModel.identity.in_(identities),
                GraphNodeModel.deleted.is_(False),
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

    async def soft_delete_edges_for_node(
        self,
        organization_id: uuid.UUID,
        identity: str,
        *,
        sync_job_id: uuid.UUID | None = None,
    ) -> int:
        result = await self._session.execute(
            select(GraphEdgeModel).where(
                GraphEdgeModel.organization_id == organization_id,
                or_(
                    GraphEdgeModel.source_identity == identity,
                    GraphEdgeModel.target_identity == identity,
                ),
                GraphEdgeModel.deleted.is_(False),
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

    async def soft_delete_missing_edges_for_source(
        self,
        organization_id: uuid.UUID,
        source_identity: str,
        seen_edges: set[tuple[str, str]],
        *,
        sync_job_id: uuid.UUID | None = None,
    ) -> int:
        result = await self._session.execute(
            select(GraphEdgeModel).where(
                GraphEdgeModel.organization_id == organization_id,
                GraphEdgeModel.source_identity == source_identity,
                GraphEdgeModel.deleted.is_(False),
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

    async def soft_delete_edges_for_sources(
        self,
        organization_id: uuid.UUID,
        source_identities: set[str],
        *,
        sync_job_id: uuid.UUID | None = None,
    ) -> int:
        if not source_identities:
            return 0
        result = await self._session.execute(
            select(GraphEdgeModel).where(
                GraphEdgeModel.organization_id == organization_id,
                GraphEdgeModel.source_identity.in_(source_identities),
                GraphEdgeModel.deleted.is_(False),
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

    async def get_node(
        self,
        organization_id: uuid.UUID,
        identity: str,
    ) -> GraphNode | None:
        result = await self._session.execute(
            select(GraphNodeModel).where(
                GraphNodeModel.organization_id == organization_id,
                GraphNodeModel.identity == identity,
            ),
        )
        row = result.scalar_one_or_none()
        return _node_to_entity(row) if row else None

    async def get_nodes_by_identities(
        self,
        organization_id: uuid.UUID,
        identities: set[str],
    ) -> list[GraphNode]:
        if not identities:
            return []
        result = await self._session.execute(
            select(GraphNodeModel).where(
                GraphNodeModel.organization_id == organization_id,
                GraphNodeModel.identity.in_(identities),
            ),
        )
        return [_node_to_entity(row) for row in result.scalars()]

    async def get_edges_by_keys(
        self,
        organization_id: uuid.UUID,
        keys: set[tuple[str, str, str]],
    ) -> list[GraphEdge]:
        if not keys:
            return []
        result = await self._session.execute(
            select(GraphEdgeModel).where(
                GraphEdgeModel.organization_id == organization_id,
                GraphEdgeModel.source_identity.in_({k[0] for k in keys}),
                GraphEdgeModel.target_identity.in_({k[1] for k in keys}),
                GraphEdgeModel.relationship_type.in_({k[2] for k in keys}),
            ),
        )
        rows = [
            row
            for row in result.scalars()
            if (
                row.source_identity,
                row.target_identity,
                row.relationship_type,
            )
            in keys
        ]
        return [_edge_to_entity(row) for row in rows]

    async def list_active_nodes(
        self,
        organization_id: uuid.UUID,
        *,
        limit: int = 1000,
        offset: int = 0,
        metadata_type: str | None = None,
    ) -> list[GraphNode]:
        query = select(GraphNodeModel).where(
            GraphNodeModel.organization_id == organization_id,
            GraphNodeModel.deleted.is_(False),
        )
        if metadata_type is not None:
            query = query.where(GraphNodeModel.type == metadata_type)
        result = await self._session.execute(
            query.order_by(GraphNodeModel.api_name)
            .limit(limit)
            .offset(offset),
        )
        return [_node_to_entity(row) for row in result.scalars()]

    async def list_active_edges(
        self,
        organization_id: uuid.UUID,
        *,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[GraphEdge]:
        result = await self._session.execute(
            select(GraphEdgeModel)
            .where(
                GraphEdgeModel.organization_id == organization_id,
                GraphEdgeModel.deleted.is_(False),
            )
            .order_by(GraphEdgeModel.source_api_name)
            .limit(limit)
            .offset(offset),
        )
        return [_edge_to_entity(row) for row in result.scalars()]

    async def count_nodes(
        self,
        organization_id: uuid.UUID,
    ) -> int:
        result = await self._session.execute(
            select(func.count(GraphNodeModel.id)).where(
                GraphNodeModel.organization_id == organization_id,
            ),
        )
        return int(result.scalar_one())

    async def count_edges(
        self,
        organization_id: uuid.UUID,
    ) -> int:
        result = await self._session.execute(
            select(func.count(GraphEdgeModel.id)).where(
                GraphEdgeModel.organization_id == organization_id,
            ),
        )
        return int(result.scalar_one())
