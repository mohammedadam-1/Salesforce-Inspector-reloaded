from __future__ import annotations

import uuid
from typing import Any

import structlog

from sfir_backend.application.use_cases.graph.service import GraphService

logger = structlog.get_logger(__name__)


class ImpactAssessor:
    def __init__(self, graph_service: GraphService) -> None:
        self._graph_service = graph_service

    async def assess_delete_impact(
        self,
        organization_id: uuid.UUID,
        component_type: str,
        component_name: str,
    ) -> dict[str, Any]:
        graph = await self._graph_service.build_graph(organization_id)
        if not graph:
            return {"error": "Graph not available"}

        node_key = f"{component_type}:{component_name}"
        node = graph.get_node(node_key)
        if not node:
            return {"error": f"Component '{component_type}:{component_name}' not found"}

        downstream = graph.get_downstream(node_key, 5)
        upstream = graph.get_upstream(node_key, 1)

        incoming_edges = graph.get_incoming_edges(node_key)
        outgoing_edges = graph.get_outgoing_edges(node_key)

        impact_score = min(1.0, len(downstream) / 20)
        can_delete_safely = len(downstream) == 0
        has_dependents = len(downstream) > 0

        impacted_types: dict[str, int] = {}
        for dep_node in downstream:
            ntype = dep_node.node_type.value
            impacted_types[ntype] = impacted_types.get(ntype, 0) + 1

        risk_level: str
        if len(downstream) == 0:
            risk_level = "none"
        elif len(downstream) <= 3:
            risk_level = "low"
        elif len(downstream) <= 10:
            risk_level = "medium"
        else:
            risk_level = "high"

        recommendations: list[str] = []
        if can_delete_safely:
            recommendations.append(f"Safe to delete '{component_name}' — no downstream dependents.")
        else:
            recommendations.append(
                f"Unsafe to delete — {len(downstream)} component(s) depend on it."
            )
            recommendations.append("Review and update all dependent components before deletion.")
        if impacted_types.get("flow", 0) > 0:
            recommendations.append(
                f"Review {impacted_types['flow']} flow(s) that reference this component."
            )
        if impacted_types.get("apex_class", 0) > 0:
            recommendations.append(
                f"Update {impacted_types['apex_class']} Apex class(es) with hard references."
            )
        if impacted_types.get("profile", 0) > 0 or impacted_types.get("permission_set", 0) > 0:
            recommendations.append("Check permission assignments that may break.")

        return {
            "component": f"{component_type}:{component_name}",
            "delete_possible": can_delete_safely,
            "risk_level": risk_level,
            "risk_score": round(impact_score, 3),
            "downstream_count": len(downstream),
            "upstream_count": len(upstream),
            "incoming_edges": len(incoming_edges),
            "outgoing_edges": len(outgoing_edges),
            "impacted_components": [
                {"type": n.node_type.value, "name": n.api_name}
                for n in downstream[:100]
            ],
            "impacted_types_summary": impacted_types,
            "recommendations": recommendations,
        }

    async def assess_rename_impact(
        self,
        organization_id: uuid.UUID,
        component_type: str,
        component_name: str,
        new_name: str | None = None,
    ) -> dict[str, Any]:
        graph = await self._graph_service.build_graph(organization_id)
        if not graph:
            return {"error": "Graph not available"}

        node_key = f"{component_type}:{component_name}"
        node = graph.get_node(node_key)
        if not node:
            return {"error": f"Component '{component_type}:{component_name}' not found"}

        upstream = graph.get_upstream(node_key, 1)
        downstream = graph.get_downstream(node_key, 3)

        incoming_edges = graph.get_incoming_edges(node_key)

        breaking_refs: list[dict[str, str]] = []
        for edge in incoming_edges:
            source_node = graph.get_node(edge.source_id)
            if source_node:
                breaking_refs.append({
                    "component": f"{source_node.node_type.value}:{source_node.api_name}",
                    "edge_type": edge.edge_type.value,
                    "action_required": "Update reference to new name" if new_name else "Review reference",
                })

        referenced_by_code: list[dict[str, str]] = []
        component_name_lower = component_name.lower()
        for other_key, other_node in graph.nodes.items():
            if other_key == node_key:
                continue
            body = self._get_node_body(other_node)
            if body and component_name_lower in body.lower():
                referenced_by_code.append({
                    "component": f"{other_node.node_type.value}:{other_node.api_name}",
                    "match_type": "hardcoded_reference",
                })

        risk_level: str
        total_refs = len(breaking_refs) + len(referenced_by_code)
        if total_refs == 0:
            risk_level = "none"
        elif total_refs <= 5:
            risk_level = "low"
        elif total_refs <= 20:
            risk_level = "medium"
        else:
            risk_level = "high"

        return {
            "component": f"{component_type}:{component_name}",
            "new_name": new_name,
            "total_references_to_update": total_refs,
            "risk_level": risk_level,
            "graph_edges": len(breaking_refs),
            "hardcoded_references": len(referenced_by_code),
            "breaking_references": breaking_refs[:50],
            "hardcoded_references_detail": referenced_by_code[:50],
            "downstream_dependents": [
                f"{n.node_type.value}:{n.api_name}" for n in downstream[:30]
            ],
            "recommendations": self._rename_recommendations(
                total_refs, breaking_refs, referenced_by_code, component_name, new_name,
            ),
        }

    async def assess_deployment_risk(
        self,
        organization_id: uuid.UUID,
        components: list[dict[str, str]],
    ) -> dict[str, Any]:
        graph = await self._graph_service.build_graph(organization_id)
        if not graph:
            return {"error": "Graph not available"}

        total_risk_score = 0.0
        component_risks: list[dict[str, Any]] = []
        all_affected: dict[str, int] = {}
        has_cycles = bool(graph.find_cycles())

        for comp in components:
            ctype = comp.get("type", "")
            cname = comp.get("name", "")
            impact = await self.assess_delete_impact(organization_id, ctype, cname)
            risk = impact.get("risk_score", 0)
            total_risk_score += risk
            component_risks.append({
                "component": f"{ctype}:{cname}",
                "risk_score": risk,
                "downstream_count": impact.get("downstream_count", 0),
            })
            for itype, count in impact.get("impacted_types_summary", {}).items():
                all_affected[itype] = all_affected.get(itype, 0) + count

        total_comp = len(components) if components else 1
        avg_risk = total_risk_score / total_comp

        risk_level: str
        if avg_risk < 0.1:
            risk_level = "low"
        elif avg_risk < 0.4:
            risk_level = "medium"
        else:
            risk_level = "high"

        order: list[str] = []
        if components:
            ordered = await self._estimate_deployment_order(organization_id, components)
            order = ordered

        return {
            "component_count": len(components),
            "average_risk_score": round(avg_risk, 3),
            "risk_level": risk_level,
            "has_cycles": has_cycles,
            "total_affected_components": sum(all_affected.values()),
            "affected_by_type": all_affected,
            "component_risks": sorted(component_risks, key=lambda x: -x["risk_score"]),
            "suggested_deployment_order": order,
            "recommendations": self._deployment_recommendations(
                risk_level, has_cycles, total_comp, all_affected,
            ),
        }

    async def _estimate_deployment_order(
        self,
        organization_id: uuid.UUID,
        components: list[dict[str, str]],
    ) -> list[str]:
        graph = await self._graph_service.build_graph(organization_id)
        if not graph:
            return [f"{c['type']}:{c['name']}" for c in components]

        in_degree: dict[str, int] = {}
        dep_map: dict[str, list[str]] = {}

        for comp in components:
            key = f"{comp['type']}:{comp['name']}"
            if key not in in_degree:
                in_degree[key] = 0
            if key not in dep_map:
                dep_map[key] = []

        for comp in components:
            key = f"{comp['type']}:{comp['name']}"
            upstream = graph.get_upstream(key, 1)
            for up_node in upstream:
                up_key = f"{up_node.node_type.value}:{up_node.api_name}"
                if up_key in in_degree:
                    in_degree[key] = in_degree.get(key, 0) + 1
                    dep_map.setdefault(up_key, []).append(key)

        queue: list[str] = [k for k, v in in_degree.items() if v == 0]
        result: list[str] = []

        while queue:
            node = queue.pop(0)
            result.append(node)
            for dependent in dep_map.get(node, []):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        remaining = [k for k in in_degree if k not in result]
        result.extend(remaining)
        return result

    async def classify_breaking_changes(
        self,
        organization_id: uuid.UUID,
        changes: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for change in changes:
            ctype = change.get("type", "")
            cname = change.get("name", "")
            change_type = change.get("change", "modify")

            impact = await self.assess_delete_impact(organization_id, ctype, cname)
            downstream_count = impact.get("downstream_count", 0)

            breaking: bool
            severity: str
            reason: str

            if change_type == "delete":
                breaking = downstream_count > 0
                severity = "breaking" if breaking else "non-breaking"
                reason = (
                    f"Component is referenced by {downstream_count} other component(s)"
                    if breaking
                    else "No downstream dependents — safe to delete"
                )
            elif change_type == "rename":
                breaking = True
                severity = "breaking"
                reason = "All references to the old name must be updated"
            elif change_type in ("modify", "update"):
                if downstream_count > 0:
                    breaking = True
                    severity = "potentially_breaking"
                    reason = f"Modification may affect {downstream_count} dependent component(s)"
                else:
                    breaking = False
                    severity = "non-breaking"
                    reason = "No downstream dependents — safe to modify"
            elif change_type in ("add", "create"):
                breaking = False
                severity = "non-breaking"
                reason = "New component with no existing dependents"
            else:
                breaking = False
                severity = "unknown"
                reason = f"Cannot determine breaking nature of '{change_type}'"

            results.append({
                "component": f"{ctype}:{cname}",
                "change_type": change_type,
                "breaking": breaking,
                "severity": severity,
                "reason": reason,
            })

        return results

    def _get_node_body(self, node: Any) -> str:
        metadata = node.metadata or {}
        body = metadata.get("body", "") if isinstance(metadata, dict) else ""
        if not body:
            if hasattr(node, "description") and node.description:
                body = node.description
        if isinstance(body, dict):
            body = ""
        return str(body)

    def _rename_recommendations(
        self,
        total_refs: int,
        breaking_refs: list,
        code_refs: list,
        old_name: str,
        new_name: str | None,
    ) -> list[str]:
        recs: list[str] = []
        if total_refs == 0:
            recs.append(f"No references found — rename is safe.")
            return recs
        recs.append(f"Found {total_refs} reference(s) to update.")
        if breaking_refs:
            recs.append(f"Update {len(breaking_refs)} graph edges referencing '{old_name}'.")
        if code_refs:
            recs.append(
                f"Review {len(code_refs)} hardcoded reference(s) in metadata bodies."
            )
        if new_name:
            recs.append(f"After rename, update all references to use '{new_name}'.")
        recs.append("Perform a full deployment test after rename to catch any missed references.")
        return recs

    def _deployment_recommendations(
        self,
        risk_level: str,
        has_cycles: bool,
        component_count: int,
        affected: dict[str, int],
    ) -> list[str]:
        recs: list[str] = []
        if risk_level == "low":
            recs.append("Low deployment risk — proceed with standard deployment process.")
        elif risk_level == "medium":
            recs.append("Moderate deployment risk — recommend testing in sandbox first.")
            recs.append("Consider deploying during maintenance window.")
        else:
            recs.append("High deployment risk — deploy to a full-copy sandbox for validation.")
            recs.append("Prepare rollback plan before deployment.")

        if has_cycles:
            recs.append("Circular dependencies detected — resolve these before deployment.")

        if affected.get("flow", 0) > 2:
            recs.append(f"Test {affected['flow']} affected flow(s) after deployment.")
        if affected.get("apex_class", 0) > 2:
            recs.append(f"Recompile {affected['apex_class']} affected Apex class(es) post-deployment.")

        recs.append("Run all automated tests before and after deployment.")
        return recs
