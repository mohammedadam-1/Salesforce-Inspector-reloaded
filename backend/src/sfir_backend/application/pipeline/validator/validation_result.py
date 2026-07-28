from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any

from sfir_backend.domain.canonical.base import MetadataComponent


@dataclass
class ValidationResult:
    severity: str = "error"
    error_code: str = ""
    message: str = ""
    component_id: str = ""
    component_type: str = ""
    api_name: str = ""
    field_name: str | None = None
    suggested_action: str | None = None
    metadata: dict[str, Any] = dc_field(default_factory=dict)


@dataclass
class ValidationReport:
    results: list[ValidationResult] = dc_field(default_factory=list)
    valid: list[MetadataComponent] = dc_field(default_factory=list)
    invalid: list[tuple[MetadataComponent, list[ValidationResult]]] = dc_field(default_factory=list)
