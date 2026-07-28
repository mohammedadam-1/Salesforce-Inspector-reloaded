from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

dependency_analysis_duration = Histogram(
    name="sfir_dependency_analysis_duration_seconds",
    documentation="Dependency analysis duration",
    labelnames=["analysis_type"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

dependency_analysis_relations_found = Gauge(
    name="sfir_dependency_analysis_relations_found",
    documentation="Number of relations found by dependency analysis",
    labelnames=["analysis_type"],
)

impact_assessment_duration = Histogram(
    name="sfir_impact_assessment_duration_seconds",
    documentation="Impact assessment duration",
    labelnames=["assessment_type"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

impact_breaking_changes = Counter(
    name="sfir_impact_breaking_changes_total",
    documentation="Total breaking changes detected",
    labelnames=["assessment_type"],
)

impact_risk_score = Gauge(
    name="sfir_impact_risk_score",
    documentation="Impact risk score distribution",
    labelnames=["assessment_type", "severity"],
)

code_intelligence_duration = Histogram(
    name="sfir_code_intelligence_duration_seconds",
    documentation="Code intelligence analysis duration",
    labelnames=["analysis_type"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

code_intelligence_issues_found = Counter(
    name="sfir_code_intelligence_issues_total",
    documentation="Total code issues found",
    labelnames=["analysis_type", "severity"],
)

metadata_analysis_duration = Histogram(
    name="sfir_metadata_analysis_duration_seconds",
    documentation="Metadata analysis duration",
    labelnames=["metadata_type"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

documentation_duration = Histogram(
    name="sfir_documentation_duration_seconds",
    documentation="Documentation generation duration",
    labelnames=["doc_type"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

tool_execution_duration = Histogram(
    name="sfir_tool_execution_duration_seconds",
    documentation="Engineering tool execution duration",
    labelnames=["tool_name"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

tool_execution_total = Counter(
    name="sfir_tool_execution_total",
    documentation="Total tool executions",
    labelnames=["tool_name", "status"],
)

tool_permission_denied = Counter(
    name="sfir_tool_permission_denied_total",
    documentation="Total tool permission denials",
    labelnames=["tool_name"],
)

confidence_score_distribution = Gauge(
    name="sfir_confidence_score",
    documentation="Confidence score distribution",
    labelnames=["feature"],
)
