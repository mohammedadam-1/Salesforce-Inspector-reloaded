from __future__ import annotations

from typing import Any

from sfir_backend.application.use_cases.ai.code_intelligence import (
    CodeIntelligenceEngine,
)
from sfir_backend.application.use_cases.ai.dependency_analyzer import (
    DependencyAnalyzer,
)
from sfir_backend.application.use_cases.ai.documentation_generator import (
    DocumentationGenerator,
)
from sfir_backend.application.use_cases.ai.field_dependency_engine import (
    FieldDependencyEngine,
)
from sfir_backend.application.use_cases.ai.impact_assessor import ImpactAssessor
from sfir_backend.application.use_cases.ai.metadata_analyzer import MetadataAnalyzer
from sfir_backend.application.use_cases.ai.tools import AgentTool
from sfir_backend.domain.request_context import RequestContext

MISSING_REQUEST_CONTEXT_MESSAGE = (
    "Request context with organization identity is required for this tool."
)


def _organization_id_from_context(
    request_context: RequestContext | None,
) -> Any | None:
    if not request_context or not request_context.organization_id:
        return None
    return request_context.organization_id


class FieldImpactTool(AgentTool):
    def __init__(self, field_dep_engine: FieldDependencyEngine) -> None:
        self._engine = field_dep_engine

    @property
    def name(self) -> str:
        return "field_impact"

    @property
    def description(self) -> str:
        return "Find all components that reference a specific field or object"

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "object_name": {
                    "type": "string",
                    "description": "Salesforce object API name (e.g. Account, Opportunity)",
                },
                "field_name": {
                    "type": "string",
                    "description": "Field API name (optional — if omitted, finds all object references)",
                },
            },
            "required": ["object_name"],
        }

    async def execute(
        self,
        object_name: str,
        field_name: str = "",
        request_context: RequestContext | None = None,
    ) -> str:
        org_id = _organization_id_from_context(request_context)
        if org_id is None:
            return MISSING_REQUEST_CONTEXT_MESSAGE
        if field_name:
            refs = await self._engine.find_field_references(org_id, object_name, field_name)
            if not refs:
                return f"No references found for `{object_name}.{field_name}`."
            lines = [f"References to `{object_name}.{field_name}` ({len(refs)} total):"]
            for r in refs[:30]:
                lines.append(f"- {r['component_type']}: `{r['component_name']}` ({r['confidence']})")
            return "\n".join(lines)
        else:
            result = await self._engine.find_object_references(org_id, object_name)
            text_refs = result.get("text_references", [])
            upstream = result.get("graph_upstream", [])
            downstream = result.get("graph_downstream", [])

            parts: list[str] = []
            if text_refs:
                parts.append(f"References to `{object_name}` ({len(text_refs)} found in source code):")
                for r in text_refs[:20]:
                    parts.append(f"- {r['component_type']}: `{r['component_name']}`")
            if upstream:
                parts.append(f"\nGraph dependencies — used by ({len(upstream)}):")
                for d in upstream[:15]:
                    parts.append(f"- {d['component_type']}: `{d['component_name']}`")
            if downstream:
                parts.append(f"\nGraph dependencies — depends on ({len(downstream)}):")
                for d in downstream[:15]:
                    parts.append(f"- {d['component_type']}: `{d['component_name']}`")
            if not parts:
                return f"No references found for `{object_name}`."
            return "\n".join(parts)


