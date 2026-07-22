from __future__ import annotations

from typing import Any

from sfir_backend.domain.metadata.objects import ValidationRule
from sfir_backend.infrastructure.salesforce.parsers.base import (
    MetadataParser,
    ParsingResult,
    parse_metadata_body,
)


class ValidationRuleParser(MetadataParser[ValidationRule]):
    metadata_type = "ValidationRule"

    def can_parse(self, component_type: str) -> bool:
        return component_type == "ValidationRule"

    async def parse(self, raw: dict[str, Any]) -> ParsingResult[ValidationRule]:
        try:
            rule = ValidationRule(
                name=raw.get("ValidationName", raw.get("fullName", "")),
                active=str(raw.get("Active", "true")).lower() == "true",
                error_message=raw.get("ErrorMessage", ""),
                error_display_field=raw.get("ErrorDisplayField"),
                formula=raw.get("Formula", ""),
                description=raw.get("Description"),
            )
            return ParsingResult.ok(rule)
        except Exception as e:
            return ParsingResult.fail(f"ValidationRule parse error: {e}")

    async def parse_body(self, body: str) -> ParsingResult[ValidationRule]:
        try:
            parsed = parse_metadata_body(body)
            if isinstance(parsed, str):
                return ParsingResult.fail("Expected XML body")
            return await self.parse(parsed)
        except Exception as e:
            return ParsingResult.fail(f"ValidationRule body parse error: {e}")
