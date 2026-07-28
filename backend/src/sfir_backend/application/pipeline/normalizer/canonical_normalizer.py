from __future__ import annotations

import structlog

from sfir_backend.application.pipeline.normalizer.fingerprint_service import (
    FingerprintService,
)
from sfir_backend.application.pipeline.normalizer.i_normalization_rule import (
    INormalizationRule,
)
from sfir_backend.application.pipeline.normalizer.i_normalizer import INormalizer
from sfir_backend.application.pipeline.normalizer.identity_service import (
    IdentityService,
)
from sfir_backend.application.pipeline.normalizer.normalized_model import (
    NormalizationReport,
    NormalizedDocument,
    utc_now_str,
)
from sfir_backend.application.pipeline.normalizer.relationship_normalizer import (
    RelationshipNormalizer,
)
from sfir_backend.domain.canonical.base import MetadataComponent

logger = structlog.get_logger(__name__)


class CanonicalNormalizer(INormalizer):
    def __init__(
        self,
        identity_service: IdentityService | None = None,
        fingerprint_service: FingerprintService | None = None,
        relationship_normalizer: RelationshipNormalizer | None = None,
    ) -> None:
        self._identity_service = identity_service or IdentityService()
        self._fingerprint_service = fingerprint_service or FingerprintService()
        self._relationship_normalizer = relationship_normalizer or RelationshipNormalizer(self._identity_service)
        self._rules: list[INormalizationRule] = []

    def register(self, rule: INormalizationRule) -> None:
        self._rules.append(rule)

    def normalize(self, components: list[MetadataComponent]) -> NormalizationReport:
        normalized: list[NormalizedDocument] = []
        skipped: list[dict[str, str]] = []
        errors: list[str] = []

        org_id: str = ""
        platform: str = "salesforce"
        if components:
            c0 = components[0]
            org_id = str(c0.organization_id) if c0.organization_id else ""
            sp = c0.source_platform
            platform = sp.value if hasattr(sp, "value") else str(sp)

        for component in components:
            try:
                doc = self._normalize_one(component, org_id, platform)
                if doc is not None:
                    normalized.append(doc)
                else:
                    skipped.append({"api_name": component.api_name or "?", "type": component.type, "error": "normalization returned None"})
            except Exception as exc:
                msg = f"Normalization failed for {component.type}/{component.api_name or '?'}: {exc}"
                errors.append(msg)
                skipped.append({"api_name": component.api_name or "?", "type": component.type, "error": str(exc)})
                logger.warning("canonical_normalizer_component_failed", api_name=component.api_name, type=component.type, error=str(exc))

        return NormalizationReport(normalized=normalized, skipped=skipped, errors=errors)

    def _normalize_one(
        self,
        component: MetadataComponent,
        org_id: str,
        platform: str,
    ) -> NormalizedDocument | None:
        if component is None:
            return None
        if not component.api_name:
            return None

        identity = self._identity_service.compute_component_hash_from_component(component)
        content_hash = self._fingerprint_service.compute_content_hash(component)

        raw_rels: list = []
        for rel in component.relationships or []:
            tid = self._identity_service.compute_component_hash(
                organization_id=org_id,
                source_platform=platform,
                type_name=rel.target_type,
                api_name=rel.target_api_name,
            )
            raw_rels.append(NormalizedRelationship(
                type=rel.type.value if hasattr(rel.type, "value") else str(rel.type),
                target_identity=tid,
                target_fqdn=rel.target_api_name,
                metadata=dict(rel.metadata),
            ))

        extracted = self._relationship_normalizer.extract(component, org_id, platform)
        raw_rels.extend(extracted)
        deduped = self._relationship_normalizer.deduplicate(raw_rels)

        relationship_hash = self._fingerprint_service.compute_relationship_hash(deduped)
        fingerprint = self._fingerprint_service.compute_fingerprint(content_hash, relationship_hash)

        doc = NormalizedDocument(
            identity=identity,
            component_key=None,
            type=component.type,
            api_name=component.api_name,
            qualified_name=component.api_name,
            fully_qualified_name=component.api_name,
            label=component.label or None,
            namespace=component.namespace or None,
            description=component.description or None,
            version=component.version,
            status=component.status.value if hasattr(component.status, "value") else str(component.status),
            source_platform=platform,
            organization_id=org_id,
            owner_id=None,
            created_at=None,
            updated_at=None,
            fingerprint=fingerprint,
            content_hash=content_hash,
            properties=dict(component.metadata_properties or {}),
            relationships=deduped,
            normalized_at=utc_now_str(),
        )

        for rule in self._rules:
            try:
                if rule.can_handle(component):
                    doc = rule.normalize(component, doc)
            except Exception as exc:
                logger.warning(
                    "canonical_normalizer_rule_failed",
                    rule=type(rule).__name__,
                    error=str(exc),
                )

        return doc
