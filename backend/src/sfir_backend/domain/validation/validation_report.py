"""Validation report models for the Metadata Validation & Consistency Engine.

These are pure domain data models — they carry no repository or persistence
dependencies and are safe to construct in any layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from datetime import datetime
from enum import StrEnum
from typing import Any


class ValidationSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ValidationCategory(StrEnum):
    COMPLETENESS = "completeness"
    CONSISTENCY = "consistency"
    DUPLICATE = "duplicate"
    INTEGRITY = "integrity"
    ORPHAN = "orphan"
    CANONICAL = "canonical"
    RELATIONSHIP = "relationship"
    UNSUPPORTED = "unsupported"


@dataclass
class ValidationFinding:
    """A single deterministic validation finding."""

    category: ValidationCategory
    severity: ValidationSeverity
    error_code: str
    message: str
    component_type: str = ""
    api_name: str = ""
    reference_type: str = ""
    reference_api_name: str = ""
    suggested_action: str = ""
    metadata: dict[str, Any] = dc_field(default_factory=dict)


@dataclass
class MetadataValidationReport:
    """The complete result of validating an organization's metadata."""

    validation_timestamp: datetime
    organization_id: str
    metadata_counts: dict[str, int]
    downloaded_counts: dict[str, int] | None = None
    missing_metadata: list[ValidationFinding] = dc_field(default_factory=list)
    broken_references: list[ValidationFinding] = dc_field(default_factory=list)
    duplicate_entries: list[ValidationFinding] = dc_field(default_factory=list)
    orphaned_entries: list[ValidationFinding] = dc_field(default_factory=list)
    consistency_failures: list[ValidationFinding] = dc_field(default_factory=list)
    integrity_failures: list[ValidationFinding] = dc_field(default_factory=list)
    canonical_failures: list[ValidationFinding] = dc_field(default_factory=list)
    relationship_notes: list[ValidationFinding] = dc_field(default_factory=list)
    unsupported_types: list[str] = dc_field(default_factory=list)
    findings: list[ValidationFinding] = dc_field(default_factory=list)
    validation_score: int = 100
    passed: bool = True

    @property
    def total_findings(self) -> int:
        return len(self.findings)

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == ValidationSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == ValidationSeverity.WARNING)

    def summary(self) -> dict[str, Any]:
        """Compact machine-readable summary of the report."""
        return {
            "validation_timestamp": self.validation_timestamp.isoformat(),
            "organization_id": self.organization_id,
            "metadata_counts": self.metadata_counts,
            "downloaded_counts": self.downloaded_counts,
            "total_findings": self.total_findings,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "missing_metadata": len(self.missing_metadata),
            "broken_references": len(self.broken_references),
            "duplicate_entries": len(self.duplicate_entries),
            "orphaned_entries": len(self.orphaned_entries),
            "consistency_failures": len(self.consistency_failures),
            "integrity_failures": len(self.integrity_failures),
            "canonical_failures": len(self.canonical_failures),
            "unsupported_types": self.unsupported_types,
            "validation_score": self.validation_score,
            "passed": self.passed,
        }
