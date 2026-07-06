"""Dependency graph engine with BFS/DFS traversal and impact analysis.

Supports queries like:
- "What depends on this field?"
- "What does this object depend on?"
- "What breaks if I change this field?"
- "Which Flow/CustomMetadata references this field?"
"""

import hashlib
import json
import uuid
from collections import deque
from collections.abc import Sequence
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.infrastructure.database.models.graph import (
    DependencyEdge,
    DependencySnapshot,
)
from sfir_backend.infrastructure.database.models.metadata import (
    MetadataComponent,
    MetadataField,
)

logger = structlog.get_logger(__name__)


class TraversalDirection(str, Enum):
    UPSTREAM = "upstream"
    DOWNSTREAM = "downstream"
    BOTH = "both"


class RiskLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DependencyGraphService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_upstream_dependencies(
        self,
        organization_id: uuid.UUID,
        component_key: str,
        max_depth: int = 5,
    ) -> list[dict[str, Any]]:
        """Find everything that depends on the given component.

        "What uses this?" — traverse edges where component is the target.
        """
        return await self._traverse(
            organization_id=organization_id,
            root_key=component_key,
            direction=TraversalDirection.UPSTREAM,
            max_depth=max_depth,
        )

    async def get_downstream_dependencies(
        self,
        organization_id: uuid.UUID,
        component_key: str,
        max_depth: int = 5,
    ) -> list[dict[str, Any]]:
        """Find everything that the given component depends on.

        "What does this use?" — traverse edges where component is the source.
        """
        return await self._traverse(
            organization_id=organization_id,
            root_key=component_key,
            direction=TraversalDirection.DOWNSTREAM,
            max_depth=max_depth,
        )

    async def _traverse(
        self,
        organization_id: uuid.UUID,
        root_key: str,
        direction: TraversalDirection,
        max_depth: int = 5,
    ) -> list[dict[str, Any]]:
        """BFS traversal of the dependency graph.

        For UPSTREAM: source_key -> target_key = our_key (what uses our_key)
        For DOWNSTREAM: source_key = our_key -> target_key (what our_key uses)
        """
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque()
        results: list[dict[str, Any]] = []

        queue.append((root_key, 0))
        visited.add(root_key)

        while queue:
            current_key, depth = queue.popleft()

            if depth >= max_depth:
                continue

            if direction == TraversalDirection.UPSTREAM:
                edges_query = select(DependencyEdge).where(
                    DependencyEdge.organization_id == organization_id,
                    DependencyEdge.target_key == current_key,
                )
            else:
                edges_query = select(DependencyEdge).where(
                    DependencyEdge.organization_id == organization_id,
                    DependencyEdge.source_key == current_key,
                )

            edges_result = await self._session.execute(edges_query)
            edges = edges_result.scalars().all()

            for edge in edges:
                if direction == TraversalDirection.UPSTREAM:
                    neighbor_key = edge.source_key
                else:
                    neighbor_key = edge.target_key

                results.append({
                    "source_key": edge.source_key,
                    "target_key": edge.target_key,
                    "edge_type": edge.edge_type,
                    "confidence": edge.confidence,
                    "risk_level": edge.risk_level,
                    "evidence": edge.evidence,
                    "depth": depth + 1,
                })

                if neighbor_key not in visited:
                    visited.add(neighbor_key)
                    queue.append((neighbor_key, depth + 1))

        return results

    async def analyze_change_impact(
        self,
        organization_id: uuid.UUID,
        component_key: str,
        change_description: str,
        max_depth: int = 10,
    ) -> dict[str, Any]:
        """Analyze the impact of changing a component.

        Returns:
            - impacted_components: all affected components
            - risk_score: 0-100 risk assessment
            - risk_level: low/medium/high/critical
            - summary: plain-text summary of the impact
            - by_type: breakdown by component type
        """
        upstream = await self.get_upstream_dependencies(
            organization_id, component_key, max_depth
        )

        if not upstream:
            return {
                "component_key": component_key,
                "impacted_count": 0,
                "risk_score": 0,
                "risk_level": RiskLevel.NONE,
                "summary": f"No dependents found for {component_key}. Low risk.",
                "upstream": [],
                "by_type": {},
            }

        # Calculate risk
        total_edges = len(upstream)
        high_risk = sum(
            1 for u in upstream if u.get("risk_level") == "high"
        )
        critical_risk = sum(
            1 for u in upstream if u.get("risk_level") == "critical"
        )

        risk_score = min(
            100,
            (high_risk * 20 + critical_risk * 40) / max(total_edges, 1) * 100,
        )

        if risk_score == 0:
            risk_level = RiskLevel.LOW
        elif risk_score < 30:
            risk_level = RiskLevel.MEDIUM
        elif risk_score < 70:
            risk_level = RiskLevel.HIGH
        else:
            risk_level = RiskLevel.CRITICAL

        by_type: dict[str, int] = {}
        for edge in upstream:
            etype = edge["edge_type"]
            by_type[etype] = by_type.get(etype, 0) + 1

        return {
            "component_key": component_key,
            "change_description": change_description,
            "impacted_count": total_edges,
            "risk_score": round(risk_score, 1),
            "risk_level": risk_level,
            "summary": (
                f"Changing `{component_key}` impacts {total_edges} "
                f"dependents across {len(by_type)} categories. "
                f"Risk level: {risk_level}."
            ),
            "upstream": upstream,
            "by_type": by_type,
        }

    async def get_or_create_snapshot(
        self,
        organization_id: uuid.UUID,
        root_key: str,
        direction: TraversalDirection = TraversalDirection.UPSTREAM,
        max_depth: int = 5,
        ttl_seconds: int = 600,
    ) -> dict[str, Any]:
        """Get a cached snapshot of dependency analysis or create one."""
        graph_hash = self._compute_hash(root_key, direction.value, max_depth)

        existing = await self._session.execute(
            select(DependencySnapshot).where(
                DependencySnapshot.organization_id == organization_id,
                DependencySnapshot.root_key == root_key,
                DependencySnapshot.traversal_direction == direction.value,
                DependencySnapshot.graph_hash == graph_hash,
                DependencySnapshot.generated_at
                > datetime.now(UTC),
            )
            .order_by(DependencySnapshot.generated_at.desc())
            .limit(1)
        )
        snapshot = existing.scalar_one_or_none()

        if snapshot:
            return {
                "cached": True,
                "generated_at": snapshot.generated_at,
                "root_key": snapshot.root_key,
                "traversal_direction": snapshot.traversal_direction,
                "max_depth": snapshot.max_depth,
                "payload": snapshot.payload,
            }

        results = await self._traverse(
            organization_id, root_key, direction, max_depth
        )

        snapshot = DependencySnapshot(
            id=uuid.uuid4(),
            organization_id=organization_id,
            root_key=root_key,
            traversal_direction=direction.value,
            max_depth=max_depth,
            graph_hash=graph_hash,
            payload={
                "results": results,
                "total": len(results),
            },
            generated_at=datetime.now(UTC),
        )
        self._session.add(snapshot)
        await self._session.flush()

        return {
            "cached": False,
            "generated_at": snapshot.generated_at,
            "root_key": snapshot.root_key,
            "traversal_direction": snapshot.traversal_direction,
            "max_depth": snapshot.max_depth,
            "payload": snapshot.payload,
        }

    async def find_path(
        self,
        organization_id: uuid.UUID,
        source_key: str,
        target_key: str,
    ) -> list[dict[str, Any]]:
        """Find the shortest dependency path between two components using BFS."""
        visited: dict[str, list[dict[str, Any]]] = {source_key: []}
        queue: deque[str] = deque([source_key])

        while queue:
            current = queue.popleft()

            edges_result = await self._session.execute(
                select(DependencyEdge).where(
                    DependencyEdge.organization_id == organization_id,
                    DependencyEdge.source_key == current,
                )
            )
            edges = edges_result.scalars().all()

            for edge in edges:
                neighbor = edge.target_key
                path_so_far = visited[current] + [
                    {
                        "source_key": edge.source_key,
                        "target_key": edge.target_key,
                        "edge_type": edge.edge_type,
                    }
                ]

                if neighbor == target_key:
                    return path_so_far

                if neighbor not in visited:
                    visited[neighbor] = path_so_far
                    queue.append(neighbor)

        return []

    async def find_shared_dependencies(
        self,
        organization_id: uuid.UUID,
        component_keys: list[str],
    ) -> list[dict[str, Any]]:
        """Find common dependencies shared by multiple components."""
        all_upstream: list[set[str]] = []

        for key in component_keys:
            results = await self.get_upstream_dependencies(
                organization_id, key, max_depth=3
            )
            upstream_keys = {r["source_key"] for r in results}
            all_upstream.append(upstream_keys)

        if not all_upstream:
            return []

        shared = set.intersection(*all_upstream) if len(all_upstream) > 1 else all_upstream[0]

        shared_details = []
        for sk in shared:
            shared_details.append({
                "key": sk,
                "referenced_by": component_keys,
            })

        return shared_details

    async def detect_dependencies_for_component(
        self,
        organization_id: uuid.UUID,
        component_id: uuid.UUID,
    ) -> int:
        """Auto-detect dependencies for a single component by analyzing its content.

        This is called after a component is synced. It scans the component's
        extra/payload for references to other components and creates edges.
        """
        result = await self._session.execute(
            select(MetadataComponent).where(
                MetadataComponent.id == component_id,
                MetadataComponent.organization_id == organization_id,
            )
        )
        component = result.scalar_one_or_none()
        if not component:
            return 0

        edges_created = 0
        extra = component.extra or {}
        content = extra.get("Body", "")

        if not content:
            return 0

        if component.component_type == "ApexClass":
            edges = self._detect_apex_references(
                organization_id, component, content
            )
            for edge_data in edges:
                edge = self._safe_create_edge(organization_id, edge_data)
                if edge:
                    self._session.add(edge)
                    edges_created += 1

        elif component.component_type == "ApexTrigger":
            edges = self._detect_apex_references(
                organization_id, component, content
            )
            for edge_data in edges:
                edge = self._safe_create_edge(organization_id, edge_data)
                if edge:
                    self._session.add(edge)
                    edges_created += 1

        await self._session.flush()
        return edges_created

    def _detect_apex_references(
        self,
        organization_id: uuid.UUID,
        component: MetadataComponent,
        body: str,
    ) -> list[dict[str, Any]]:
        """Detect SOQL object/field references in Apex code.

        Uses simple regex pattern matching for:
        - [SELECT ... FROM ObjectName]
        - schema.getGlobalDescribe().get('ObjectName')
        - ObjectName.__c
        - ObjectName.FieldName__c
        - Database.query / Database.countQuery
        """
        import re

        edges = []

        # Detect SOQL FROM clauses: FROM ObjectName
        from_pattern = re.compile(
            r"\bFROM\s+([A-Za-z_][A-Za-z0-9_]*(?:\x2e__c)?)",
            re.IGNORECASE,
        )
        for match in from_pattern.finditer(body):
            obj_name = match.group(1)
            edge = self._build_edge(
                organization_id=organization_id,
                source=component,
                target_key=f"CustomObject:{obj_name}",
                edge_type="apex_soql_reference",
                confidence=90,
                evidence={"soql": match.group(), "line": self._get_line_number(body, match.start())},
            )
            if edge:
                edges.append(edge)

        # Detect Schema.getGlobalDescribe().get('ObjectName')
        describe_pattern = re.compile(
            r"Schema\.getGlobalDescribe\(\)\.get\('([^']+)'\)",
            re.IGNORECASE,
        )
        for match in describe_pattern.finditer(body):
            obj_name = match.group(1)
            edge = self._build_edge(
                organization_id=organization_id,
                source=component,
                target_key=f"CustomObject:{obj_name}",
                edge_type="apex_describe_reference",
                confidence=85,
                evidence={"code": match.group(), "line": self._get_line_number(body, match.start())},
            )
            if edge:
                edges.append(edge)

        # Detect field references: ObjectName.FieldName
        field_pattern = re.compile(
            r"([A-Za-z_]\w*)\.([A-Za-z_]\w*__c)\b"
        )
        for match in field_pattern.finditer(body):
            obj_name = match.group(1)
            field_name = match.group(2)
            edge = self._build_edge(
                organization_id=organization_id,
                source=component,
                target_key=f"CustomField:{obj_name}.{field_name}",
                edge_type="apex_field_reference",
                confidence=70,
                evidence={"code": match.group(), "line": self._get_line_number(body, match.start())},
            )
            if edge:
                edges.append(edge)

        return edges

    def _build_edge(
        self,
        organization_id: uuid.UUID,
        source: MetadataComponent,
        target_key: str,
        edge_type: str,
        confidence: int,
        evidence: dict,
    ) -> dict[str, Any] | None:
        source_key = f"{source.component_type}:{source.full_name}"
        return {
            "organization_id": organization_id,
            "source_component_id": source.id,
            "source_key": source_key,
            "target_key": target_key,
            "edge_type": edge_type,
            "confidence": confidence,
            "risk_level": self._assess_risk(edge_type),
            "source_api": "tooling",
            "evidence": evidence,
        }

    def _safe_create_edge(
        self, organization_id: uuid.UUID, edge_data: dict
    ) -> DependencyEdge | None:
        from sqlalchemy import and_

        existing = self._session.execute(
            select(DependencyEdge).where(
                and_(
                    DependencyEdge.organization_id == organization_id,
                    DependencyEdge.source_key == edge_data["source_key"],
                    DependencyEdge.target_key == edge_data["target_key"],
                    DependencyEdge.edge_type == edge_data["edge_type"],
                )
            )
        )
        if existing.scalar_one_or_none():
            return None

        return DependencyEdge(
            id=uuid.uuid4(),
            **{k: v for k, v in edge_data.items() if k != "id"},
        )

    def _get_line_number(self, text: str, position: int) -> int:
        return text[:position].count("\n") + 1

    def _assess_risk(self, edge_type: str) -> str:
        high_risk = {"deployed_reference", "flow_update", "validation_rule"}
        medium_risk = {"apex_soql_reference", "apex_field_reference"}
        if edge_type in high_risk:
            return "high"
        elif edge_type in medium_risk:
            return "medium"
        return "low"

    def _compute_hash(self, *args: str) -> str:
        raw = "|".join(args)
        return hashlib.sha256(raw.encode()).hexdigest()[:32]
