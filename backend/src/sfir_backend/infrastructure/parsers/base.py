from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from sfir_backend.domain.canonical import (
    MetadataComponent,
)
from sfir_backend.infrastructure.parsers.errors import (
    FatalParserError,
    ParserError,
)


class ParserContext(BaseModel):
    organization_id: str = ""
    api_version: str | None = None
    source: str = "metadata_api"
    options: dict[str, Any] = Field(default_factory=dict)


class ExtractedReference(BaseModel):
    source_api_name: str = ""
    source_type: str = ""
    target_api_name: str = ""
    target_type: str = ""
    reference_type: str = "direct"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExtractedRelationship(BaseModel):
    type: str = "references"
    source_api_name: str = ""
    source_type: str = ""
    target_api_name: str = ""
    target_type: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ParseResult(BaseModel):
    component: MetadataComponent | None = None
    references: list[ExtractedReference] = Field(default_factory=list)
    relationships: list[ExtractedRelationship] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    duration_ms: float = 0.0
    metadata_type: str = ""


class BaseParser(ABC):
    metadata_type: str = ""
    api_version: str | None = None

    async def parse(
        self,
        raw: dict[str, Any],
        context: ParserContext | None = None,
    ) -> ParseResult:
        start = time.monotonic()
        result = ParseResult(metadata_type=self.metadata_type)
        try:
            validated = self._validate(raw, context)
            normalized = self._normalize(validated, context)
            component = self._parse(normalized, context)
            if component is not None:
                result.component = component
                result.references = self._extract_references(component, normalized, context)
                result.relationships = self._extract_relationships(
                    component, result.references, context,
                )
        except FatalParserError as exc:
            result.errors.append(str(exc))
        except ParserError as exc:
            result.warnings.append(str(exc))
        finally:
            result.duration_ms = (time.monotonic() - start) * 1000
        return result

    def _validate(
        self,
        raw: dict[str, Any],
        context: ParserContext | None = None,
    ) -> dict[str, Any]:
        _ = context
        return raw

    def _normalize(
        self,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> dict[str, Any]:
        _ = context
        return data

    @abstractmethod
    def _parse(
        self,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> MetadataComponent | None:
        ...

    def _extract_references(
        self,
        component: MetadataComponent,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> list[ExtractedReference]:
        _ = component, data, context
        return []

    def _extract_relationships(
        self,
        component: MetadataComponent,
        references: list[ExtractedReference],
        context: ParserContext | None = None,
    ) -> list[ExtractedRelationship]:
        _ = component, references, context
        return []
