from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AnalysisType(StrEnum):
    DELETE = "delete"
    RENAME = "rename"
    MODIFY = "modify"
    CREATE = "create"
    VERSION_UPGRADE = "version_upgrade"
    BULK_CHANGE = "bulk_change"
    DEPLOYMENT = "deployment"
    SIMULATION = "simulation"


class ImpactSeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ImpactStatus(StrEnum):
    BLOCKING = "blocking"
    WARNING = "warning"
    INFO = "info"
    SAFE = "safe"


class ChangeType(StrEnum):
    DELETE = "delete"
    RENAME = "rename"
    MODIFY = "modify"
    CREATE = "create"
    VERSION_UPGRADE = "version_upgrade"
    REPLACE = "replace"


class RecommendedAction(BaseModel):
    action: str = ""
    description: str = ""
    priority: str = "medium"
    component_key: str = ""
    status: ImpactStatus = ImpactStatus.INFO


class AffectedComponent(BaseModel):
    component_key: str = ""
    name: str = ""
    component_type: str = ""
    severity: ImpactSeverity = ImpactSeverity.INFO
    status: ImpactStatus = ImpactStatus.INFO
    change_type: ChangeType = ChangeType.MODIFY
    dependency_depth: int = 0
    path: list[str] = Field(default_factory=list)
    message: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ImpactPath(BaseModel):
    nodes: list[str] = Field(default_factory=list)
    edges: list[str] = Field(default_factory=list)
    total_depth: int = 0


class BlastRadius(BaseModel):
    direct_count: int = 0
    indirect_count: int = 0
    recursive_count: int = 0
    total_count: int = 0
    max_depth: int = 0
    has_circular_dependency: bool = False
    cross_package_count: int = 0
    cross_module_count: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)


class RiskAssessment(BaseModel):
    risk_score: float = 0.0
    severity: ImpactSeverity = ImpactSeverity.INFO
    confidence: float = 1.0
    max_dependency_depth: int = 0
    critical_path: list[str] = Field(default_factory=list)
    business_impact: str = ""
    deployment_risk: str = "low"
    rollback_complexity: str = "low"
    reasons: list[str] = Field(default_factory=list)


class DeploymentReadiness(BaseModel):
    is_ready: bool = True
    blocking_issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    safe_deployment_order: list[str] = Field(default_factory=list)
    rollback_steps: list[str] = Field(default_factory=list)
    risk_assessment: RiskAssessment = Field(default_factory=RiskAssessment)


class ImpactSummary(BaseModel):
    analysis_type: AnalysisType = AnalysisType.SIMULATION
    component_key: str = ""
    component_name: str = ""
    component_type: str = ""
    total_affected: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    blocking_count: int = 0
    max_depth: int = 0
    has_cycles: bool = False
    risk_score: float = 0.0
    risk_severity: ImpactSeverity = ImpactSeverity.INFO


class ImpactAnalysis(BaseModel):
    id: str = ""
    analysis_type: AnalysisType = AnalysisType.SIMULATION
    component_key: str = ""
    component_name: str = ""
    component_type: str = ""
    affected_components: list[AffectedComponent] = Field(default_factory=list)
    paths: list[ImpactPath] = Field(default_factory=list)
    blast_radius: BlastRadius = Field(default_factory=BlastRadius)
    risk_assessment: RiskAssessment = Field(default_factory=RiskAssessment)
    deployment_readiness: DeploymentReadiness = Field(default_factory=DeploymentReadiness)
    summary: ImpactSummary = Field(default_factory=ImpactSummary)
    warnings: list[str] = Field(default_factory=list)
    recommended_actions: list[RecommendedAction] = Field(default_factory=list)
    created_at: datetime | None = None
    took_ms: float = 0.0


class ImpactReport(BaseModel):
    title: str = ""
    analysis: ImpactAnalysis = Field(default_factory=ImpactAnalysis)
    affected_by_type: dict[str, list[AffectedComponent]] = Field(default_factory=dict)
    critical_components: list[AffectedComponent] = Field(default_factory=list)
    dependency_tree: list[ImpactPath] = Field(default_factory=list)
    recommendations: list[RecommendedAction] = Field(default_factory=list)
    deployment_order: list[str] = Field(default_factory=list)
    rollback_plan: list[str] = Field(default_factory=list)


class SimulationRequest(BaseModel):
    component_key: str = ""
    change_type: ChangeType = ChangeType.DELETE
    metadata: dict[str, Any] = Field(default_factory=dict)
    simulate_rename: str = ""
    simulate_delete: bool = False
    simulate_modify: bool = False


class SimulationResult(BaseModel):
    request: SimulationRequest = Field(default_factory=SimulationRequest)
    analysis: ImpactAnalysis = Field(default_factory=ImpactAnalysis)
    is_safe: bool = True
    blocking_issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
