from __future__ import annotations

from collections import defaultdict

from sfir_backend.domain.documentation.models import (
    DocumentationPage,
    DocumentationReport,
    ReportType,
    Section,
    SectionType,
)
from sfir_backend.domain.graph.models import Graph
from sfir_backend.domain.search.models import SearchDocument
from sfir_backend.infrastructure.documentation.renderers import MarkdownRenderer


class DependencyReportGenerator:
    def __init__(self) -> None:
        self._md = MarkdownRenderer()

    def generate_dependency_tree(
        self,
        graph: Graph,
        component_key: str,
    ) -> DocumentationReport:
        md_lines: list[str] = []
        self._build_tree_md(graph, component_key, md_lines, 0, set())
        content = "\n".join(md_lines)
        section = Section(
            title="Dependency Tree",
            content=content,
            order=0,
            section_type=SectionType.DEPENDENCIES,
        )
        page = DocumentationPage(
            title=f"Dependency Tree: {component_key}",
            component_key=component_key,
            component_type="report",
            sections=[section],
            word_count=len(content.split()),
        )
        return DocumentationReport(
            title=f"Dependency Tree Report: {component_key}",
            report_type=ReportType.DEPENDENCY,
            pages=[page],
            statistics={"root": component_key},
        )

    def generate_reverse_dependency_tree(
        self,
        graph: Graph,
        component_key: str,
    ) -> DocumentationReport:
        md_lines: list[str] = []
        self._build_reverse_tree_md(graph, component_key, md_lines, 0, set())
        content = "\n".join(md_lines)
        section = Section(
            title="Reverse Dependency Tree",
            content=content,
            order=0,
            section_type=SectionType.REFERENCES,
        )
        page = DocumentationPage(
            title=f"Reverse Dependency Tree: {component_key}",
            component_key=component_key,
            component_type="report",
            sections=[section],
            word_count=len(content.split()),
        )
        return DocumentationReport(
            title=f"Reverse Dependency Report: {component_key}",
            report_type=ReportType.DEPENDENCY,
            pages=[page],
            statistics={"root": component_key},
        )

    def generate_component_references(
        self,
        graph: Graph,
        component_key: str,
    ) -> DocumentationReport:
        node = graph.get_node(component_key)
        if not node:
            return DocumentationReport(
                title=f"References: {component_key} (not found)",
                report_type=ReportType.DEPENDENCY,
            )
        deps_rows: list[list[str]] = []
        for edge in graph.get_outgoing_edges(component_key):
            target = graph.get_node(edge.target_id)
            deps_rows.append([
                f"`{edge.target_id}`",
                target.node_type.value if target and target.node_type else "?",
                edge.edge_type.value if edge.edge_type else "",
            ])
        refs_rows: list[list[str]] = []
        for edge in graph.get_incoming_edges(component_key):
            source = graph.get_node(edge.source_id)
            refs_rows.append([
                f"`{edge.source_id}`",
                source.node_type.value if source and source.node_type else "?",
                edge.edge_type.value if edge.edge_type else "",
            ])

        sections: list[Section] = []
        if deps_rows:
            sections.append(Section(
                title="Dependencies",
                content=self._md.render_table(["Component", "Type", "Relation"], deps_rows),
                order=0,
                section_type=SectionType.DEPENDENCIES,
            ))
        if refs_rows:
            sections.append(Section(
                title="Referenced By",
                content=self._md.render_table(["Component", "Type", "Relation"], refs_rows),
                order=1,
                section_type=SectionType.REFERENCES,
            ))
        if not sections:
            sections.append(Section(
                title="References",
                content="No references found.",
                order=0,
                section_type=SectionType.REFERENCES,
            ))

        page = DocumentationPage(
            title=f"Component References: {component_key}",
            component_key=component_key,
            sections=sections,
        )
        return DocumentationReport(
            title=f"Component References Report: {component_key}",
            report_type=ReportType.DEPENDENCY,
            pages=[page],
            statistics={
                "dependencies": len(deps_rows),
                "references": len(refs_rows),
            },
        )

    def generate_graph_summary(self, graph: Graph) -> DocumentationReport:
        type_counts: dict[str, int] = defaultdict(int)
        edge_count = graph.edge_count
        for node in graph.nodes.values():
            ntype = node.node_type.value if node.node_type else "unknown"
            type_counts[ntype] += 1
        rows = [[t, str(c)] for t, c in sorted(type_counts.items())]
        content = self._md.render_table(["Component Type", "Count"], rows)
        content += f"\n\n**Total Nodes:** {graph.node_count}\n"
        content += f"**Total Edges:** {edge_count}\n"

        section = Section(
            title="Graph Summary",
            content=content,
            order=0,
            section_type=SectionType.OVERVIEW,
        )
        page = DocumentationPage(
            title="Graph Summary",
            sections=[section],
            word_count=len(content.split()),
        )
        return DocumentationReport(
            title="Dependency Graph Summary",
            report_type=ReportType.DEPENDENCY,
            pages=[page],
            statistics={
                "total_nodes": graph.node_count,
                "total_edges": edge_count,
                "node_types": dict(type_counts),
            },
        )

    def generate_circular_dependency_report(
        self,
        graph: Graph,
    ) -> DocumentationReport:
        cycles = self._find_cycles(graph)
        if not cycles:
            section = Section(
                title="Circular Dependencies",
                content="No circular dependencies found.",
                order=0,
                section_type=SectionType.DEPENDENCIES,
            )
        else:
            rows = []
            for i, cycle in enumerate(cycles, 1):
                rows.append([str(i), " → ".join(cycle), str(len(cycle))])
            content = self._md.render_table(
                ["#", "Cycle", "Length"], rows,
            )
            section = Section(
                title="Circular Dependencies",
                content=content,
                order=0,
                section_type=SectionType.DEPENDENCIES,
            )

        page = DocumentationPage(
            title="Circular Dependency Report",
            sections=[section],
            word_count=len(section.content.split()),
        )
        return DocumentationReport(
            title="Circular Dependency Analysis",
            report_type=ReportType.DEPENDENCY,
            pages=[page],
            statistics={"cycles_found": len(cycles)},
        )

    def _build_tree_md(
        self,
        graph: Graph,
        key: str,
        lines: list[str],
        depth: int,
        visited: set[str],
    ) -> None:
        indent = "  " * depth
        node = graph.get_node(key)
        label = node.api_name if node else key
        ntype = f" ({node.node_type.value})" if node and node.node_type else ""
        if key in visited:
            lines.append(f"{indent}- `{label}`{ntype} *(circular)*")
            return
        lines.append(f"{indent}- `{label}`{ntype}")
        visited.add(key)
        for edge in graph.get_outgoing_edges(key):
            self._build_tree_md(graph, edge.target_id, lines, depth + 1, visited)

    def _build_reverse_tree_md(
        self,
        graph: Graph,
        key: str,
        lines: list[str],
        depth: int,
        visited: set[str],
    ) -> None:
        indent = "  " * depth
        node = graph.get_node(key)
        label = node.api_name if node else key
        ntype = f" ({node.node_type.value})" if node and node.node_type else ""
        if key in visited:
            lines.append(f"{indent}- `{label}`{ntype} *(circular)*")
            return
        lines.append(f"{indent}- `{label}`{ntype}")
        visited.add(key)
        for edge in graph.get_incoming_edges(key):
            self._build_reverse_tree_md(graph, edge.source_id, lines, depth + 1, visited)

    def _find_cycles(self, graph: Graph) -> list[list[str]]:
        cycles: list[list[str]] = []
        visited: set[str] = set()
        rec_stack: list[str] = []

        def dfs(node: str) -> None:
            visited.add(node)
            rec_stack.append(node)
            for edge in graph.get_outgoing_edges(node):
                nxt = edge.target_id
                if nxt not in visited:
                    dfs(nxt)
                elif nxt in rec_stack:
                    idx = rec_stack.index(nxt)
                    cycle = list(rec_stack[idx:])
                    if cycle not in cycles:
                        cycles.append(cycle)
            rec_stack.pop()

        for key in graph.nodes:
            if key not in visited:
                dfs(key)
        return cycles