class CodeReviewTool(AgentTool):
    @property
    def name(self) -> str:
        return "code_review"

    @property
    def description(self) -> str:
        return "Analyze Apex/LWC/Aura code for quality, performance, security, and best practices"

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code_snippet": {
                    "type": "string",
                    "description": "Apex, LWC (JS/HTML), or Aura code to review",
                },
                "language": {
                    "type": "string",
                    "enum": ["apex", "lwc", "aura", "visualforce"],
                    "description": "Programming language of the code",
                },
            },
            "required": ["code_snippet", "language"],
        }

    async def execute(
        self,
        code_snippet: str,
        language: str,
        request_context: RequestContext | None = None,
    ) -> str:
        _ = request_context
        lines: list[str] = [f"## Code Review — {language.upper()}\n"]
        total_lines = code_snippet.count("\n") + 1
        total_chars = len(code_snippet)

        lines.append(f"- **Size**: {total_lines} lines, {total_chars} characters")

        if language == "apex":
            observations = self._review_apex(code_snippet)
            lines.append(f"- **Observations**: {len(observations)}")
            for obs in observations:
                lines.append(f"  - {obs}")

            security = self._check_apex_security(code_snippet)
            if security:
                lines.append(f"- **Security**: {len(security)} finding(s)")
                for s in security:
                    lines.append(f"  - ⚠ {s}")

            gov_limit_warnings = self._check_governor_limits(code_snippet)
            if gov_limit_warnings:
                lines.append(f"- **Governor Limits**: {len(gov_limit_warnings)} warning(s)")
                for w in gov_limit_warnings:
                    lines.append(f"  - ⚡ {w}")

        elif language in ("lwc", "aura"):
            import_warnings = self._check_imports(code_snippet)
            if import_warnings:
                lines.append(f"- **Imports**: {len(import_warnings)} observation(s)")
                for w in import_warnings:
                    lines.append(f"  - {w}")

        best_practices = self._check_best_practices(code_snippet, language)
        if best_practices:
            lines.append(f"- **Best Practices**: {len(best_practices)} suggestion(s)")
            for bp in best_practices:
                lines.append(f"  - 💡 {bp}")

        if not any(self._check_apex, self._check_imports, self._check_best_practices):
            lines.append("\nNo specific issues detected in basic scan.")

        return "\n".join(lines)

    def _review_apex(self, code: str) -> list[str]:
        observations: list[str] = []
        lower = code.lower()

        if "system.debug" in lower:
            observations.append("Contains `System.debug` statements — remove before deployment")
        if "without sharing" in lower:
            observations.append("Declared `without sharing` — verify this is intentional")
        if "testmethod" in lower or "@istest" in lower:
            observations.append("Contains test methods")
        if "future" in lower:
            observations.append("Uses `@future` — consider Queueable for better error handling")
        if "schedule" in lower or "batch" in lower:
            observations.append("Contains scheduled/batch processing")
        if len(code) > 10000:
            observations.append(f"Class is large ({len(code)} chars) — consider splitting")
        if "hardisdelete" in lower or "delete" in code.lower():
            if "undelete" not in lower:
                pass
        return observations

    def _check_apex_security(self, code: str) -> list[str]:
        findings: list[str] = []
        lower = code.lower()

        soql_patterns = [
            ("SELECT", "SELECT"),
        ]
        has_soql = any(p[0].lower() in lower for p in soql_patterns)

        if has_soql and "with sharing" not in lower and "without sharing" not in lower:
            findings.append("SOQL queries found but class has no sharing declaration")
        if "database.query" in lower:
            findings.append("Uses dynamic SOQL (`Database.query`) — potential injection risk")
        if "sosl" in lower or "find" in lower and "[" in code:
            findings.append("Uses SOSL — verify search terms are sanitized")
        if "getcontent" in lower:
            findings.append("Uses `PageReference.getContent()` — potential for excessive resources")
        if "encodingutil" in lower:
            pass
        return findings

    def _check_governor_limits(self, code: str) -> list[str]:
        warnings: list[str] = []
        lower = code.lower()

        soql_count = lower.count("select ") - lower.count("selectoption")
        if soql_count > 5:
            warnings.append(f"{soql_count} SOQL queries detected — may approach 100 query limit in loops")

        loop_soql = self._detect_soql_in_loops(code)
        if loop_soql:
            warnings.append(f"SOQL inside loop detected (~{loop_soql}) — use collections")

        dml_count = lower.count("insert ") + lower.count("update ") + lower.count("delete ") + lower.count("upsert ")
        if dml_count > 3:
            warnings.append(f"{dml_count} DML operations — may approach 150 DML limit in loops")

        if "database.insert" in lower or "database.update" in lower:
            warnings.append("Uses partial DML — verify all-or-none behavior")
        return warnings

    def _detect_soql_in_loops(self, code: str) -> int:
        lines = code.split("\n")
        in_loop = False
        soql_in_loop = 0
        for line in lines:
            stripped = line.strip()
            if any(kw in stripped for kw in ["for (", "while (", "do {"]):
                in_loop = True
            if in_loop and ("[select " in stripped.lower() or "[find " in stripped.lower()):
                soql_in_loop += 1
            if stripped == "}" or stripped.startswith("}"):
                in_loop = False
        return soql_in_loop

    def _check_imports(self, code: str) -> list[str]:
        observations: list[str] = []
        lines = code.split("\n")
        import_count = sum(1 for l in lines if l.strip().startswith("import "))
        if import_count > 20:
            observations.append(f"Large number of imports ({import_count}) — consider selective imports")
        return observations

    def _check_best_practices(self, code: str, language: str) -> list[str]:
        suggestions: list[str] = []
        lower = code.lower()

        if language == "apex":
            if "trigger" in lower and len(code) > 2000:
                suggestions.append("Trigger logic should be delegated to a handler class")
            if "//" not in code:
                suggestions.append("Add inline comments for complex logic")
            if "test" in lower and "assert" not in lower:
                suggestions.append("Tests should include assertions")
        elif language in ("lwc", "aura"):
            if "onclick" in code.lower() or "onchange" in code.lower():
                suggestions.append("Use declarative event handlers instead of inline ones")
            if "innerhtml" in lower:
                suggestions.append("Avoid `innerHTML` — use templating instead")

        return suggestions


