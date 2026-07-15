from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SearchableType(StrEnum):
    OBJECT = "object"
    FIELD = "field"
    APEX_CLASS = "apex_class"
    TRIGGER = "trigger"
    FLOW = "flow"
    VALIDATION_RULE = "validation_rule"
    FORMULA = "formula"
    PERMISSION_SET = "permission_set"
    PROFILE = "profile"
    LAYOUT = "layout"
    RECORD_TYPE = "record_type"
    REPORT = "report"
    DASHBOARD = "dashboard"
    NAMED_CREDENTIAL = "named_credential"
    ROLE = "role"
    QUEUE = "queue"
    PUBLIC_GROUP = "public_group"
    SHARING_RULE = "sharing_rule"
    GLOBAL_VALUE_SET = "global_value_set"
    CUSTOM_METADATA = "custom_metadata"
    CUSTOM_SETTING = "custom_setting"
    LIGHTNING_PAGE = "lightning_page"
    QUICK_ACTION = "quick_action"
    EMAIL_TEMPLATE = "email_template"
    CONNECTED_APP = "connected_app"
    WORKFLOW = "workflow"
    APPROVAL_PROCESS = "approval_process"
    GLOBAL = "global"
    DEPENDENCY = "dependency"


class SearchFilter(BaseModel):
    field: str = ""
    value: Any = None
    operator: str = "eq"

    model_config = {"extra": "allow"}


class SearchSort(BaseModel):
    field: str = ""
    direction: str = "desc"


class SearchPagination(BaseModel):
    offset: int = 0
    limit: int = 20
    max_limit: int = 100


class SearchQuery(BaseModel):
    raw_query: str = ""
    tokens: list[str] = Field(default_factory=list)
    exact_phrases: list[str] = Field(default_factory=list)
    exclude_tokens: list[str] = Field(default_factory=list)
    filters: list[SearchFilter] = Field(default_factory=list)
    sort: SearchSort = Field(default_factory=SearchSort)
    pagination: SearchPagination = Field(default_factory=SearchPagination)
    metadata_types: list[str] = Field(default_factory=list)
    organization_id: str = ""
    namespace: str | None = None
    min_dependency_depth: int = 0
    max_dependency_depth: int | None = None

    def has_query(self) -> bool:
        return bool(self.raw_query.strip()) or bool(self.tokens)


class SearchDocument(BaseModel):
    id: str = ""
    api_name: str = ""
    label: str = ""
    description: str = ""
    metadata_type: str = ""
    namespace: str | None = None
    organization_id: str = ""
    status: str = "active"
    created_at: datetime | None = None
    updated_at: datetime | None = None
    metadata_properties: dict[str, Any] = Field(default_factory=dict)
    dependency_score: float = 0.0
    popularity_score: float = 0.0
    edge_count: int = 0

    def searchable_text(self) -> str:
        parts = [self.api_name, self.label, self.description or ""]
        if self.namespace:
            parts.append(self.namespace)
        return " ".join(parts)

    @property
    def key(self) -> str:
        return f"{self.metadata_type}:{self.api_name}"


class SearchResult(BaseModel):
    document: SearchDocument = Field(default_factory=SearchDocument)
    score: float = 0.0
    rank: int = 0
    matched_fields: list[str] = Field(default_factory=list)
    highlights: dict[str, str] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    results: list[SearchResult] = Field(default_factory=list)
    total_count: int = 0
    page: int = 0
    page_size: int = 20
    total_pages: int = 0
    query: str = ""
    took_ms: float = 0.0
    suggestions: list[str] = Field(default_factory=list)


class SearchSuggestion(BaseModel):
    text: str = ""
    metadata_type: str = ""
    score: float = 0.0


class SavedSearch(BaseModel):
    id: str = ""
    name: str = ""
    query: str = ""
    filters: list[SearchFilter] = Field(default_factory=list)
    sort: SearchSort = Field(default_factory=SearchSort)
    organization_id: str = ""
    created_by: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RecentSearch(BaseModel):
    id: str = ""
    query: str = ""
    organization_id: str = ""
    user_id: str = ""
    searched_at: datetime | None = None
    result_count: int = 0
