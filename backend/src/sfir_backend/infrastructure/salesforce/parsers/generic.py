from __future__ import annotations

from typing import Any

from sfir_backend.infrastructure.salesforce.parsers.base import (
    MetadataParser,
    ParsingResult,
    parse_metadata_body,
)


class GenericMetadataParser(MetadataParser[dict]):
    metadata_type = "Generic"

    def can_parse(self, _component_type: str) -> bool:
        return True

    async def parse(self, raw: dict[str, Any]) -> ParsingResult[dict]:
        return ParsingResult.ok(raw)

    async def parse_body(self, body: str) -> ParsingResult[dict]:
        try:
            parsed = parse_metadata_body(body)
            if isinstance(parsed, str):
                return ParsingResult.ok({"Body": parsed})
            return ParsingResult.ok(parsed)
        except Exception as e:
            return ParsingResult.fail(f"Generic parse error: {e}")