class SecurityReviewTool(AgentTool):
    @property
    def name(self) -> str:
        return "security_review"

    @property
    def description(self) -> str:
        return "Review Salesforce metadata for security concerns: CRUD/FLS, sharing, access"

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "component_type": {
                    "type": "string",
                    "description": "Metadata type (e.g. ApexClass, Profile, PermissionSet)",
                },
                "component_name": {
                    "type": "string",
                    "description": "API name of the component to review",
                },
                "code_snippet": {
                    "type": "string",
                    "description": "Optional code snippet for inline review",
                },
            },
            "required": [],
        }

    async def execute(
        self,
        component_type: str = "",
        component_name: str = "",
        code_snippet: str = "",
        request_context: RequestContext | None = None,
    ) -> str:
        _ = request_context
        findings: list[str] = []

        if code_snippet:
            findings.extend(self._review_code_security(code_snippet))

        if component_type == "ApexClass" and component_name:
            findings.append(f"- **{component_name}** — Review sharing declaration, CRUD/FLS enforcement")

        if component_type in ("Profile", "PermissionSet"):
            findings.append(f"- **{component_name}** — Review object permissions, field-level security")

        if not findings:
            return "No security concerns identified."

        lines = ["## Security Review", ""]
        for f in findings:
            lines.append(f)
        return "\n".join(lines)

    def _review_code_security(self, code: str) -> list[str]:
        findings: list[str] = []
        lower = code.lower()

        if "with sharing" not in lower and "without sharing" not in lower:
            findings.append("🔴 No sharing declaration — class runs in system context")
        if "without sharing" in lower:
            findings.append("🟡 `without sharing` — verify this is intentional")
        if "stripinaccessible" not in lower and ("select " in lower and " from " in lower):
            findings.append("🟡 SOQL without `stripInaccessible` — may expose hidden fields")

        crud_patterns = [
            ("isAccessible", "Object accessibility"),
            ("isCreateable", "Object create permission"),
            ("isUpdateable", "Object update permission"),
            ("isDeletable", "Object delete permission"),
            ("isAccessible()", "Field-level security"),
        ]
        for pattern, label in crud_patterns:
            if pattern not in lower:
                continue
            findings.append(f"Uses `{pattern}` — {label} enforced")

        return findings


class DependencyAnalysisTool(AgentTool):
    def __init__(self, dep_analyzer: DependencyAnalyzer) -> None:
        self._analyzer = dep_analyzer

    @property
    def name(self) -> str:
        return "dependency_analysis"

    @property
    def description(self) -> str:
        return "Comprehensive dependency analysis — field refs, cross-object, flow, apex, SOQL/SOSL, LWC imports, formula refs"

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "analysis_type": {
                    "type": "string",
                    "enum": [
                        "field_references", "cross_object", "flow_dependencies",
                        "apex_references", "soql_sosl", "lwc_imports",
                        "formula_references", "all_references",
                    ],
                    "description": "Type of dependency analysis to perform",
                },
                "object_name": {
                    "type": "string",
                    "description": "Object API name (for field/cross-object analysis)",
                },
                "field_name": {
                    "type": "string",
                    "description": "Field API name (for field reference analysis)",
                },
                "component_type": {
                    "type": "string",
                    "description": "Metadata component type (e.g. ApexClass, Flow, CustomObject)",
                },
                "component_name": {
                    "type": "string",
                    "description": "API name of the component to analyze",
                },
            },
            "required": ["analysis_type"],
        }

    async def execute(
        self,
        analysis_type: str = "",
        object_name: str = "",
        field_name: str = "",
        component_type: str = "",
        component_name: str = "",
        request_context: RequestContext | None = None,
    ) -> str:
        org_id = _organization_id_from_context(request_context)
        if org_id is None:
            return MISSING_REQUEST_CONTEXT_MESSAGE

        if analysis_type == "field_references" and object_name and field_name:
            refs = await self._analyzer.analyze_field_references(org_id, object_name, field_name)
            if not refs:
                return f"No references to `{object_name}.{field_name}` found."
            lines = [f"Field references to `{object_name}.{field_name}` ({len(refs)} total):"]
            for r in refs[:40]:
                lines.append(f"- {r['component_type']}: `{r['component_name']}` ({r['reference_type']})")
            return "\n".join(lines)

        if analysis_type == "cross_object" and object_name:
            result = await self._analyzer.analyze_cross_object_refs(org_id, object_name)
            if "error" in result:
                return result["error"]
            lines = [f"Cross-object references to `{object_name}` ({result['total_references']} total):"]
            for ctype, refs in result.get("references_by_type", {}).items():
                lines.append(f"\n{ctype} ({len(refs)}):")
                for r in refs[:15]:
                    lines.append(f"  - {r['name']} ({r['reference']})")
            return "\n".join(lines)

        if analysis_type == "soql_sosl" and component_name:
            refs = await self._analyzer.extract_soql_sosl(org_id, component_name)
            if not refs:
                return f"No SOQL/SOSL queries found in `{component_name}`."
            lines = [f"SOQL/SOSL in `{component_name}` ({len(refs)} total):"]
            for r in refs[:30]:
                lines.append(f"- {r['type']} → `{r['object']}` in {r['component']}")
            return "\n".join(lines)

        if analysis_type == "flow_dependencies" and component_name:
            result = await self._analyzer.analyze_flow_dependencies(org_id, component_name)
            if "error" in result:
                return result["error"]
            lines = [f"Flow dependencies for `{component_name}`:"]
            if result.get("objects_used"):
                lines.append(f"\nObjects used ({len(result['objects_used'])}): " + ", ".join(result["objects_used"][:10]))
            if result.get("subflows"):
                lines.append(f"\nSubflows: " + ", ".join(result["subflows"][:10]))
            if result.get("apex_actions"):
                lines.append(f"\nApex actions: " + ", ".join(result["apex_actions"][:10]))
            return "\n".join(lines)

        if analysis_type == "apex_references" and component_name:
            result = await self._analyzer.analyze_apex_references(org_id, component_name)
            if "error" in result:
                return result["error"]
            lines = [f"Apex references for `{component_name}`:"]
            if result.get("extends"):
                lines.append(f"\nExtends: " + ", ".join(result["extends"]))
            if result.get("implements"):
                lines.append(f"\nImplements: " + ", ".join(result["implements"]))
            if result.get("classes_used"):
                lines.append(f"\nClasses used: " + ", ".join(result["classes_used"][:15]))
            if result.get("objects_referenced"):
                lines.append(f"\nObjects: " + ", ".join(result["objects_referenced"][:15]))
            if result.get("used_by"):
                lines.append(f"\nUsed by ({len(result['used_by'])}): " + ", ".join(result["used_by"][:15]))
            return "\n".join(lines)

        if analysis_type == "lwc_imports" and component_name:
            refs = await self._analyzer.analyze_lwc_imports(org_id, component_name)
            if not refs:
                return f"No LWC imports found in `{component_name}`."
            lines = [f"LWC imports in `{component_name}` ({len(refs)}):"]
            for r in refs[:20]:
                lines.append(f"- {r['component']} imports {r['imports']} from {r['from']}")
            return "\n".join(lines)

        if analysis_type == "formula_references" and component_name:
            refs = await self._analyzer.analyze_formula_references(org_id, component_name)
            if not refs:
                return f"No formula references found for `{component_name}`."
            lines = [f"Formula references for `{component_name}` ({len(refs)}):"]
            for r in refs[:20]:
                ref_fields = ", ".join(r.get("referenced_fields", [])[:10])
                lines.append(f"- {r['formula_field']} references: {ref_fields}")
            return "\n".join(lines)

        if analysis_type == "all_references" and component_type and component_name:
            result = await self._analyzer.analyze_all_references(org_id, component_type, component_name)
            if "error" in result:
                return result["error"]
            lines = [f"All references for `{component_type}:{component_name}`:"]
            lines.append(f"\nUpstream ({result['upstream_count']}):")
            for d in result["upstream"][:15]:
                lines.append(f"  - {d['type']}:{d['name']}")
            lines.append(f"\nDownstream ({result['downstream_count']}):")
            for d in result["downstream"][:20]:
                lines.append(f"  - {d['type']}:{d['name']}")
            return "\n".join(lines)

        return ("Usage: dependency_analysis(analysis_type=...) with analysis_type in: "
                "field_references, cross_object, flow_dependencies, apex_references, "
                "soql_sosl, lwc_imports, formula_references, all_references")