class ArchitectureReportGenerator:
    def __init__(self) -> None:
        self._md = MarkdownRenderer()

    def generate_organization_overview(
        self,
        graph: Graph,
    ) -> DocumentationReport:
        type_counts: dict[str, int] = defaultdict(int)
        namespace_counts: dict[str, int] = defaultdict(int)
        for node in graph.nodes.values():
            ntype = node.node_type.value if node.node_type else "unknown"
            type_counts[ntype] += 1
            ns = node.namespace or "standard"
            namespace_counts[ns] += 1

        sections: list[Section] = []
        overview_props = {
            "Total Components": str(graph.node_count),
            "Total Dependencies": str(graph.edge_count),
            "Unique Types": str(len(type_counts)),
            "Namespaces": str(len(namespace_counts)),
        }
        sections.append(Section(
            title="Organization Overview",
            content=self._md.render_properties_table(overview_props),
            order=0,
            section_type=SectionType.OVERVIEW,
        ))
        type_rows = [[t, str(c)] for t, c in sorted(type_counts.items())]
        sections.append(Section(
            title="Component Inventory",
            content=self._md.render_table(["Type", "Count"], type_rows),
            order=1,
            section_type=SectionType.PROPERTIES,
        ))
        ns_rows = [[ns, str(c)] for ns, c in sorted(namespace_counts.items())]
        sections.append(Section(
            title="Namespace Summary",
            content=self._md.render_table(["Namespace", "Count"], ns_rows),
            order=2,
            section_type=SectionType.PROPERTIES,
        ))

        page = DocumentationPage(
            title="Organization Metadata Overview",
            sections=sections,
            word_count=sum(len(s.content.split()) for s in sections),
        )
        return DocumentationReport(
            title="Architecture Report: Organization Overview",
            report_type=ReportType.ARCHITECTURE,
            pages=[page],
            statistics={
                "total_components": graph.node_count,
                "total_dependencies": graph.edge_count,
                "unique_types": len(type_counts),
                "namespaces": len(namespace_counts),
            },
        )

    def generate_component_inventory(
        self,
        graph: Graph,
        component_type: str | None = None,
    ) -> DocumentationReport:
        nodes_to_include = (
            [n for n in graph.nodes.values()
             if n.node_type and n.node_type.value == component_type]
            if component_type
            else list(graph.nodes.values())
        )
        type_header = f" ({component_type})" if component_type else ""
        rows: list[list[str]] = []
        for node in sorted(nodes_to_include, key=lambda n: n.api_name):
            ntype = node.node_type.value if node.node_type else ""
            if component_type and ntype != component_type:
                continue
            rows.append([
                f"`{node.api_name}`",
                ntype,
                node.label or "",
                node.namespace or "—",
            ])
        content = self._md.render_table(
            ["API Name", "Type", "Label", "Namespace"],
            rows,
        ) if rows else "No components found."
        section = Section(
            title=f"Component Inventory{type_header}",
            content=content,
            order=0,
            section_type=SectionType.OVERVIEW,
        )
        page = DocumentationPage(
            title=f"Component Inventory{type_header}",
            sections=[section],
            word_count=len(content.split()),
        )
        return DocumentationReport(
            title=f"Architecture Report: Component Inventory{type_header}",
            report_type=ReportType.ARCHITECTURE,
            pages=[page],
            statistics={"total_components": len(rows)},
        )

    def generate_relationship_overview(
        self,
        graph: Graph,
    ) -> DocumentationReport:
        edge_type_counts: dict[str, int] = defaultdict(int)
        for edge in graph.edges.values():
            et = edge.edge_type.value if edge.edge_type else "unknown"
            edge_type_counts[et] += 1
        rows = [[et, str(c)]
                for et, c in sorted(edge_type_counts.items())]
        content = self._md.render_table(["Relationship Type", "Count"], rows)
        section = Section(
            title="Relationship Overview",
            content=content,
            order=0,
            section_type=SectionType.RELATIONSHIPS,
        )
        page = DocumentationPage(
            title="Relationship Overview",
            sections=[section],
        )
        return DocumentationReport(
            title="Architecture Report: Relationship Overview",
            report_type=ReportType.ARCHITECTURE,
            pages=[page],
            statistics={"total_relationships": graph.edge_count,
                        "types": dict(edge_type_counts)},
        )


