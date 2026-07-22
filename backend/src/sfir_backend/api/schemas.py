from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationParams(BaseModel):
    limit: int = Field(default=50, ge=1, le=200, description="Items per page")
    offset: int = Field(default=0, ge=0, description="Offset from start")


class CursorParams(BaseModel):
    cursor: str | None = Field(default=None, description="Pagination cursor")
    limit: int = Field(default=50, ge=1, le=200)


class PaginatedResponse[T](BaseModel):
    items: list[T]
    total: int = Field(description="Total matching items")
    limit: int = Field(description="Items per page")
    offset: int = Field(description="Current offset")
    has_more: bool = Field(description="Whether more results exist")


class SortParams(BaseModel):
    sort_by: str | None = Field(default=None, description="Field to sort by")
    sort_order: str = Field(default="asc", pattern=r"^(asc|desc)$")


class ErrorDetail(BaseModel):
    field: str | None = Field(default=None, description="Field that failed validation")
    code: str = Field(description="Error code")
    message: str = Field(description="Human-readable error message")


class ProblemResponse(BaseModel):
    type: str = Field(default="about:blank", description="Error type URI")
    title: str = Field(description="Short error title")
    status: int = Field(description="HTTP status code")
    detail: str = Field(description="Detailed error message")
    instance: str | None = Field(default=None, description="Request path")
    correlation_id: str | None = Field(default=None)
    errors: list[ErrorDetail] | None = Field(default=None)


class MessageResponse(BaseModel):
    message: str = Field(description="Success message")
    correlation_id: str | None = None


class IdResponse(BaseModel):
    id: uuid.UUID = Field(description="Resource ID")


class VersionResponse(BaseModel):
    service: str = "sfir-backend"
    version: str = "0.1.0"
    environment: str = Field(description="Deployment environment")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
