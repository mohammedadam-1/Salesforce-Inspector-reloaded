from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sfir_backend.domain.canonical import MetadataComponent
from sfir_backend.domain.entities.metadata_sync import MetadataVersion


@dataclass
class PipelineContext:
    organization_id: UUID
    connection_id: UUID
    sync_job_id: UUID
    sync_type: str = "full"
    change_source: str = "sync"

    component_type: str = ""
    raw_components: list[dict] = field(default_factory=list)
    component_hashes: dict[str, str] = field(default_factory=dict)

    parsed_components: list[MetadataComponent] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)

    validated_components: list[MetadataComponent] = field(default_factory=list)
    validation_results: list = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)

    mapped_components: list[MetadataComponent] = field(default_factory=list)

    canonical_components: list[MetadataComponent] = field(default_factory=list)

    normalized_components: list = field(default_factory=list)
    normalization_errors: list[str] = field(default_factory=list)

    saved_versions: list[MetadataVersion] = field(default_factory=list)

    persistence_result: dict = field(default_factory=lambda: {"saved": 0, "skipped": 0, "errors": 0})

    normalized_relationships: list = field(default_factory=list)

    graph_result: dict = field(default_factory=dict)
    graph_statistics: dict = field(default_factory=dict)
    graph_version: str = ""

    indexed_count: int = 0

    mapping_errors: list[str] = field(default_factory=list)

    stage_timing: dict[str, float] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0
