from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import structlog

from sfir_backend.domain.ai.models import AIFeature, AIProviderType

logger = structlog.get_logger(__name__)


SYSTEM_ROLE_TEMPLATES: dict[AIFeature, str] = {
    AIFeature.EXPLAIN_APEX: (
        "You are a Salesforce Apex expert. Explain the provided Apex code "
        "in clear, concise language. Reference specific metadata IDs where applicable."
    ),
    AIFeature.EXPLAIN_FLOW: (
        "You are a Salesforce Flow expert. Explain the provided flow definition "
        "step by step, covering all elements, connectors, and logic paths."
    ),
    AIFeature.EXPLAIN_VALIDATION_RULE: (
        "You are a Salesforce Validation Rule expert. Explain the formula, "
        "error message, and when this rule triggers."
    ),
    AIFeature.EXPLAIN_FORMULA: (
        "You are a Salesforce Formula expert. Explain the formula fields, "
        "their dependencies, and computed values."
    ),
    AIFeature.EXPLAIN_TRIGGER: (
        "You are a Salesforce Apex Trigger expert. Explain the trigger "
        "events, operations, and logic flow."
    ),
    AIFeature.EXPLAIN_PERMISSION_SET: (
        "You are a Salesforce Security expert. Explain the permission set "
        "assignments, enabled permissions, and security implications."
    ),
    AIFeature.EXPLAIN_REPORT: (
        "You are a Salesforce Reporting expert. Explain the report type, "
        "filters, groupings, and what the report shows."
    ),
    AIFeature.EXPLAIN_DASHBOARD: (
        "You are a Salesforce Dashboard expert. Explain the dashboard "
        "components, data sources, and visualizations."
    ),
    AIFeature.EXPLAIN_METADATA_RELATIONSHIPS: (
        "You are a Salesforce Metadata expert. Explain how the given metadata "
        "components relate to each other and their dependencies."
    ),
    AIFeature.SUMMARIZE_DEPENDENCY_GRAPH: (
        "You are a Salesforce Architecture expert. Summarize the dependency "
        "graph structure, key components, and architectural patterns found."
    ),
    AIFeature.SUMMARIZE_IMPACT_ANALYSIS: (
        "You are a Salesforce Change Management expert. Summarize the impact "
        "analysis findings, affected components, and recommended actions."
    ),
    AIFeature.GENERATE_EXECUTIVE_SUMMARY: (
        "You are a Technical Writer creating executive summaries. "
        "Provide a high-level overview suitable for non-technical stakeholders."
    ),
    AIFeature.GENERATE_TECHNICAL_SUMMARY: (
        "You are a Technical Writer creating technical summaries. "
        "Provide detailed technical documentation suitable for developers."
    ),
    AIFeature.GENERATE_RELEASE_NOTES: (
        "You are a Release Manager. Generate comprehensive release notes "
        "that describe what changed, why, and any required actions."
    ),
    AIFeature.GENERATE_DEPLOYMENT_NOTES: (
        "You are a DevOps Engineer. Generate deployment notes covering "
        "the deployment order, pre-requisites, and rollback plan."
    ),
    AIFeature.GENERATE_MIGRATION_SUMMARY: (
        "You are a Migration Specialist. Summarize the migration scope, "
        "affected components, and migration steps."
    ),
    AIFeature.NATURAL_LANGUAGE_SEARCH: (
        "You are a Salesforce Search expert. Convert natural language "
        "queries into precise metadata search results. "
        "Always reference the actual search result IDs."
    ),
    AIFeature.QUESTION_ANSWERING: (
        "You are a Salesforce Metadata Knowledge Base. Answer questions "
        "based exclusively on the provided context. "
        "If the context does not contain the answer, say so."
    ),
}

CONTEXT_TEMPLATES: dict[str, str] = {
    "metadata": (
        "=== METADATA CONTEXT ===\n"
        "The following metadata components are available:\n"
        "{metadata_content}\n"
    ),
    "dependency_graph": (
        "=== DEPENDENCY GRAPH ===\n"
        "The dependency graph shows the following structure:\n"
        "{graph_content}\n"
    ),
    "impact_analysis": (
        "=== IMPACT ANALYSIS ===\n"
        "Impact analysis results:\n"
        "{impact_content}\n"
    ),
    "documentation": (
        "=== DOCUMENTATION ===\n"
        "Existing documentation:\n"
        "{doc_content}\n"
    ),
    "search_results": (
        "=== SEARCH RESULTS ===\n"
        "Search results:\n"
        "{search_content}\n"
    ),
    "metadata_versions": (
        "=== VERSION HISTORY ===\n"
        "Metadata version history:\n"
        "{version_content}\n"
    ),
    "audit_log": (
        "=== AUDIT LOG ===\n"
        "Relevant audit log entries:\n"
        "{audit_content}\n"
    ),
}


class PromptTemplateEngine:
    def __init__(self) -> None:
        self._role_templates: dict[AIFeature, str] = dict(SYSTEM_ROLE_TEMPLATES)
        self._context_templates: dict[str, str] = dict(CONTEXT_TEMPLATES)
        self._custom_templates: dict[str, str] = {}

    def get_role_template(self, feature: AIFeature) -> str:
        return self._role_templates.get(feature, SYSTEM_ROLE_TEMPLATES[AIFeature.QUESTION_ANSWERING])

    def set_role_template(self, feature: AIFeature, template: str) -> None:
        self._role_templates[feature] = template

    def render_context(self, context_type: str, **kwargs: Any) -> str:
        template = self._context_templates.get(context_type)
        if not template:
            return ""
        return template.format(**kwargs)

    def set_context_template(self, name: str, template: str) -> None:
        self._context_templates[name] = template

    def register_custom_template(self, name: str, template: str) -> None:
        self._custom_templates[name] = template

    def get_custom_template(self, name: str) -> str | None:
        return self._custom_templates.get(name)


class PromptVersionManager:
    def __init__(self) -> None:
        self._versions: dict[str, dict[str, Any]] = {}

    def create_version(
        self,
        name: str,
        content: str,
        version: str = "1.0.0",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        version_id = hashlib.sha256(f"{name}:{version}".encode()).hexdigest()[:12]
        self._versions[version_id] = {
            "name": name,
            "content": content,
            "version": version,
            "metadata": metadata or {},
            "created_at": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc,
            ).isoformat(),
        }
        return version_id

    def get_version(self, version_id: str) -> dict[str, Any] | None:
        return self._versions.get(version_id)

    def list_versions(self, name: str | None = None) -> list[dict[str, Any]]:
        if name:
            return [v for v in self._versions.values() if v["name"] == name]
        return list(self._versions.values())

    def validate_prompt(self, prompt: str) -> list[str]:
        issues: list[str] = []
        placeholders = re.findall(r"\{(\w+)\}", prompt)
        for ph in placeholders:
            if ph not in ("metadata_content", "graph_content", "impact_content",
                           "doc_content", "search_content", "version_content",
                           "audit_content", "query", "context", "history"):
                issues.append(f"Unknown placeholder: {{{ph}}}")
        if len(prompt) > 100_000:
            issues.append(f"Prompt too long: {len(prompt)} chars (max 100000)")
        return issues
