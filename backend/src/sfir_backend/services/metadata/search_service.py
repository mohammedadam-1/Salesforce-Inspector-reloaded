"""Full-text search over indexed metadata using PostgreSQL tsvector."""

import uuid
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.infrastructure.database.models.metadata import (
    MetadataComponent,
    MetadataField,
)


class MetadataSearchService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def search_components(
        self,
        organization_id: uuid.UUID,
        query: str,
        component_types: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Search metadata components using full-text search.

        Uses PostgreSQL tsvector search on the `search_vector` column.
        """
        ts_query = func.plainto_tsquery("english", query)
        ts_rank = func.ts_rank(MetadataComponent.search_vector, ts_query)

        conditions = [
            MetadataComponent.search_vector.op("@@")(ts_query),
            MetadataComponent.organization_id == organization_id,
            MetadataComponent.status == "active",
        ]

        if component_types:
            conditions.append(
                MetadataComponent.component_type.in_(component_types)
            )

        query_stmt = (
            select(
                MetadataComponent,
                ts_rank.label("rank"),
            )
            .where(*conditions)
            .order_by(ts_rank.desc())
            .limit(limit)
            .offset(offset)
        )

        count_stmt = (
            select(func.count())
            .select_from(MetadataComponent)
            .where(*conditions)
        )

        total_result = await self._session.execute(count_stmt)
        total = total_result.scalar() or 0

        result = await self._session.execute(query_stmt)
        rows = result.all()

        return [
            {
                "id": str(row.MetadataComponent.id),
                "component_type": row.MetadataComponent.component_type,
                "api_name": row.MetadataComponent.api_name,
                "full_name": row.MetadataComponent.full_name,
                "label": row.MetadataComponent.label,
                "namespace_prefix": row.MetadataComponent.namespace_prefix,
                "salesforce_id": row.MetadataComponent.salesforce_id,
                "status": row.MetadataComponent.status,
                "rank": float(row.rank),
            }
            for row in rows
        ], total

    async def search_fields(
        self,
        organization_id: uuid.UUID,
        query: str,
        data_types: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Search metadata fields using full-text search."""
        ts_query = func.plainto_tsquery("english", query)
        ts_rank = func.ts_rank(MetadataField.search_vector, ts_query)

        conditions = [
            MetadataField.search_vector.op("@@")(ts_query),
            MetadataField.organization_id == organization_id,
        ]

        if data_types:
            conditions.append(MetadataField.data_type.in_(data_types))

        query_stmt = (
            select(MetadataField, ts_rank.label("rank"))
            .where(*conditions)
            .order_by(ts_rank.desc())
            .limit(limit)
            .offset(offset)
        )

        count_stmt = (
            select(func.count())
            .select_from(MetadataField)
            .where(*conditions)
        )

        total_result = await self._session.execute(count_stmt)
        total = total_result.scalar() or 0

        result = await self._session.execute(query_stmt)
        rows = result.all()

        return [
            {
                "id": str(row.MetadataField.id),
                "component_id": str(row.MetadataField.component_id),
                "api_name": row.MetadataField.api_name,
                "label": row.MetadataField.label,
                "data_type": row.MetadataField.data_type,
                "is_custom": row.MetadataField.is_custom,
                "is_formula": row.MetadataField.is_formula,
                "is_required": row.MetadataField.is_required,
                "rank": float(row.rank),
            }
            for row in rows
        ], total

    async def get_component_with_fields(
        self,
        organization_id: uuid.UUID,
        component_id: uuid.UUID,
    ) -> dict[str, Any] | None:
        """Get a metadata component with all its fields."""
        result = await self._session.execute(
            select(MetadataComponent).where(
                MetadataComponent.id == component_id,
                MetadataComponent.organization_id == organization_id,
            )
        )
        component = result.scalar_one_or_none()
        if not component:
            return None

        fields_result = await self._session.execute(
            select(MetadataField).where(
                MetadataField.component_id == component_id,
            ).order_by(MetadataField.api_name)
        )
        fields = fields_result.scalars().all()

        return {
            "id": str(component.id),
            "component_type": component.component_type,
            "api_name": component.api_name,
            "full_name": component.full_name,
            "label": component.label,
            "namespace_prefix": component.namespace_prefix,
            "salesforce_id": component.salesforce_id,
            "status": component.status,
            "extra": component.extra,
            "created_at": component.created_at,
            "updated_at": component.updated_at,
            "fields": [
                {
                    "id": str(f.id),
                    "api_name": f.api_name,
                    "label": f.label,
                    "data_type": f.data_type,
                    "relationship_name": f.relationship_name,
                    "reference_to": f.reference_to,
                    "is_custom": f.is_custom,
                    "is_formula": f.is_formula,
                    "is_required": f.is_required,
                    "is_unique": f.is_unique,
                    "is_external_id": f.is_external_id,
                }
                for f in fields
            ],
        }

    async def get_component_types(
        self, organization_id: uuid.UUID
    ) -> list[str]:
        """Get distinct component types present in the organization."""
        result = await self._session.execute(
            select(MetadataComponent.component_type)
            .where(
                MetadataComponent.organization_id == organization_id,
                MetadataComponent.status == "active",
            )
            .distinct()
            .order_by(MetadataComponent.component_type)
        )
        return [row[0] for row in result.all()]

    async def get_data_types(self, organization_id: uuid.UUID) -> list[str]:
        """Get distinct field data types present."""
        result = await self._session.execute(
            select(MetadataField.data_type)
            .where(MetadataField.organization_id == organization_id)
            .distinct()
            .order_by(MetadataField.data_type)
        )
        return [row[0] for row in result.all()]