class ImpactAssessmentTool(AgentTool):
    def __init__(self, impact_assessor: ImpactAssessor) -> None:
        self._assessor = impact_assessor

    @property
    def name(self) -> str:
        return "impact_assessment"

    @property
    def description(self) -> str:
        return "Analyze impact of changes — safe delete, rename impact, deployment risk, breaking change classification"

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "assessment_type": {
                    "type": "string",
                    "enum": ["delete_impact", "rename_impact", "deployment_risk", "breaking_changes"],
                    "description": "Type of impact assessment",
                },
                "component_type": {
                    "type": "string",
                    "description": "Metadata component type (e.g. ApexClass, Flow, CustomObject)",
                },
                "component_name": {
                    "type": "string",
                    "description": "API name of the component",
                },
                "new_name": {
                    "type": "string",
                    "description": "New name for rename assessment",
                },
                "components_json": {
                    "type": "string",
                    "description": "JSON array of {'type': ..., 'name': ..., 'change': 'modify|delete|rename'} for batch assessment",
                },
            },
            "required": ["assessment_type"],
        }

    async def execute(
        self,
        assessment_type: str = "",
        component_type: str = "",
        component_name: str = "",
        new_name: str = "",
        components_json: str = "",
        request_context: RequestContext | None = None,
    ) -> str:
        import json
        org_id = _organization_id_from_context(request_context)
        if org_id is None:
            return MISSING_REQUEST_CONTEXT_MESSAGE

        if assessment_type == "delete_impact" and component_type and component_name:
            result = await self._assessor.assess_delete_impact(org_id, component_type, component_name)
            if "error" in result:
                return result["error"]
            lines = [
                f"## Delete Impact Analysis: {component_type}:{component_name}",
                f"- **Risk Level**: {result['risk_level'].upper()}",
                f"- **Risk Score**: {result['risk_score']}",
                f"- **Downstream Dependents**: {result['downstream_count']}",
            ]
            if result.get("impacted_types_summary"):
                lines.append("- **Impacted Types**:")
                for t, c in sorted(result["impacted_types_summary"].items()):
                    lines.append(f"  - {t}: {c}")
            lines.append("")
            if result.get("recommendations"):
                lines.append("### Recommendations")
                for r in result["recommendations"]:
                    lines.append(f"- {r}")
            return "\n".join(lines)

        if assessment_type == "rename_impact" and component_type and component_name:
            result = await self._assessor.assess_rename_impact(org_id, component_type, component_name, new_name or None)
            if "error" in result:
                return result["error"]
            lines = [
                f"## Rename Impact: {component_type}:{component_name}",
                f"- **References to update**: {result['total_references_to_update']}",
                f"- **Risk Level**: {result['risk_level'].upper()}",
                f"- **Graph edges**: {result['graph_edges']}",
                f"- **Hardcoded refs**: {result['hardcoded_references']}",
            ]
            if result.get("breaking_references"):
                lines.append("\n### Breaking References")
                for r in result["breaking_references"][:20]:
                    lines.append(f"- {r['component']} ({r['action_required']})")
            if result.get("recommendations"):
                lines.append("\n### Recommendations")
                for r in result["recommendations"]:
                    lines.append(f"- {r}")
            return "\n".join(lines)

        if assessment_type == "deployment_risk" and components_json:
            try:
                components = json.loads(components_json)
            except json.JSONDecodeError:
                return "Invalid components_json — must be a JSON array"
            result = await self._assessor.assess_deployment_risk(org_id, components)
            if "error" in result:
                return result["error"]
            lines = [
                f"## Deployment Risk Assessment ({result['component_count']} components)",
                f"- **Risk Level**: {result['risk_level'].upper()}",
                f"- **Average Risk**: {result['average_risk_score']}",
                f"- **Has Cycles**: {result['has_cycles']}",
                f"- **Total Affected**: {result['total_affected_components']}",
            ]
            if result.get("suggested_deployment_order"):
                lines.append("\n### Suggested Deployment Order")
                for i, comp in enumerate(result["suggested_deployment_order"], 1):
                    lines.append(f"  {i}. {comp}")
            if result.get("recommendations"):
                lines.append("\n### Recommendations")
                for r in result["recommendations"]:
                    lines.append(f"- {r}")
            return "\n".join(lines)

        if assessment_type == "breaking_changes" and components_json:
            try:
                changes = json.loads(components_json)
            except json.JSONDecodeError:
                return "Invalid components_json — must be a JSON array"
            results = await self._assessor.classify_breaking_changes(org_id, changes)
            if not results:
                return "No changes to classify."
            lines = ["## Breaking Change Classification"]
            for r in results:
                icon = "🔴" if r["breaking"] else "🟢"
                lines.append(f"\n{icon} {r['component']} ({r['change_type']})")
                lines.append(f"   Severity: {r['severity']}")
                lines.append(f"   Reason: {r['reason']}")
            return "\n".join(lines)

        return ("Usage: impact_assessment(assessment_type=...) with type in: "
                "delete_impact, rename_impact, deployment_risk, breaking_changes")


