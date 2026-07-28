from __future__ import annotations

import hashlib
import json
from typing import Any

from sfir_backend.application.pipeline.normalizer.normalized_model import (
    NormalizedRelationship,
)
from sfir_backend.domain.canonical.base import MetadataComponent


def _canonical_json(obj: Any, exclude_fields: set[str] | None = None) -> str:
    exclude = exclude_fields or set()
    if isinstance(obj, MetadataComponent):
        data = obj.model_dump()
        for field in exclude:
            data.pop(field, None)
        return json.dumps(data, sort_keys=True, default=str)
    if isinstance(obj, dict):
        cleaned = {k: v for k, v in obj.items() if k not in exclude}
        return json.dumps(cleaned, sort_keys=True, default=str)
    return json.dumps(obj, sort_keys=True, default=str)


class FingerprintService:
    def compute_content_hash(self, component: MetadataComponent) -> str:
        serialized = _canonical_json(
            component,
            exclude_fields={"id", "relationships", "metadata_properties", "created_at", "updated_at", "hash"},
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def compute_relationship_hash(self, relationships: list[NormalizedRelationship]) -> str:
        pairs = sorted((r.type, r.target_identity) for r in relationships)
        serialized = json.dumps(pairs, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def compute_version_hash(self, content_hash: str, version: int) -> str:
        serialized = f"{content_hash}:{version}"
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def compute_fingerprint(self, content_hash: str, relationship_hash: str) -> str:
        serialized = f"{content_hash}:{relationship_hash}"
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
