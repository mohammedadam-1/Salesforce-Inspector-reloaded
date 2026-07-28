from __future__ import annotations

import hashlib

from sfir_backend.domain.canonical.base import MetadataComponent


class IdentityService:
    def compute_component_hash(
        self,
        organization_id: str,
        source_platform: str,
        type_name: str,
        api_name: str,
        namespace: str | None = None,
    ) -> str:
        h = hashlib.sha256()
        h.update(organization_id.strip().encode("utf-8"))
        h.update(b":")
        h.update(source_platform.strip().encode("utf-8"))
        h.update(b":")
        h.update(type_name.strip().encode("utf-8"))
        h.update(b":")
        h.update(api_name.strip().encode("utf-8"))
        if namespace:
            h.update(b":")
            h.update(namespace.strip().encode("utf-8"))
        return h.hexdigest()

    def compute_component_hash_from_component(self, component: MetadataComponent) -> str:
        org_id = str(component.organization_id) if component.organization_id else ""
        platform = component.source_platform.value if hasattr(component.source_platform, "value") else str(component.source_platform)
        return self.compute_component_hash(
            organization_id=org_id,
            source_platform=platform,
            type_name=component.type,
            api_name=component.api_name,
            namespace=component.namespace,
        )
