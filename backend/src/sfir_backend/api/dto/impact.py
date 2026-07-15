import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ImpactAnalysisRequest(BaseModel):
    component_type: str = Field(description="Type of metadata component")
    component_name: str = Field(description="API name of the component")
    max_depth: int = Field(default=3, ge=1, le=10)
    include_details: bool = Field(default=True)


class ImpactSimulateRequest(BaseModel):
    component_type: str
    component_name: str
    change_type: str = Field(default="modify", pattern=r"^(modify|delete|rename)$")
    max_depth: int = Field(default=3, ge=1, le=10)


class ImpactedComponent(BaseModel):
    component_type: str
    component_name: str
    component_id: str
    impact_depth: int
    impact_path: list[str] | None = None
    change_type: str | None = None
    risk: str | None = Field(default=None, pattern=r"^(high|medium|low)$")


class ImpactAnalysisResponse(BaseModel):
    id: uuid.UUID
    source_type: str
    source_name: str
    impacted_components: list[ImpactedComponent]
    total_impacted: int
    max_depth: int
    created_at: datetime


class ImpactAnalysisSummary(BaseModel):
    id: uuid.UUID
    source: str
    total_impacted: int
    high_risk: int
    medium_risk: int
    low_risk: int
    created_at: datetime


class ImpactReport(BaseModel):
    id: uuid.UUID
    source_type: str
    source_name: str
    impacted_components: list[ImpactedComponent]
    summary: dict[str, Any]
    recommendations: list[str] | None = None
