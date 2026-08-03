"""Metadata Validation & Consistency Engine orchestrator.

The engine is the *proof layer* for the MetadataRepository single source of
truth. It is strictly read-only: it loads components through
``IMetadataRepository``, runs deterministic validation rules, and produces a
``MetadataValidationReport``. It never writes, updates, or deletes.

Repository access is limited to the public interface methods:
``get_by_organization``, ``get_types``, and (optionally) ``get_relationships`` /
``get_dependencies`` for component-level relationship validation. The engine
does NOT touch ORM models or persistence internals.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog

from sfir_backend.application.pipeline.validator.i_metadata_validator import (
    IMetadataValidator,
)
from sfir_backend.application.use_cases.metadata.validation_rules import (
    ValidationRuleSet,
    build_reference_registry,
    default_rule_set,
    to_pascal_type,
)
from sfir_backend.domain.entities.metadata_sync import SyncJob
from sfir_backend.domain.canonical.base import MetadataComponent
from sfir_backend.domain.repositories.metadata_repo import IMetadataRepository
from sfir_backend.domain.request_context import RequestContext
from sfir_backend.domain.validation.validation_report import (
    MetadataValidationReport,
    ValidationCategory,
    ValidationFinding,
    ValidationSeverity,
)

logger = structlog.get_logger(__name__)

# Severity weights used to derive the 0-100 validation score.
_ERROR_WEIGHT = 5
_WARNING_WEIGHT = 1


def aggregate_downloaded_counts(sync_jobs: list[SyncJob]) -> dict[str, int]:
    """Aggregate per-type downloaded counts from sync jobs.

    ``processed_items`` reflects how many items were actually downloaded and
    handed to the pipeline for a given ``metadata_type``. Only jobs with a
    ``metadata_type`` are counted; a job covering all types (``metadata_type``
    is None) cannot contribute per-type counts.
    """
    counts: dict[str, int] = {}
    for job in sync_jobs:
        if not job.metadata_type:
            continue
        canonical = to_pascal_type(job.metadata_type)
        counts[canonical] = counts.get(canonical, 0) + job.processed_items
    return counts


class MetadataValidationEngine:
    """Validates an organization's metadata through the repository interface."""

    def __init__(
        self,
        metadata_repo: IMetadataRepository,
        *,
        validator: IMetadataValidator | None = None,
        rule_set: ValidationRuleSet | None = None,
        sync_job_repo: Any | None = None,
    ) -> None:
        self._repo = metadata_repo
        self._validator = validator
        self._rule_set = rule_set or default_rule_set(validator)
        self._sync_job_repo = sync_job_repo

    async def downloaded_counts(
        self,
        organization_id: uuid.UUID,
        *,
        request_context: RequestContext | None = None,
    ) -> dict[str, int]:
        """Load per-type downloaded counts from sync jobs (if wired)."""
        if self._sync_job_repo is None:
            return {}
        jobs = await self._sync_job_repo.list_by_organization(
            organization_id, limit=500
        )
        return aggregate_downloaded_counts(jobs)

    async def validate(
        self,
        organization_id: uuid.UUID,
        *,
        downloaded_counts: dict[str, int] | None = None,
        request_context: RequestContext | None = None,
    ) -> MetadataValidationReport:
        """Run the full validation suite and return a report.

        Raises:
            PermissionError: tenant isolation violation via request_context.
        """
        components = await self._repo.get_by_organization(
            organization_id, request_context=request_context
        )
        present_types = await self._repo.get_types(
            organization_id, request_context=request_context
        )
        present_types = [to_pascal_type(t) for t in present_types]

        if downloaded_counts is None:
            downloaded_counts = await self.downloaded_counts(
                organization_id, request_context=request_context
            )
        if not downloaded_counts:
            downloaded_counts = None

        registry = build_reference_registry(components)
        metadata_counts = {
            to_pascal_type(t): len(names) for t, names in registry.items()
            if t not in ("*", "Objects")
        }

        findings = self._rule_set.run(
            components,
            registry=registry,
            downloaded_counts=downloaded_counts,
        )

        report = self._partition_and_score(
            organization_id=organization_id,
            components=components,
            present_types=present_types,
            metadata_counts=metadata_counts,
            downloaded_counts=downloaded_counts,
            findings=findings,
        )
        return report

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _partition_and_score(
        self,
        *,
        organization_id: uuid.UUID,
        components: list[MetadataComponent],
        present_types: list[str],
        metadata_counts: dict[str, int],
        downloaded_counts: dict[str, int] | None,
        findings: list[ValidationFinding],
    ) -> MetadataValidationReport:
        missing_metadata: list[ValidationFinding] = []
        broken_references: list[ValidationFinding] = []
        duplicate_entries: list[ValidationFinding] = []
        orphaned_entries: list[ValidationFinding] = []
        consistency_failures: list[ValidationFinding] = []
        integrity_failures: list[ValidationFinding] = []
        canonical_failures: list[ValidationFinding] = []
        relationship_notes: list[ValidationFinding] = []
        unsupported_types: list[str] = []

        for finding in findings:
            category = finding.category
            if category == ValidationCategory.COMPLETENESS:
                missing_metadata.append(finding)
            elif category == ValidationCategory.CONSISTENCY:
                consistency_failures.append(finding)
                if finding.error_code == "BROKEN_REFERENCE":
                    broken_references.append(finding)
            elif category == ValidationCategory.DUPLICATE:
                duplicate_entries.append(finding)
            elif category == ValidationCategory.ORPHAN:
                orphaned_entries.append(finding)
            elif category == ValidationCategory.INTEGRITY:
                integrity_failures.append(finding)
            elif category == ValidationCategory.CANONICAL:
                canonical_failures.append(finding)
            elif category == ValidationCategory.RELATIONSHIP:
                relationship_notes.append(finding)
            elif category == ValidationCategory.UNSUPPORTED:
                unsupported_types.append(finding.reference_type or finding.api_name)

        error_count = sum(
            1 for f in findings if f.severity == ValidationSeverity.ERROR
        )
        warning_count = sum(
            1 for f in findings if f.severity == ValidationSeverity.WARNING
        )
        score = max(
            0,
            100 - (error_count * _ERROR_WEIGHT) - (warning_count * _WARNING_WEIGHT),
        )
        passed = error_count == 0

        # Surface the read-path limitation as a relationship/integrity note when
        # the repository returned zero type-specific reference data.
        if components:
            self._append_read_path_note(
                findings,
                relationship_notes,
                components,
            )

        return MetadataValidationReport(
            validation_timestamp=datetime.now(timezone.utc),
            organization_id=str(organization_id),
            metadata_counts=metadata_counts,
            downloaded_counts=downloaded_counts,
            missing_metadata=missing_metadata,
            broken_references=broken_references,
            duplicate_entries=duplicate_entries,
            orphaned_entries=orphaned_entries,
            consistency_failures=consistency_failures,
            integrity_failures=integrity_failures,
            canonical_failures=canonical_failures,
            relationship_notes=relationship_notes,
            unsupported_types=sorted(set(unsupported_types)),
            findings=findings,
            validation_score=score,
            passed=passed,
        )

    def _append_read_path_note(
        self,
        findings: list[ValidationFinding],
        relationship_notes: list[ValidationFinding],
        components: list[MetadataComponent],
    ) -> None:
        """Emit an INFO note explaining the type-specific field read-path gap."""
        from sfir_backend.application.use_cases.metadata.validation_rules import (
            _OBJECT_REFERENCE_TYPES,
        )

        typed_reference_count = 0
        for c in components:
            canonical = to_pascal_type(c.type)
            if canonical in _OBJECT_REFERENCE_TYPES and (c.metadata_properties or {}):
                typed_reference_count += 1

        note = ValidationFinding(
            category=ValidationCategory.RELATIONSHIP,
            severity=ValidationSeverity.INFO,
            error_code="READ_PATH_NOTE",
            message=(
                "IMetadataRepository returns base MetadataComponent objects: "
                "type-specific reference fields (object_api_name, reference_to, "
                "etc.) are only visible when carried in metadata_properties. "
                "Raw relationship/dependency edges are not exposed, so "
                "edge-level duplicate/broken-edge validation is unavailable "
                "through the public interface."
            ),
            metadata={
                "components_loaded": len(components),
                "components_with_type_specific_properties": typed_reference_count,
            },
        )
        findings.append(note)
        relationship_notes.append(note)
