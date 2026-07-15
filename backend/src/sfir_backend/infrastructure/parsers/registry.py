from __future__ import annotations

from sfir_backend.infrastructure.parsers.base import BaseParser
from sfir_backend.infrastructure.parsers.errors import UnsupportedMetadataTypeError


class ParserRegistry:
    def __init__(self) -> None:
        self._parsers: dict[str, BaseParser] = {}

    def register(self, parser: BaseParser) -> None:
        if not parser.metadata_type:
            raise ValueError(f"Parser {type(parser).__name__} has empty metadata_type")
        self._parsers[parser.metadata_type] = parser

    def get(self, metadata_type: str) -> BaseParser:
        parser = self._parsers.get(metadata_type)
        if parser is None:
            raise UnsupportedMetadataTypeError(f"No parser registered for '{metadata_type}'")
        return parser

    def has(self, metadata_type: str) -> bool:
        return metadata_type in self._parsers

    def list_types(self) -> list[str]:
        return list(self._parsers.keys())

    def register_all(self, parsers: list[BaseParser]) -> None:
        for parser in parsers:
            self.register(parser)

    def __len__(self) -> int:
        return len(self._parsers)