class MetadataAnalysisTool(AgentTool):
    def __init__(self, meta_analyzer: MetadataAnalyzer) -> None:
        self._analyzer = meta_analyzer

    @property
    def name(self) -> str:
        return "metadata_analysis"

    @property
    def description(self) -> str:
        return "Deep analysis of Salesforce metadata — objects, fields, flows, apex, validation rules, profiles, layouts, reports"

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "analysis_type": {
                    "type": "string",
                    "enum": [
                        "analyze_object", "analyze_field", "analyze_flow",
                        "analyze_apex", "analyze_validation_rule", "analyze_profile",
                    ],
                    "description": "Type of metadata analysis",
                },
                "object_name": {
                    "type": "string",
                    "description": "Object API name",
                },
                "field_name": {
                    "type": "string",
                    "description": "Field API name",
                },
                "component_name": {
                    "type": "string",
                    "description": "Component API name (flow, apex class, validation rule, profile)",
                },
            },
            "required": ["analysis_type"],
        }

    async def execute(
        self,
        analysis_type: str = "",
        object_name: str = "",
        field_name: str = "",
        component_name: str = "",
        request_context: RequestContext | None = None,
    ) -> str:
        org_id = _organization_id_from_context(request_context)
        if org_id is None:
            return MISSING_REQUEST_CONTEXT_MESSAGE

        if analysis_type == "analyze_object" and object_name:
            result = await self._analyzer.analyze_object(org_id, object_name)
            if "error" in result:
                return result["error"]
            lines = [
                f"## Object: {object_name}",
                f"- **Label**: {result.get('label', '')}",
                f"- **Description**: {result.get('description', 'N/A')}",
                f"- **Fields (sample)**: {result.get('field_count', 0)}",
                f"- **APEX Triggers**: {result.get('has_apex_triggers', False)}",
                f"- **Validation Rules**: {result.get('validation_rule_count', 0)}",
                f"- **Layouts**: {result.get('layout_count', 0)}",
            ]
            return "\n".join(lines)

        if analysis_type == "analyze_field" and object_name and field_name:
            result = await self._analyzer.analyze_field(org_id, object_name, field_name)
            if "error" in result:
                return result["error"]
            lines = [
                f"## Field: {object_name}.{field_name}",
                f"- **Type**: {result.get('field_type', 'unknown')}",
                f"- **Required**: {result.get('is_required', False)}",
                f"- **Unique**: {result.get('is_unique', False)}",
            ]
            if result.get("picklist_values"):
                lines.append(f"- **Picklist**: {', '.join(result['picklist_values'][:15])}")
            if result.get("referenced_by"):
                lines.append(f"- **Referenced by**: {len(result['referenced_by'])} component(s)")
                for r in result["referenced_by"][:10]:
                    lines.append(f"  - {r['component']}")
            return "\n".join(lines)

        if analysis_type == "analyze_flow" and component_name:
            result = await self._analyzer.analyze_flow(org_id, component_name)
            if "error" in result:
                return result["error"]
            lines = [
                f"## Flow: {component_name}",
                f"- **Label**: {result.get('label', '')}",
                f"- **Trigger**: {result.get('trigger_type', 'unknown')}",
                f"- **Active**: {result.get('is_active', False)}",
                f"- **Elements**: {result.get('elements_estimated', 0)}",
                f"- **Decisions**: {result.get('decisions_estimated', 0)}",
                f"- **Record Creates**: {result.get('record_creates', 0)}",
                f"- **Record Updates**: {result.get('record_updates', 0)}",
            ]
            if result.get("objects_used"):
                lines.append(f"- **Objects**: {', '.join(result['objects_used'][:10])}")
            if result.get("subflows"):
                lines.append(f"- **Subflows**: {', '.join(result['subflows'][:10])}")
            return "\n".join(lines)

        if analysis_type == "analyze_apex" and component_name:
            result = await self._analyzer.analyze_apex_class(org_id, component_name)
            if "error" in result:
                return result["error"]
            lines = [
                f"## Apex Class: {component_name}",
                f"- **Type**: {result.get('type', 'ApexClass')}",
                f"- **Lines**: {result.get('line_count', 0)}",
                f"- **Methods**: {result.get('method_count', 0)}",
            ]
            if result.get("methods"):
                lines.append(f"- **Method list**: {', '.join(result['methods'][:20])}")
            if result.get("extends"):
                lines.append(f"- **Extends**: {', '.join(result['extends'])}")
            if result.get("implements"):
                lines.append(f"- **Implements**: {', '.join(result['implements'])}")
            if result.get("objects_referenced"):
                lines.append(f"- **Objects**: {', '.join(result['objects_referenced'][:10])}")
            return "\n".join(lines)

        if analysis_type == "analyze_validation_rule" and component_name:
            result = await self._analyzer.analyze_validation_rule(org_id, component_name)
            if "error" in result:
                return result["error"]
            lines = [
                f"## Validation Rule: {component_name}",
                f"- **Formula length**: {result.get('formula_length', 0)} chars",
            ]
            if result.get("field_references"):
                lines.append(f"- **Fields referenced**: {', '.join(result['field_references'][:20])}")
            if result.get("formula_body"):
                lines.append(f"\n**Formula**:\n```\n{result['formula_body'][:1000]}\n```")
            return "\n".join(lines)

        if analysis_type == "analyze_profile" and component_name:
            result = await self._analyzer.analyze_profile(org_id, component_name)
            if "error" in result:
                return result["error"]
            lines = [
                f"## Profile/Permission Set: {component_name}",
                f"- **Type**: {result.get('type', 'Profile')}",
            ]
            if result.get("permissions_granted"):
                lines.append(f"- **Permissions ({len(result['permissions_granted'])}):")
                for p in result["permissions_granted"][:30]:
                    lines.append(f"  - {p}")
            return "\n".join(lines)

        return ("Usage: metadata_analysis(analysis_type=...) with type in: "
                "analyze_object, analyze_field, analyze_flow, analyze_apex, "
                "analyze_validation_rule, analyze_profile")


