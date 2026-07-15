from __future__ import annotations

from typing import Any

from sfir_backend.domain.metadata.layouts import (
    Layout,
    LayoutItem,
    LayoutSection,
    RelatedListItem,
)
from sfir_backend.infrastructure.salesforce.parsers.base import (
    MetadataParser,
    ParsingResult,
    parse_metadata_body,
)


class LayoutParser(MetadataParser[Layout]):
    metadata_type = "Layout"

    def can_parse(self, component_type: str) -> bool:
        return component_type == "Layout"

    async def parse(self, raw: dict[str, Any]) -> ParsingResult[Layout]:
        try:
            name: str = raw.get("Name", raw.get("fullName", ""))
            obj_type: str = raw.get("TableEnumOrId", raw.get("objectType", raw.get("sobjectType", "")))  # noqa: E501
            sections_raw = raw.get("Sections", raw.get("sections", []))
            sections = [self._parse_section(s) for s in sections_raw if isinstance(s, dict)]

            related_raw = raw.get("RelatedLists", raw.get("relatedLists", []))
            related = [
                RelatedListItem(
                    object_name=rl.get("RelatedList", rl.get("relatedList", "")),
                    label=rl.get("Label", rl.get("label", "")),
                    fields=rl.get("Fields", rl.get("fields", [])),
                    sort_field=rl.get("SortField", rl.get("sortField")),
                    sort_order=rl.get("SortOrder", rl.get("sortOrder", "Asc")),
                )
                for rl in related_raw
                if isinstance(rl, dict)
            ]

            layout = Layout(
                name=name,
                object_type=obj_type,
                component_id=raw.get("Id"),
                sections=sections,
                related_lists=related,
            )
            return ParsingResult.ok(layout)
        except Exception as e:
            return ParsingResult.fail(f"Layout parse error: {e}")

    async def parse_body(self, body: str) -> ParsingResult[Layout]:
        try:
            parsed = parse_metadata_body(body)
            if isinstance(parsed, str):
                return ParsingResult.fail("Expected XML body")
            return await self.parse(parsed)
        except Exception as e:
            return ParsingResult.fail(f"Layout body parse error: {e}")

    def _parse_section(self, raw: dict[str, Any]) -> LayoutSection:
        return LayoutSection(
            label=raw.get("Label", raw.get("label", "")),
            collapsible=str(raw.get("Collapsible", "false")).lower() == "true",
            columns=int(raw.get("Columns", raw.get("columns", 1))),
            heading=raw.get("Heading", raw.get("heading")),
            layout_columns=[],
        )

    def _parse_item(self, raw: dict[str, Any]) -> LayoutItem:
        return LayoutItem(
            field=raw.get("Field", raw.get("field")),
            custom_link=raw.get("CustomLink", raw.get("customLink")),
            behavior=raw.get("Behavior", raw.get("behavior", "Required")),
        )
