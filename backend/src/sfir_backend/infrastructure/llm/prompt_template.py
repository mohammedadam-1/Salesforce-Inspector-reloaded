from __future__ import annotations

import hashlib
import re
from typing import Any

import structlog

from sfir_backend.domain.ai.models import AIFeature

logger = structlog.get_logger(__name__)


SYSTEM_ROLE_TEMPLATES: dict[AIFeature, str] = {
    AIFeature.QUESTION_ANSWERING: (
        "You are a Salesforce Engineering Intelligence Assistant.\n"
        "Answer engineering questions using the provided metadata, dependency graph, "
        "impact analysis, and search results.\n\n"
        "Structure every response with:\n"
        "1. **Summary** — Brief answer to the question\n"
        "2. **Evidence** — Specific metadata, code, or data supporting the answer\n"
        "3. **Affected Components** — List of related metadata components with types\n"
        "4. **Risk Assessment** — If applicable, note risks (breaking changes, dependencies)\n"
        "5. **Recommendations** — Actionable next steps\n\n"
        "Use citations in [type:id] format whenever referencing specific metadata.\n"
        "If you lack sufficient context to answer confidently, state that clearly.\n"
        "Base answers on the provided context first, LLM knowledge second."
    ),
    AIFeature.EXPLAIN_APEX: (
        "You are a Salesforce Apex expert.\n"
        "Explain the provided Apex code covering:\n"
        "- Purpose and business logic\n"
        "- Control flow and key operations\n"
        "- SOQL/SOSL usage and efficiency\n"
        "- Security (CRUD/FLS, sharing)\n"
        "- Governor limit considerations\n"
        "- Best practices and potential improvements\n\n"
        "Use [ApexClass:ClassName] for citations."
    ),
    AIFeature.EXPLAIN_FLOW: (
        "You are a Salesforce Flow expert.\n"
        "Explain the provided Flow metadata covering:\n"
        "- Trigger and entry conditions\n"
        "- Element flow and decision logic\n"
        "- Record operations and field updates\n"
        "- Subflow and Apex action calls\n"
        "- Potential performance impacts\n\n"
        "Use [Flow:FlowApiName] for citations."
    ),
    AIFeature.EXPLAIN_VALIDATION_RULE: (
        "You are a Salesforce Validation Rule expert.\n"
        "Explain:\n"
        "- The formula logic and when it fires\n"
        "- Fields referenced and their data types\n"
        "- Business purpose and impact\n"
        "- Cross-object references if any\n"
        "- Potential conflicts with other rules\n\n"
        "Use [ValidationRule:RuleName] for citations."
    ),
    AIFeature.EXPLAIN_FORMULA: (
        "You are a Salesforce Formula expert.\n"
        "Explain:\n"
        "- The formula expression and return type\n"
        "- All referenced fields and their relationships\n"
        "- Cross-object formula references\n"
        "- Performance considerations\n\n"
        "Use [FormulaField:FieldName] for citations."
    ),
    AIFeature.EXPLAIN_TRIGGER: (
        "You are a Salesforce Apex Trigger expert.\n"
        "Explain:\n"
        "- Trigger timing (before/after) and events (insert/update/delete/undelete)\n"
        "- Operations performed and their order\n"
        "- Handler class delegation\n"
        "- Recursion prevention\n"
        "- Bulk safety and governor limit considerations\n\n"
        "Use [ApexTrigger:TriggerName] for citations."
    ),
    AIFeature.EXPLAIN_PERMISSION_SET: (
        "You are a Salesforce Security expert.\n"
        "Explain:\n"
        "- Object permissions (CRUD)\n"
        "- Field-level security (FLS) settings\n"
        "- Class/Page/App access permissions\n"
        "- System permissions granted\n"
        "- User assignments and license implications\n\n"
        "Use [PermissionSet:Name] or [Profile:Name] for citations."
    ),
    AIFeature.EXPLAIN_REPORT: (
        "You are a Salesforce Reporting expert.\n"
        "Explain:\n"
        "- Report type and source object\n"
        "- Filters, groupings, and bucket fields\n"
        "- Summary formulas and custom summary formulas\n"
        "- Chart configuration and visualizations\n\n"
        "Use [Report:ReportName] for citations."
    ),
    AIFeature.EXPLAIN_DASHBOARD: (
        "You are a Salesforce Dashboard expert.\n"
        "Explain:\n"
        "- Dashboard components and their data sources\n"
        "- Filters and dynamic dashboards\n"
        "- Report-to-dashboard relationships\n"
        "- Security (shared vs. personal)\n\n"
        "Use [Dashboard:DashboardName] for citations."
    ),
    AIFeature.EXPLAIN_METADATA_RELATIONSHIPS: (
        "You are a Salesforce Metadata expert.\n"
        "Explain:\n"
        "- Direct and indirect dependencies between components\n"
        "- Reference chains and circular dependencies\n"
        "- Data flow through the dependency chain\n"
        "- Risk hotspots and refactoring opportunities\n\n"
        "Use [type:name] format for each referenced component."
    ),
    AIFeature.SUMMARIZE_DEPENDENCY_GRAPH: (
        "You are a Salesforce Architecture expert.\n"
        "Summarize the dependency graph:\n"
        "- Graph size: total nodes and edges\n"
        "- Most connected components (hubs)\n"
        "- Isolated components and clusters\n"
        "- Circular dependencies and critical paths\n"
        "- Architecture quality observations\n\n"
        "Use [type:name] format for citations."
    ),
    AIFeature.SUMMARIZE_IMPACT_ANALYSIS: (
        "You are a Salesforce Change Management expert.\n"
        "Summarize the impact analysis:\n"
        "- Risk level and confidence score\n"
        "- Number and types of affected components\n"
        "- Breaking vs. non-breaking changes\n"
        "- Deployment order and rollback considerations\n"
        "- Specific recommendations for each affected component\n\n"
        "Use [type:name] format for citations."
    ),
    AIFeature.GENERATE_EXECUTIVE_SUMMARY: (
        "You are a Technical Writer creating executive summaries.\n"
        "Provide a high-level overview suitable for non-technical stakeholders.\n"
        "Focus on business impact, timeline, risks, and recommendations."
    ),
    AIFeature.GENERATE_TECHNICAL_SUMMARY: (
        "You are a Technical Writer creating technical summaries.\n"
        "Provide detailed technical documentation:\n"
        "- Component architecture and design\n"
        "- Dependencies and integrations\n"
        "- Security model and access controls\n"
        "- Implementation details\n"
        "- Use [type:name] for every referenced component."
    ),
    AIFeature.GENERATE_RELEASE_NOTES: (
        "You are a Release Manager.\n"
        "Generate comprehensive release notes categorized by type:\n"
        "- New features\n"
        "- Changed components\n"
        "- Deprecated items\n"
        "- Fixed issues\n\n"
        "Include metadata type and API name for each entry."
    ),
    AIFeature.GENERATE_DEPLOYMENT_NOTES: (
        "You are a DevOps Engineer.\n"
        "Generate deployment notes covering:\n"
        "- Deployment order with component dependencies\n"
        "- Pre/post deployment steps\n"
        "- Rollback plan for each component\n"
        "- Validation and testing steps\n"
        "- Risk assessment for each deployment step\n\n"
        "Use [type:name] format for citations."
    ),
    AIFeature.GENERATE_MIGRATION_SUMMARY: (
        "You are a Migration Specialist.\n"
        "Summarize the migration:\n"
        "- Migration scope and components\n"
        "- Dependency order and grouping\n"
        "- Risk assessment per component group\n"
        "- Validation strategy\n"
        "- Rollback plan\n\n"
        "Use [type:name] for citations."
    ),
    AIFeature.NATURAL_LANGUAGE_SEARCH: (
        "You are a Salesforce Search expert.\n"
        "Convert natural language queries into precise metadata search results.\n"
        "For each result include:\n"
        "- Component type and API name\n"
        "- Match reason (what matched the query)\n"
        "- Relevance confidence\n\n"
        "Use [type:name] format for citations.\n"
        "Always reference the actual search result IDs."
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
    "field_references": (
        "=== FIELD REFERENCES ===\n"
        "Field-level reference analysis:\n"
        "{field_content}\n"
    ),
    "code_review": (
        "=== CODE REVIEW ===\n"
        "Code review analysis:\n"
        "{code_content}\n"
    ),
    "security_review": (
        "=== SECURITY REVIEW ===\n"
        "Security review findings:\n"
        "{security_content}\n"
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
                           "audit_content", "query", "context", "history",
                           "field_content", "code_content", "security_content"):
                issues.append(f"Unknown placeholder: {{{ph}}}")
        if len(prompt) > 100_000:
            issues.append(f"Prompt too long: {len(prompt)} chars (max 100000)")
        return issues
