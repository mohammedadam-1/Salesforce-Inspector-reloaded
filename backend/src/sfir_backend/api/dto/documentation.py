import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DocumentationGenerateRequest(BaseModel):
    component_ids: list[str] | None = None
    metadata_types: list[str] | None = None
    include_dependencies: bool = Field(default=True)
    include_usage: bool = Field(default=True)
    format: str = Field(default="markdown", pattern=r"^(markdown|html|json)$")


class DocumentationExportRequest(BaseModel):
    component_ids: list[str] | None = None
    format: str = Field(default="markdown", pattern=r"^(markdown|html|json|pdf)$")
    include_metadata: bool = Field(default=True)


class DocumentationItem(BaseModel):
    id: str
    component_type: str
    component_name: str
    description: str | None = None
    fields: list[dict[str, Any]] | None = None
    dependencies: list[dict[str, str]] | None = None
    usage: list[str] | None = None
    generated_at: datetime | None = None


class DocumentationResponse(BaseModel):
    id: uuid.UUID
    status: str
    total_components: int
    components: list[DocumentationItem]
    format: str
    created_at: datetime


class DocumentationListResponse(BaseModel):
    items: list[DocumentationItem]
    total: int


class ComponentDocRequest(BaseModel):
    component_type: str
    component_name: str
