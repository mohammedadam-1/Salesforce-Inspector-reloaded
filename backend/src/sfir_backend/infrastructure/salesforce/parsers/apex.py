from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sfir_backend.domain.metadata.apex import ApexClass, ApexTrigger
from sfir_backend.infrastructure.salesforce.parsers.base import MetadataParser, ParsingResult


def _parse_body_symbols(body: str) -> list[dict]:
    symbols: list[dict] = []

    class_pattern = re.compile(
        r"(?:global|public|private|protected)?\s*"
        r"(?:abstract|virtual|with sharing|without sharing|inherited sharing)?\s*"
        r"class\s+(\w+)",
    )
    for m in class_pattern.finditer(body):
        symbols.append({"type": "class", "name": m.group(1)})

    method_pattern = re.compile(
        r"(?:global|public|private|protected|static|virtual|override|abstract)?\s*"
        r"(?:[\w<>[\],\s]+)\s+(\w+)\s*\(",
    )
    for m in method_pattern.finditer(body):
        symbols.append({"type": "method", "name": m.group(1)})

    ref_pattern = re.compile(r"\b([A-Z]\w*)\b\.\s*\w+\s*\(")
    seen: set[str] = set()
    for m in ref_pattern.finditer(body):
        ref = m.group(1)
        if ref not in {"System", "String", "Integer", "Boolean", "Long", "Double",
                        "Decimal", "Date", "Datetime", "Time", "Id", "Blob",
                        "Object", "Set", "List", "Map", "SObject",
                        "Schema", "JSON", "Math", "Test", "PageReference",
                        "Type", "Pattern", "EncodingUtil", "Url"} and ref not in seen:
            seen.add(ref)
            symbols.append({"type": "reference", "name": ref})

    return symbols


def _extract_object_references(body: str) -> list[str]:
    patterns = [
        r"INSERT\s+(\w+)",
        r"UPDATE\s+(\w+)",
        r"UPSERT\s+(\w+)",
        r"DELETE\s+(\w+)",
        r"SELECT\s+.*?\s+FROM\s+(\w+)",
        r"\[SELECT\s+.*?\s+FROM\s+(\w+)",
    ]
    seen: set[str] = set()
    refs: list[str] = []
    for pat in patterns:
        for m in re.finditer(pat, body, re.IGNORECASE | re.DOTALL):
            obj = m.group(1)
            if obj not in seen and obj[0].isupper() and obj != "SObject":
                seen.add(obj)
                refs.append(obj)
    return refs


class ApexClassParser(MetadataParser[ApexClass]):
    metadata_type = "ApexClass"

    def can_parse(self, component_type: str) -> bool:
        return component_type in {"ApexClass", "ApexClassMember"}

    async def parse(self, raw: dict[str, Any]) -> ParsingResult[ApexClass]:
        try:
            name: str = raw.get("Name", "")
            body: str = raw.get("Body", "")
            if not body:
                return ParsingResult.fail("No body content for ApexClass")
            api_version = raw.get("ApiVersion") or raw.get("ApiVersion", 0)
            lm = raw.get("LastModifiedDate")
            last_modified = (
                _parse_datetime(lm) if lm and isinstance(lm, str) else None
            )
            symbols = _parse_body_symbols(body)
            cls = ApexClass(
                name=name,
                body=body,
                api_version=int(api_version) if api_version else 0,
                status=raw.get("Status", "Active"),
                component_id=raw.get("Id"),
                namespace_prefix=raw.get("NamespacePrefix"),
                last_modified_date=last_modified,
                symbols=symbols,
            )
            return ParsingResult.ok(cls)
        except Exception as e:
            return ParsingResult.fail(f"ApexClass parse error: {e}")

    async def parse_body(self, body: str) -> ParsingResult[ApexClass]:
        try:
            symbols = _parse_body_symbols(body)
            cls = ApexClass(name="", body=body, symbols=symbols)
            return ParsingResult.ok(cls)
        except Exception as e:
            return ParsingResult.fail(f"ApexClass body parse error: {e}")


class ApexTriggerParser(MetadataParser[ApexTrigger]):
    metadata_type = "ApexTrigger"

    def can_parse(self, component_type: str) -> bool:
        return component_type == "ApexTrigger"

    async def parse(self, raw: dict[str, Any]) -> ParsingResult[ApexTrigger]:
        try:
            name: str = raw.get("Name", "")
            body: str = raw.get("Body", "")
            if not body:
                return ParsingResult.fail("No body content for ApexTrigger")
            obj_type = raw.get("TableEnumOrId") or raw.get("ObjectType", "")
            lm = raw.get("LastModifiedDate")
            last_modified = (
                _parse_datetime(lm) if lm and isinstance(lm, str) else None
            )
            trig = ApexTrigger(
                name=name,
                body=body,
                object_type=obj_type,
                api_version=int(raw.get("ApiVersion", 0)),
                status=raw.get("Status", "Active"),
                component_id=raw.get("Id"),
                last_modified_date=last_modified,
            )
            return ParsingResult.ok(trig)
        except Exception as e:
            return ParsingResult.fail(f"ApexTrigger parse error: {e}")

    async def parse_body(self, body: str) -> ParsingResult[ApexTrigger]:
        try:
            obj_type = ""
            m = re.search(r"trigger\s+\w+\s+on\s+(\w+)", body)
            if m:
                obj_type = m.group(1)
            trig = ApexTrigger(name="", body=body, object_type=obj_type)
            return ParsingResult.ok(trig)
        except Exception as e:
            return ParsingResult.fail(f"ApexTrigger body parse error: {e}")


def _parse_datetime(value: str) -> datetime | None:
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None
