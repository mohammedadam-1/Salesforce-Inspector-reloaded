from __future__ import annotations

from typing import Any

from pydantic import Field

from sfir_backend.domain.canonical.base import MetadataComponent


class MetadataQuickAction(MetadataComponent):
    type: str = "quick_action"
    object_api_name: str = ""
    action_type: str = "Create"
    target_object: str | None = None
    target_record_type: str | None = None
    target_field_list: str | None = None
    height: int | None = None
    width: int | None = None
    icon: str | None = None
    options_create: bool = True
    options_edit: bool = True
    options_event: bool = False


class MetadataLightningPage(MetadataComponent):
    type: str = "lightning_page"
    master_label: str = ""
    description: str | None = None
    page_type: str = "RecordPage"
    template: str | None = None
    regions: list[dict[str, Any]] = Field(default_factory=list)