class CodeIntelligenceTool(AgentTool):
    def __init__(self, code_engine: CodeIntelligenceEngine) -> None:
        self._engine = code_engine

    @property
    def name(self) -> str:
        return "code_intelligence"

    @property
    def description(self) -> str:
        return "Advanced code analysis — Apex structure, SOQL optimization, governor limits, security, flow logic, LWC analysis"

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "analysis_type": {
                    "type": "string",
                    "enum": [
                        "analyze_apex", "soql_optimization", "governor_limits",
                        "flow_logic", "analyze_lwc",
                    ],
                    "description": "Type of code intelligence analysis",
                },
                "code": {
                    "type": "string",
                    "description": "Source code to analyze",
                },
                "html_code": {
                    "type": "string",
                    "description": "HTML template (for LWC analysis)",
                },
                "component_name": {
                    "type": "string",
                    "description": "Component name for flow analysis",
                },
            },
            "required": ["analysis_type"],
        }

    async def execute(
        self,
        analysis_type: str = "",
        code: str = "",
        html_code: str = "",
        component_name: str = "",
        request_context: RequestContext | None = None,
    ) -> str:
        _ = request_context
        if analysis_type == "analyze_apex" and code:
            result = self._engine.analyze_apex(code)
            if "error" in result:
                return result["error"]
            lines = [
                f"## Apex Analysis",
                f"- **Lines**: {result['total_lines']}, **Chars**: {result['total_chars']}",
                f"- **Classes**: {len(result['classes'])}",
                f"- **Methods**: {len(result['methods']['all'])}",
                f"- **Sharing**: {result['sharing_declaration']}",
                f"- **SOQL**: {len(result['soql_queries'])}",
                f"- **DML**: {len(result['dml_operations'])}",
                f"- **Complexity**: {result['complexity_score']['level']} ({result['complexity_score']['score']})",
            ]
            if result.get("security_findings"):
                lines.append("\n### Security")
                for f in result["security_findings"][:10]:
                    lines.append(f"- [{f['severity']}] {f['finding']}")
            if result.get("governor_limit_concerns"):
                lines.append("\n### Governor Limits")
                for g in result["governor_limit_concerns"][:10]:
                    lines.append(f"- [{g['severity']}] {g['finding']}")
            if result.get("best_practices"):
                lines.append("\n### Best Practices")
                for b in result["best_practices"][:10]:
                    lines.append(f"- {b['finding']}")
            return "\n".join(lines)

        if analysis_type == "soql_optimization" and code:
            findings = self._engine.analyze_soql_optimization(code)
            if not findings:
                return "No SOQL optimization findings."
            lines = ["## SOQL Optimization"]
            for f in findings:
                lines.append(f"\n**Query**: `{f.get('query', '')[:100]}...`")
                if f.get("issues"):
                    for issue in f["issues"]:
                        lines.append(f"- {issue}")
            return "\n".join(lines)

        if analysis_type == "governor_limits" and code:
            result = self._engine.estimate_governor_usage(code)
            if "error" in result:
                return result["error"]
            lines = [
                "## Governor Limit Estimation",
                f"- **SOQL**: {result['soql_queries']} / 100",
                f"- **SOSL**: {result['sosl_queries']} / 20",
                f"- **DML**: {result['dml_statements']} / 150",
                f"- **In Loops**: {result['in_loops_count']}",
                f"- **Heap Allocations**: {result['heap_allocations']}",
            ]
            if result.get("concerns"):
                for c in result["concerns"]:
                    lines.append(f"- ⚡ {c}")
            return "\n".join(lines)

        if analysis_type == "flow_logic" and component_name:
            result = self._engine.analyze_flow_logic({"elements": []})
            lines = [
                f"## Flow Logic Analysis: {component_name}",
                f"- **Elements**: {result['total_elements']}",
                f"- **Decisions**: {result['decision_count']}",
                f"- **Loops**: {result['loop_count']}",
                f"- **Subflows**: {result['subflow_count']}",
            ]
            return "\n".join(lines)

        if analysis_type == "analyze_lwc" and code:
            result = self._engine.analyze_lwc(code, html_code)
            if "error" in result:
                return result["error"]
            lines = ["## LWC Analysis"]
            if "js" in result:
                js = result["js"]
                lines.append(f"\n**JavaScript**: {js.get('line_count', 0)} lines")
                lines.append(f"- **@api**: {len(js.get('api_properties', []))}")
                lines.append(f"- **@track**: {len(js.get('tracked_properties', []))}")
                lines.append(f"- **@wire**: {js.get('wire_adapters', [])}")
                if js.get("lifecycle_hooks"):
                    hooks = [k for k, v in js["lifecycle_hooks"].items() if v]
                    if hooks:
                        lines.append(f"- **Lifecycle**: {', '.join(hooks)}")
            if "html" in result:
                html = result["html"]
                lines.append(f"\n**HTML**: {html.get('line_count', 0)} lines")
                if html.get("child_components"):
                    lines.append(f"- **Children**: {', '.join(html['child_components'][:10])}")
                if html.get("conditionals"):
                    conds = {k: v for k, v in html["conditionals"].items() if v > 0}
                    if conds:
                        lines.append(f"- **Conditionals**: {conds}")
            return "\n".join(lines)

        return ("Usage: code_intelligence(analysis_type=...) with type in: "
                "analyze_apex, soql_optimization, governor_limits, flow_logic, analyze_lwc")


