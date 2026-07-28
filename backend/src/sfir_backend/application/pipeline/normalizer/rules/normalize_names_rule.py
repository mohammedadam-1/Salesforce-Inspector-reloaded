from __future__ import annotations

from sfir_backend.application.pipeline.normalizer.i_normalization_rule import (
    INormalizationRule,
)
from sfir_backend.application.pipeline.normalizer.normalized_model import (
    ComponentKey,
    NormalizedDocument,
)
from sfir_backend.domain.canonical.base import MetadataComponent


class NormalizeNamesRule(INormalizationRule):
    def can_handle(self, component: MetadataComponent) -> bool:
        return True

    def normalize(
        self,
        component: MetadataComponent,
        normalized: NormalizedDocument,
    ) -> NormalizedDocument:
        ns = component.namespace
        namespace = ns if ns else None
        normalized.namespace = namespace

        if namespace:
            normalized.fully_qualified_name = f"{namespace}___{component.api_name}"
        else:
            normalized.fully_qualified_name = component.api_name

        normalized.api_name = component.api_name
        normalized.qualified_name = component.api_name
        normalized.label = component.label or None

        normalized.component_key = ComponentKey(
            type=normalized.type,
            api_name=component.api_name,
            namespace=namespace,
        )
        return normalized