class MetadataReportGenerator:
    def __init__(self) -> None:
        self._md = MarkdownRenderer()

    def generate_metadata_report(
        self,
        graph: Graph,
        _search_results: list[SearchDocument] | None = None,
    ) -> DocumentationReport:
        type_counts: dict[str, int] = defaultdict(int)
        with_fields: int = 0
        with_desc: int = 0
        with_namespace: int = 0
        total = len(graph.nodes)

        for node in graph.nodes.values():
            ntype = node.node_type.value if node.node_type else "unknown"
            type_counts[ntype] += 1
            if node.description:
                with_desc += 1
            if node.namespace:
                with_namespace += 1
            if node.metadata:
                with_fields += 1

        sections: list[Section] = []
        def _pct(part: int) -> str:
            return f"{part}/{total} ({round(part/total*100, 1)}%)" if total > 0 else "0"

        quality_props = {
            "Total Components": str(total),
            "With Description": _pct(with_desc),
            "With Namespace": _pct(with_namespace),
            "With Metadata": _pct(with_fields),
        }
        sections.append(Section(
            title="Metadata Quality",
            content=self._md.render_properties_table(quality_props),
            order=0,
            section_type=SectionType.OVERVIEW,
        ))
        type_rows = [[t, str(c)] for t, c in sorted(type_counts.items())]
        sections.append(Section(
            title="Component Types",
            content=self._md.render_table(["Type", "Count"], type_rows),
            order=1,
            section_type=SectionType.PROPERTIES,
        ))

        page = DocumentationPage(
            title="Metadata Report",
            sections=sections,
        )
        return DocumentationReport(
            title="Metadata Analysis Report",
            report_type=ReportType.METADATA,
            pages=[page],
            statistics={
                "total": total,
                "with_description": with_desc,
                "with_namespace": with_namespace,
                "with_metadata": with_fields,
                "types": dict(type_counts),
            },
        )