class DocumentationGenerationTool(AgentTool):
    def __init__(self, doc_generator: DocumentationGenerator) -> None:
        self._generator = doc_generator

    @property
    def name(self) -> str:
        return "documentation_generation"

    @property
    def description(self) -> str:
        return "Generate documentation for Salesforce components — component docs, architecture overview, field docs, API docs"

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "doc_type": {
                    "type": "string",
                    "enum": ["component", "architecture", "field", "api"],
                    "description": "Type of documentation to generate",
                },
                "component_type": {
                    "type": "string",
                    "description": "Metadata type (e.g. CustomObject, ApexClass, Flow)",
                },
                "component_name": {
                    "type": "string",
                    "description": "API name of the component",
                },
                "object_name": {
                    "type": "string",
                    "description": "Object API name (for field documentation)",
                },
                "field_name": {
                    "type": "string",
                    "description": "Field API name (for field documentation)",
                },
            },
            "required": ["doc_type"],
        }

    async def execute(
        self,
        doc_type: str = "",
        component_type: str = "",
        component_name: str = "",
        object_name: str = "",
        field_name: str = "",
        request_context: RequestContext | None = None,
    ) -> str:
        org_id = _organization_id_from_context(request_context)
        if org_id is None:
            return MISSING_REQUEST_CONTEXT_MESSAGE

        if doc_type == "component" and component_type and component_name:
            result = await self._generator.generate_component_documentation(
                org_id, component_type, component_name,
            )
            if "error" in result:
                return result.get("documentation", result["error"])
            return result.get("documentation", "Documentation generated.")

        if doc_type == "architecture":
            result = await self._generator.generate_architecture_documentation(org_id)
            return result.get("documentation", "Architecture overview generated.")

        if doc_type == "field" and object_name and field_name:
            result = await self._generator.generate_field_documentation(
                org_id, object_name, field_name,
            )
            return result.get("documentation", "Field documentation generated.")

        if doc_type == "api" and component_name:
            result = await self._generator.generate_api_documentation(org_id, component_name)
            return result.get("documentation", "API documentation generated.")

        return ("Usage: documentation_generation(doc_type=...) with type in: "
                "component, architecture, field, api")


