from __future__ import annotations

from datetime import datetime

from sfir_backend.application.pipeline.mapper.i_mapping_strategy import IMappingStrategy
from sfir_backend.domain.canonical.integration import MetadataEmailTemplate
from sfir_backend.domain.metadata.content import EmailTemplate


class EmailTemplateStrategy(IMappingStrategy):
    def can_handle(self, parsed: object) -> bool:
        return isinstance(parsed, EmailTemplate)

    def map(self, parsed: object) -> MetadataEmailTemplate:
        et = parsed
        return MetadataEmailTemplate(
            api_name=et.developer_name or et.name,
            label=et.name,
            template_type=et.template_type or "text",
            object_type=None,
            available=et.available,
            content=et.body or "",
            subject=et.subject or "",
            encoding=et.encoding or "UTF-8",
            metadata_properties={
                "component_id": et.component_id,
                "namespace_prefix": et.namespace_prefix,
                "html_body": et.html_body,
                "is_builder": et.is_builder,
                "description": et.description,
            },
        )
