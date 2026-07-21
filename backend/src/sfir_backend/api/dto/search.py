from typing import Any

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(description="Search query string")
    metadata_types: list[str] | None = Field(default=None, description="Filter by metadata types")
    namespace: str | None = None
    managed: bool | None = None
    org_id: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class SearchResultItem(BaseModel):
    id: str = Field(description="Component ID")
    component_type: str = Field(description="Metadata component type")
    component_name: str = Field(description="Component API name")
    description: str | None = None
    match_reason: str | None = None
    score: float = 0.0


class SearchResponse(BaseModel):
    items: list[SearchResultItem]
    total: int
    limit: int
    offset: int
    query: str
    namespace: str | None = None
    managed: bool | None = None


class AutocompleteRequest(BaseModel):
    prefix: str = Field(description="Search prefix", min_length=1)
    metadata_types: list[str] | None = None
    limit: int = Field(default=10, ge=1, le=50)


class AutocompleteItem(BaseModel):
    id: str
    component_name: str
    component_type: str
    label: str


class DependencyResult(BaseModel):
    source_type: str
    source_name: str
    target_type: str
    target_name: str
    dependency_type: str | None = None
    metadata: dict[str, Any] | None = None