class SafeDeleteTool(AgentTool):
    def __init__(self, impact_assessor: ImpactAssessor) -> None:
        self._assessor = impact_assessor

    @property
    def name(self) -> str:
        return "safe_delete"

    @property
    def description(self) -> str:
        return "Determine if a Salesforce component can be safely deleted without breaking dependencies"

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "component_type": {
                    "type": "string",
                    "description": "Metadata type (e.g. CustomField, ApexClass, Flow, CustomObject)",
                },
                "component_name": {
                    "type": "string",
                    "description": "API name of the component to check for safe deletion",
                },
            },
            "required": ["component_type", "component_name"],
        }

    async def execute(
        self,
        component_type: str,
        component_name: str,
        request_context: RequestContext | None = None,
    ) -> str:
        org_id = _organization_id_from_context(request_context)
        if org_id is None:
            return MISSING_REQUEST_CONTEXT_MESSAGE
        result = await self._assessor.assess_delete_impact(org_id, component_type, component_name)
        if "error" in result:
            return result["error"]

        safe = result.get("delete_possible", False)
        risk = result.get("risk_level", "unknown")
        downstream = result.get("downstream_count", 0)

        if safe:
            return (
                f"✅ **{component_type}:{component_name}** can be safely deleted.\n"
                f"- Risk: {risk}\n"
                f"- No downstream dependents found.\n"
                f"{chr(10).join('- ' + r for r in result.get('recommendations', []))}"
            )
        else:
            impacted = result.get("impacted_types_summary", {})
            impact_lines = "\n".join(f"  - {t}: {c}" for t, c in impacted.items())
            return (
                f"❌ **{component_type}:{component_name}** may NOT be safe to delete.\n"
                f"- Risk: {risk.upper()}\n"
                f"- Downstream dependents: {downstream}\n"
                f"- Impacted types:\n{impact_lines}\n"
                f"\n{chr(10).join('- ' + r for r in result.get('recommendations', []))}"
            )


class DeploymentRiskTool(AgentTool):
    def __init__(self, impact_assessor: ImpactAssessor) -> None:
        self._assessor = impact_assessor

    @property
    def name(self) -> str:
        return "deployment_risk"

    @property
    def description(self) -> str:
        return "Assess deployment risk for a set of components — risk scoring, deployment order, breaking changes"

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "components_json": {
                    "type": "string",
                    "description": "JSON array of {'type': ..., 'name': ..., 'change': 'modify|delete|rename'}",
                },
            },
            "required": ["components_json"],
        }

    async def execute(
        self,
        components_json: str,
        request_context: RequestContext | None = None,
    ) -> str:
        import json
        org_id = _organization_id_from_context(request_context)
        if org_id is None:
            return MISSING_REQUEST_CONTEXT_MESSAGE

        try:
            components = json.loads(components_json)
        except json.JSONDecodeError:
            return "Invalid JSON. Provide a JSON array of components."

        if not isinstance(components, list):
            return "components_json must be a JSON array."

        result = await self._assessor.assess_deployment_risk(org_id, components)

        if "error" in result:
            return result["error"]

        changes = await self._assessor.classify_breaking_changes(org_id, components)

        lines = [
            f"## Deployment Risk Assessment",
            f"- **Risk Level**: {result['risk_level'].upper()}",
            f"- **Average Risk Score**: {result['average_risk_score']}",
            f"- **Components**: {result['component_count']}",
            f"- **Total Affected**: {result['total_affected_components']}",
            f"- **Has Cycles**: {result['has_cycles']}",
            "",
        ]

        if changes:
            lines.append("### Breaking Change Classification")
            for c in changes:
                icon = "🔴" if c["breaking"] else "🟢"
                lines.append(f"{icon} {c['component']} — {c['severity']}")
            lines.append("")

        if result.get("suggested_deployment_order"):
            lines.append("### Suggested Deployment Order")
            for i, comp in enumerate(result["suggested_deployment_order"], 1):
                lines.append(f"  {i}. {comp}")
            lines.append("")

        if result.get("recommendations"):
            lines.append("### Recommendations")
            for r in result["recommendations"]:
                lines.append(f"- {r}")

        return "\n".join(lines)
