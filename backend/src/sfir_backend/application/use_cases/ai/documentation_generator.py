from __future__ import annotations

import uuid
from typing import Any

import structlog

from sfir_backend.application.use_cases.ai.dependency_analyzer import (
    DependencyAnalyzer,
)
from sfir_backend.application.use_cases.ai.metadata_analyzer import MetadataAnalyzer
from sfir_backend.application.use_cases.graph.service import GraphService

logger = structlog.get_logger(__name__)


class DocumentationGenerator:
    def __init__(
        self,
        graph_service: GraphService,
        metadata_analyzer: MetadataAnalyzer,
        dependency_analyzer: DependencyAnalyzer,
    ) -> None:
        self._graph_service = graph_service
        self._metadata_analyzer = metadata_analyzer
        self._dependency_analyzer = dependency_analyzer

    async def generate_component_documentation(
        self,
        organization_id: uuid.UUID,
        component_type: str,
        component_name: str,
    ) -> dict[str, Any]:
        meta = await self._metadata_analyzer.analyze_object(
            organization_id, component_name,
        ) if component_type in ("CustomObject", "object") else {}

        if component_type in ("CustomObject", "object"):
            meta = await self._metadata_analyzer.analyze_object(
                organization_id, component_name,
            )
        elif component_type in ("ApexClass", "ApexTrigger", "apex_class", "trigger"):
            meta = await self._metadata_analyzer.analyze_apex_class(
                organization_id, component_name,
            )
        elif component_type in ("Flow", "flow"):
            meta = await self._metadata_analyzer.analyze_flow(
                organization_id, component_name,
            )
        elif component_type in ("ValidationRule", "validation_rule"):
            meta = await self._metadata_analyzer.analyze_validation_rule(
                organization_id, component_name,
            )
        elif component_type in ("Profile", "PermissionSet", "profile", "permission_set"):
            meta = await self._metadata_analyzer.analyze_profile(
                organization_id, component_name,
            )
        elif component_type in ("Report", "report"):
            meta = await self._metadata_analyzer.analyze_report(
                organization_id, component_name,
            )
        elif component_type in ("Layout", "layout"):
            meta = await self._metadata_analyzer.analyze_layout(
                organization_id, component_name,
            )

        deps = await self._dependency_analyzer.analyze_all_references(
            organization_id, component_type, component_name,
        )

        components = [
            {"type": d["type"], "name": d["name"]}
            for d in deps.get("downstream", [])[:20]
        ]

        markdown = self._build_component_markdown(
            component_type, component_name, meta, deps,
        )

        return {
            "component_type": component_type,
            "component_name": component_name,
            "metadata": meta,
            "dependencies": deps,
            "affected_components": components,
            "documentation": markdown,
            "sections": ["overview", "dependencies", "dependents", "recommendations"],
        }

    async def generate_architecture_documentation(
        self,
        organization_id: uuid.UUID,
    ) -> dict[str, Any]:
        graph = await self._graph_service.build_graph(organization_id)
        if not graph:
            return {"error": "Graph not available"}

        summary = await self._graph_service.graph_summary(graph)
        cycles = await self._graph_service.find_cycles(graph)

        overview = self._build_architecture_overview(summary, cycles)
        return {
            "total_components": summary["node_count"],
            "total_edges": summary["edge_count"],
            "component_types": summary["component_types"],
            "cycle_count": summary["cycles"],
            "cycles": cycles,
            "documentation": overview,
        }

    async def generate_field_documentation(
        self,
        organization_id: uuid.UUID,
        object_name: str,
        field_name: str,
    ) -> dict[str, Any]:
        field_analysis = await self._metadata_analyzer.analyze_field(
            organization_id, object_name, field_name,
        )
        refs = await self._dependency_analyzer.analyze_field_references(
            organization_id, object_name, field_name,
        )

        markdown = self._build_field_markdown(object_name, field_name, field_analysis, refs)

        return {
            "field": f"{object_name}.{field_name}",
            "type": field_analysis.get("field_type", "unknown"),
            "required": field_analysis.get("is_required", False),
            "reference_count": len(refs),
            "references": refs[:30],
            "documentation": markdown,
        }

    async def generate_api_documentation(
        self,
        organization_id: uuid.UUID,
        class_name: str,
    ) -> dict[str, Any]:
        meta = await self._metadata_analyzer.analyze_apex_class(
            organization_id, class_name,
        )
        soql_refs = await self._dependency_analyzer.extract_soql_sosl(
            organization_id, class_name,
        )

        markdown = self._build_api_markdown(class_name, meta, soql_refs)

        return {
            "class_name": class_name,
            "type": meta.get("type", "ApexClass"),
            "methods": meta.get("methods", []),
            "soql_queries": soql_refs,
            "dependencies": {
                "extends": meta.get("extends", []),
                "implements": meta.get("implements", []),
                "classes_used": meta.get("classes_used", []),
                "objects_referenced": meta.get("objects_referenced", []),
                "used_by": meta.get("used_by", []),
            },
            "documentation": markdown,
        }

    def _build_component_markdown(
        self,
        component_type: str,
        component_name: str,
        meta: dict[str, Any],
        deps: dict[str, Any],
    ) -> str:
        lines: list[str] = [
            f"# {component_type}: {component_name}",
            "",
        ]

        if meta.get("description"):
            lines.append(f"{meta['description']}")
            lines.append("")

        if isinstance(meta, dict) and "error" not in meta:
            lines.append("## Overview")
            if "field_count" in meta and meta["field_count"] is not None:
                lines.append(f"- **Fields**: {meta['field_count']}")
            if "method_count" in meta:
                lines.append(f"- **Methods**: {meta['method_count']}")
            if "line_count" in meta:
                lines.append(f"- **Lines**: {meta['line_count']}")
            if meta.get("is_active") is not None:
                lines.append(f"- **Active**: {meta['is_active']}")
            lines.append("")

        lines.append("## Dependencies")
        upstream = deps.get("upstream", [])
        if upstream:
            for dep in upstream[:15]:
                lines.append(f"- `{dep['type']}:{dep['name']}`")
        else:
            lines.append("No upstream dependencies.")
        lines.append("")

        lines.append("## Used By (Dependents)")
        downstream = deps.get("downstream", [])
        if downstream:
            for dep in downstream[:20]:
                lines.append(f"- `{dep['type']}:{dep['name']}`")
            if len(downstream) > 20:
                lines.append(f"- *... and {len(downstream) - 20} more*")
        else:
            lines.append("No downstream dependents.")

        return "\n".join(lines)

    def _build_field_markdown(
        self,
        object_name: str,
        field_name: str,
        analysis: dict[str, Any],
        refs: list[dict[str, Any]],
    ) -> str:
        lines: list[str] = [
            f"# Field: {object_name}.{field_name}",
            "",
            f"- **Type**: {analysis.get('field_type', 'unknown')}",
            f"- **Required**: {analysis.get('is_required', False)}",
            f"- **Unique**: {analysis.get('is_unique', False)}",
            "",
        ]

        picklist = analysis.get("picklist_values", [])
        if picklist:
            lines.append("### Picklist Values")
            for v in picklist[:15]:
                label = v if isinstance(v, str) else v.get("label", v.get("value", str(v)))
                lines.append(f"- {label}")
            if len(picklist) > 15:
                lines.append(f"- *... and {len(picklist) - 15} more*")
            lines.append("")

        lines.append("## References")
        if refs:
            for ref in refs[:30]:
                lines.append(
                    f"- `{ref['component_type']}:{ref['component_name']}` "
                    f"({ref.get('reference_type', 'reference')})"
                )
        else:
            lines.append("No references found in the codebase.")

        return "\n".join(lines)

    def _build_api_markdown(
        self,
        class_name: str,
        meta: dict[str, Any],
        soql_refs: list[dict[str, Any]],
    ) -> str:
        lines: list[str] = [
            f"# Apex Class: {class_name}",
            "",
        ]

        if meta.get("description"):
            lines.append(f"{meta['description']}")
            lines.append("")

        lines.append("## Structure")
        lines.append(f"- **Type**: {meta.get('type', 'ApexClass')}")
        lines.append(f"- **Lines**: {meta.get('line_count', 0)}")
        lines.append(f"- **Methods**: {meta.get('method_count', 0)}")
        lines.append("")

        methods = meta.get("methods", [])
        if methods:
            lines.append("### Methods")
            for m in methods[:30]:
                lines.append(f"- `{m}()`")
            lines.append("")

        if meta.get("extends"):
            lines.append(f"**Extends**: {', '.join(meta['extends'])}")
        if meta.get("implements"):
            lines.append(f"**Implements**: {', '.join(meta['implements'])}")
        if meta.get("classes_used"):
            lines.append(f"**Uses classes**: {', '.join(meta['classes_used'][:15])}")
        lines.append("")

        if soql_refs:
            lines.append("## SOQL/SOSL Queries")
            for q in soql_refs[:10]:
                lines.append(f"- `{q.get('object', '?')}` — {q.get('type', 'SOQL')}")
            if len(soql_refs) > 10:
                lines.append(f"- *... and {len(soql_refs) - 10} more*")
            lines.append("")

        if meta.get("used_by"):
            lines.append("## Used By")
            for ref in meta["used_by"][:10]:
                lines.append(f"- `{ref}`")
            lines.append("")

        return "\n".join(lines)

    def _build_architecture_overview(
        self,
        summary: dict[str, Any],
        cycles: list[list[str]],
    ) -> str:
        lines: list[str] = [
            "# Architecture Overview",
            "",
            f"- **Total Components**: {summary['node_count']}",
            f"- **Total Dependencies**: {summary['edge_count']}",
            f"- **Circular Dependencies**: {summary['cycles']}",
            "",
        ]

        lines.append("## Component Distribution")
        for ctype, count in sorted(summary.get("component_types", {}).items()):
            lines.append(f"- {ctype}: {count}")
        lines.append("")

        if cycles:
            lines.append("## Circular Dependencies")
            for cycle in cycles[:10]:
                path = " → ".join(cycle[:8])
                if len(cycle) > 8:
                    path += " → ..."
                lines.append(f"- {path}")
            lines.append("")

        lines.append("## Recommendations")
        if summary["cycles"] > 0:
            lines.append("- Resolve circular dependencies for cleaner architecture.")
        if summary["node_count"] > 100:
            lines.append("- Consider modularizing the org structure.")
        lines.append("- Document key integration points for maintainability.")
        lines.append("- Review orphaned components for potential cleanup.")

        return "\n".join(lines)
