from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, TypeVar

T = TypeVar("T")


@dataclass
class ParsingResult[T]:
    success: bool
    data: T | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def ok(cls, data: T) -> ParsingResult[T]:
        return cls(success=True, data=data)

    @classmethod
    def fail(cls, error: str) -> ParsingResult[T]:
        return cls(success=False, errors=[error])

    @classmethod
    def merge(cls, results: list[ParsingResult]) -> ParsingResult[list]:
        data: list = []
        errors: list[str] = []
        warnings: list[str] = []
        for r in results:
            if r.success and r.data is not None:
                if isinstance(r.data, list):
                    data.extend(r.data)
                else:
                    data.append(r.data)
            errors.extend(r.errors)
            warnings.extend(r.warnings)
        return cls(
            success=len(errors) == 0,
            data=data,
            errors=errors,
            warnings=warnings,
        )


class MetadataParser[T](ABC):
    metadata_type: str = ""

    @abstractmethod
    def can_parse(self, component_type: str) -> bool:
        ...

    @abstractmethod
    async def parse(self, raw: dict[str, Any]) -> ParsingResult[T]:
        ...

    @abstractmethod
    async def parse_body(self, body: str) -> ParsingResult[T]:
        ...


def parse_metadata_body(body: str) -> dict[str, Any] | str:
    cleaned = body.strip()
    if cleaned.startswith("<"):
        import xml.etree.ElementTree as ET

        return _xml_to_dict(ET.fromstring(cleaned))
    return cleaned


def _xml_to_dict(element: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for child in element:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        text = child.text.strip() if child.text and child.text.strip() else None

        child_dict = _xml_to_dict(child)
        if child_dict:
            value: Any = child_dict
        elif text is not None:
            value = text
        else:
            value = ""

        if tag in result:
            existing = result[tag]
            if not isinstance(existing, list):
                result[tag] = [existing]
            result[tag].append(value)
        else:
            result[tag] = value

    return result
