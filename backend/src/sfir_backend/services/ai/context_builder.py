"""Context builder — gathers relevant metadata context for AI prompts.

Retrieves metadata components, fields, and dependencies based on
the user's query to provide grounded context for LLM responses.
"""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.infrastructure.database.models.graph import DependencyEdge
from sfir_backend.infrastructure.database.models.metadata import (
    MetadataComponent,
    MetadataField,
)
from sfir_backend.services.metadata.search_service import MetadataSearchService


class ContextBuilder:
    """Builds enriched metadata context for AI prompts.

    Strategy:
    1. Search metadata for the user's query
    2. For each result, fetch fields and dependencies
    3. Format as structured text for LLM context
    """

    MAX_COMPONENTS = 20
    MAX_FIELDS_PER_COMPONENT = 30
    MAX_DEPENDENCIES = 15

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._search_service = MetadataSearchService(session)

    async def build_context(
        self,
        organization_id: uuid.UUID,
        query: str,
        component_ids: list[uuid.UUID] | None = None,
    ) -> str:
        """Build a metadata context string from a natural language query."""
        parts: list[str] = []
        parts.append(f"Organization ID: {organization_id}")
        parts.append("")

        if component_ids:
            for cid in component_ids:
                component_data = await self._search_service.get_component_with_fields(
                    organization_id, cid
                )
                if component_data:
                    parts.append(self._format_component(component_data))
        else:
            search_results, total = await self._search_service.search_components(
                organization_id=organization_id,
                query=query,
                limit=self.MAX_COMPONENTS,
            )

            if total == 0:
                return "No matching metadata found in the indexed Salesforce org."

            parts.append(f"Found {total} matching metadata components:")
            parts.append("")

            for result in search_results[:self.MAX_COMPONENTS]:
                component_data = await self._search_service.get_component_with_fields(
                    organization_id,
                    uuid.UUID(result["id"]),
                )
                if component_data:
                    parts.append(self._format_component(component_data, include_fields=False))

                    deps = await self._get_dependencies(
                        organization_id,
                        f"{result['component_type']}:{result['full_name']}",
                    )
                    if deps:
                        parts.append(f"  Dependencies: {deps}")
                    parts.append("")

        # Add data type reference
        try:
            data_types = await self._search_service.get_data_types(organization_id)
            parts.append("Available field data types: " + ", ".join(data_types[:20]))
        except Exception:
            pass

        return "\n".join(parts)

    async def build_component_context(
        self,
        organization_id: uuid.UUID,
        component_key: str,
    ) -> str:
        """Build context for a single component by its key (Type:Name)."""
        parts: list[str] = []

        component_type, api_name = component_key.split(":", 1)

        result = await self._session.execute(
            select(MetadataComponent).where(
                MetadataComponent.organization_id == organization_id,
                MetadataComponent.component_type == component_type,
                MetadataComponent.api_name == api_name,
            )
        )
        component = result.scalar_one_or_none()
        if not component:
            return f"No component found for key: {component_key}"

        component_data = await self._search_service.get_component_with_fields(
            organization_id, component.id
        )
        if component_data:
            parts.append(self._format_component(component_data))

        deps = await self._get_dependencies(organization_id, component_key, direction="upstream")
        if deps:
            parts.append(f"Referenced by: {deps}")

        deps_down = await self._get_dependencies(organization_id, component_key, direction="downstream")
        if deps_down:
            parts.append(f"References: {deps_down}")

        return "\n".join(parts)

    async def _get_dependencies(
        self,
        organization_id: uuid.UUID,
        component_key: str,
        direction: str = "upstream",
        max_items: int = 15,
    ) -> str | None:
        """Get formatted dependency list for a component."""
        if direction == "upstream":
            query = select(DependencyEdge).where(
                DependencyEdge.organization_id == organization_id,
                DependencyEdge.target_key == component_key,
            )
        else:
            query = select(DependencyEdge).where(
                DependencyEdge.organization_id == organization_id,
                DependencyEdge.source_key == component_key,
            )

        result = await self._session.execute(query.limit(max_items))
        edges = result.scalars().all()

        if not edges:
            return None

        items = []
        for e in edges[:max_items]:
            if direction == "upstream":
                items.append(f"{e.source_key} ({e.edge_type}, confidence: {e.confidence}%)")
            else:
                items.append(f"{e.target_key} ({e.edge_type}, confidence: {e.confidence}%)")

        return "; ".join(items)

    def _format_component(
        self,
        component_data: dict[str, Any],
        include_fields: bool = True,
    ) -> str:
        """Format a metadata component as readable text."""
        lines = [
            f"[{component_data['component_type']}] {component_data['api_name']}",
        ]

        if component_data.get("label"):
            lines[0] += f' — "{component_data["label"]}"'

        if component_data.get("namespace_prefix"):
            lines[0] += f" (namespace: {component_data['namespace_prefix']})"

        if component_data.get("extra"):
            extra = component_data["extra"]
            relevant = {k: v for k, v in extra.items() if isinstance(v, (str, bool, int, float)) and k != "Body"}
            if relevant:
                lines.append(f"  Attributes: {relevant}")

        if include_fields and component_data.get("fields"):
            lines.append("  Fields:")
            for f in component_data["fields"][:self.MAX_FIELDS_PER_COMPONENT]:
                ref = ""
                if f.get("reference_to", {}).get("refers_to"):
                    ref = f" → {', '.join(f['reference_to']['refers_to'])}"
                lines.append(
                    f"    - {f['api_name']} ({f['data_type']}){ref}"
                    f"{' [required]' if f.get('is_required') else ''}"
                    f"{' [unique]' if f.get('is_unique') else ''}"
                    f"{' [formula]' if f.get('is_formula') else ''}"
                )

                if f.get("picklistValues"):
                    picklist_vals = [p["value"] for p in f["picklistValues"][:5]]
                    lines.append(f"      Picklist: {', '.join(picklist_vals)}")

        return "\n".join(lines)