class ImpactReportGenerator:
    def __init__(self) -> None:
        self._md = MarkdownRenderer()

    def generate_impact_report(
        self,
        graph: Graph,
        component_key: str,
    ) -> DocumentationReport:
        from sfir_backend.infrastructure.impact.blast_radius import BlastRadiusCalculator
        from sfir_backend.infrastructure.impact.risk import RiskCalculator

        blast = BlastRadiusCalculator()
        risk = RiskCalculator()
        br = blast.calculate(graph, component_key, max_depth=5)
        node = graph.get_node(component_key)
        ntype = node.node_type.value if node and node.node_type else "unknown"
        ra = risk.calculate(br, ntype)

        sections: list[Section] = []
        props = {
            "Component": f"`{component_key}`",
            "Total Affected": str(br.total_count),
            "Direct": str(br.direct_count),
            "Max Depth": str(br.max_depth),
            "Circular": "Yes" if br.has_circular_dependency else "No",
        }
        sections.append(Section(
            title="Impact Overview",
            content=self._md.render_properties_table(props),
            order=0,
            section_type=SectionType.OVERVIEW,
        ))
        risk_props = {
            "Risk Score": str(ra.risk_score),
            "Severity": ra.severity.value,
            "Factors": "; ".join(ra.reasons),
        }
        sections.append(Section(
            title="Risk Assessment",
            content=self._md.render_properties_table(risk_props),
            order=1,
            section_type=SectionType.IMPACT,
        ))
        if br.by_type:
            type_rows = [[t, str(c)] for t, c in sorted(br.by_type.items())]
            sections.append(Section(
                title="Affected by Type",
                content=self._md.render_table(["Type", "Count"], type_rows),
                order=2,
                section_type=SectionType.BLAST_RADIUS,
            ))

        page = DocumentationPage(
            title=f"Impact Report: {component_key}",
            component_key=component_key,
            sections=sections,
            word_count=sum(len(s.content.split()) for s in sections),
        )
        return DocumentationReport(
            title=f"Impact Analysis Report: {component_key}",
            report_type=ReportType.IMPACT,
            pages=[page],
            statistics={
                "total_affected": br.total_count,
                "risk_score": ra.risk_score,
                "severity": ra.severity.value,
            },
        )
