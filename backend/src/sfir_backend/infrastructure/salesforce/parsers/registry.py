from __future__ import annotations

from typing import Any

from sfir_backend.infrastructure.salesforce.parsers.base import MetadataParser, ParsingResult
from sfir_backend.infrastructure.salesforce.parsers.generic import GenericMetadataParser


class ParserRegistry:
    def __init__(self) -> None:
        self._parsers: dict[str, MetadataParser] = {}
        self._generic = GenericMetadataParser()

    def register(self, parser: MetadataParser) -> None:
        self._parsers[parser.metadata_type] = parser

    def get(self, component_type: str) -> MetadataParser:
        for parser in self._parsers.values():
            if parser.can_parse(component_type):
                return parser
        return self._generic

    def has_parser(self, component_type: str) -> bool:
        return any(parser.can_parse(component_type) for parser in self._parsers.values())

    async def parse(self, component_type: str, raw: dict[str, Any]) -> ParsingResult:
        parser = self.get(component_type)
        return await parser.parse(raw)

    async def parse_body(self, component_type: str, body: str) -> ParsingResult:
        parser = self.get(component_type)
        return await parser.parse_body(body)

    def registered_types(self) -> list[str]:
        return list(self._parsers.keys())


_registry: ParserRegistry | None = None


def get_registry() -> ParserRegistry:
    global _registry
    if _registry is None:
        _registry = ParserRegistry()
    return _registry


def register_parser(parser: MetadataParser) -> None:
    get_registry().register(parser)


def get_parser(component_type: str) -> MetadataParser:
    return get_registry().get(component_type)
