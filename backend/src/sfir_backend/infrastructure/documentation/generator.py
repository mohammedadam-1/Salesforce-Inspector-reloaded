from __future__ import annotations

import time

from sfir_backend.domain.documentation.models import (
    DocumentationFormat,
    DocumentationPage,
    DocumentationReport,
    GenerateRequest,
    Section,
    SectionType,
)
from sfir_backend.domain.graph.models import Graph, GraphNode, NodeType
from sfir_backend.infrastructure.documentation.renderers import (
    HTMLRenderer,
    MarkdownRenderer,
)


class DocumentationGenerator:
    def __init__(self) -> None:
        self._md = MarkdownRenderer()
        self._html = HTMLRenderer()

    def generate(
        self,
        graph: Graph,
        request: GenerateRequest,
    ) -> DocumentationReport:
        start = time.time()
        pages: list[DocumentationPage] = []

        for key in request.component_keys:
            node = graph.get_node(key)
            if node is None:
                continue
            page = self._generate_page(node, graph, request)
            pages.append(page)

        report = DocumentationReport(
            title=f"Documentation: {len(pages)} component(s)",
            report_type=request.report_type,
            pages=pages,
            format=request.format,
            took_ms=(time.time() - start) * 1000,
        )
        stats = {
            "total_components": len(request.component_keys),
            "total_pages": len(pages),
            "component_types": list(
                {p.component_type for p in pages if p.component_type},
            ),
            "format": request.format.value,
        }
        report.statistics = stats
        return report

    def generate_single(
        self,
        graph: Graph,
        component_key: str,
        format: DocumentationFormat = DocumentationFormat.MARKDOWN,
        include_sections: list[str] | None = None,
    ) -> DocumentationPage:
        node = graph.get_node(component_key)
        if node is None:
            return DocumentationPage(
                title=f"Not Found: {component_key}",
                component_key=component_key,
            )
        request = GenerateRequest(
            component_keys=[component_key],
            format=format,
            include_sections=include_sections,
        )
        return self._generate_page(node, graph, request)

    def generate_from_nodes(
        self,
        nodes: list[GraphNode],
        graph: Graph,
        format: DocumentationFormat = DocumentationFormat.MARKDOWN,
    ) -> list[DocumentationPage]:
        pages: list[DocumentationPage] = []
        for node in nodes:
            request = GenerateRequest(
                component_keys=[node.key],
                format=format,
            )
            page = self._generate_page(node, graph, request)
            pages.append(page)
        return pages

    def _generate_page(
        self,
        node: GraphNode,
        graph: Graph,
        request: GenerateRequest,
    ) -> DocumentationPage:
        sections = self._build_sections(node, graph, request)
        content = self._render_sections(sections, request.format)
        word_count = sum(len(s.content.split()) for s in content if s.content)

        return DocumentationPage(
            title=f"{node.api_name} ({node.node_type.value})",
            component_key=node.key,
            component_type=node.node_type.value if node.node_type else "",
            api_name=node.api_name,
            sections=content,
            format=request.format,
            word_count=word_count,
        )

    def _build_sections(
        self,
        node: GraphNode,
        graph: Graph,
        request: GenerateRequest,
    ) -> list[Section]:
        sections: list[Section] = []
        node_type = node.node_type.value if node.node_type else ""

        overview = self._build_overview(node)
        if overview:
            sections.append(overview)

        props = self._build_properties(node)
        if props:
            sections.append(props)

        deps = self._build_dependencies(node, graph)
        if deps:
            sections.append(deps)

        refs = self._build_references(node, graph)
        if refs:
            sections.append(refs)

        type_sections = self._build_type_specific(node, graph, node_type)
        sections.extend(type_sections)

        if request.include_sections:
            sections = [
                s for s in sections
                if s.section_type.value in request.include_sections
                or s.title.lower() in [x.lower() for x in request.include_sections]
            ]
            if not sections:
                sections = [self._build_overview(node)] if self._build_overview(node) else []

        return sections

    def _build_overview(self, node: GraphNode) -> Section | None:
        props: dict[str, str] = {
            "API Name": f"`{node.api_name}`",
            "Type": f"`{node.node_type.value if node.node_type else 'unknown'}`",
        }
        if node.namespace:
            props["Namespace"] = node.namespace
        if node.label:
            props["Label"] = node.label
        if node.description:
            props["Description"] = node.description
        else:
            props["Description"] = "N/A"
        return Section(
            title="Overview",
            content=self._md.render_properties_table(props),
            order=0,
            section_type=SectionType.OVERVIEW,
        )

    def _build_properties(self, node: GraphNode) -> Section | None:
        md = node.metadata
        if not md:
            return None
        props: dict[str, str] = {}
        for k, v in md.items():
            if isinstance(v, (str, int, float, bool)):
                props[k.replace("_", " ").title()] = str(v)
            elif isinstance(v, list):
                props[k.replace("_", " ").title()] = ", ".join(str(x) for x in v[:10])
                if len(v) > 10:
                    props[k.replace("_", " ").title()] += f" (+{len(v) - 10} more)"
        if not props:
            return None
        return Section(
            title="Properties",
            content=self._md.render_properties_table(props),
            order=1,
            section_type=SectionType.PROPERTIES,
        )

    def _build_dependencies(self, node: GraphNode, graph: Graph) -> Section | None:
        edges = graph.get_outgoing_edges(node.key)
        if not edges:
            return None
        rows: list[list[str]] = []
        for edge in edges:
            target = graph.get_node(edge.target_id)
            tname = target.api_name if target else edge.target_id
            ttype = target.node_type.value if target and target.node_type else "?"
            rows.append([ttype, f"`{tname}`", edge.edge_type.value if edge.edge_type else "?"])
        if not rows:
            return None
        content = self._md.render_table(["Type", "Target", "Relation"], rows)
        return Section(
            title="Dependencies",
            content=content,
            order=2,
            section_type=SectionType.DEPENDENCIES,
        )

    def _build_references(self, node: GraphNode, graph: Graph) -> Section | None:
        edges = graph.get_incoming_edges(node.key)
        if not edges:
            return None
        rows: list[list[str]] = []
        for edge in edges:
            source = graph.get_node(edge.source_id)
            sname = source.api_name if source else edge.source_id
            stype = source.node_type.value if source and source.node_type else "?"
            rows.append([stype, f"`{sname}`", edge.edge_type.value if edge.edge_type else "?"])
        if not rows:
            return None
        content = self._md.render_table(["Type", "Source", "Relation"], rows)
        return Section(
            title="References",
            content=content,
            order=3,
            section_type=SectionType.REFERENCES,
        )

    def _build_type_specific(
        self,
        node: GraphNode,
        graph: Graph,
        node_type: str,
    ) -> list[Section]:
        sections: list[Section] = []
        if node_type == "object":
            sec = self._build_object_fields(node, graph)
            if sec:
                sections.append(sec)
            sec = self._build_object_children(node, graph)
            if sec:
                sections.append(sec)
        elif node_type == "field":
            sec = self._build_field_references(node, graph)
            if sec:
                sections.append(sec)
        elif node_type == "flow":
            sec = self._build_flow_versions(node, graph)
            if sec:
                sections.append(sec)
        elif node_type == "apex_class":
            sec = self._build_apex_references(node, graph)
            if sec:
                sections.append(sec)
        return sections

    def _build_object_fields(self, node: GraphNode, graph: Graph) -> Section | None:
        rows: list[list[str]] = []
        for edge in graph.get_outgoing_edges(node.key):
            target = graph.get_node(edge.target_id)
            if target and target.node_type == NodeType.FIELD:
                rows.append([
                    f"`{target.api_name}`",
                    target.label or "",
                    target.node_type.value if target.node_type else "",
                ])
        if not rows:
            return None
        content = self._md.render_table(["API Name", "Label", "Type"], rows)
        return Section(
            title="Fields",
            content=content,
            order=4,
            section_type=SectionType.FIELDS,
        )

    def _build_object_children(self, node: GraphNode, graph: Graph) -> Section | None:
        rows: list[list[str]] = []
        for edge in graph.get_outgoing_edges(node.key):
            target = graph.get_node(edge.target_id)
            if target and target.node_type != NodeType.FIELD:
                rows.append([
                    f"`{target.api_name}`",
                    target.node_type.value if target.node_type else "",
                    edge.edge_type.value if edge.edge_type else "",
                ])
        if not rows:
            return None
        content = self._md.render_table(["API Name", "Type", "Relation"], rows)
        return Section(
            title="Child Components",
            content=content,
            order=5,
            section_type=SectionType.CHILDREN,
        )

    def _build_field_references(self, node: GraphNode, graph: Graph) -> Section | None:
        rows: list[list[str]] = []
        for edge in graph.get_incoming_edges(node.key):
            source = graph.get_node(edge.source_id)
            if source:
                rows.append([
                    f"`{source.api_name}`",
                    source.node_type.value if source.node_type else "",
                    edge.edge_type.value if edge.edge_type else "",
                ])
        if not rows:
            return None
        content = self._md.render_table(["Component", "Type", "Relation"], rows)
        return Section(
            title="Referenced By",
            content=content,
            order=4,
            section_type=SectionType.REFERENCES,
        )

    def _build_flow_versions(self, node: GraphNode, graph: Graph) -> Section | None:
        rows: list[list[str]] = []
        for edge in graph.get_outgoing_edges(node.key):
            target = graph.get_node(edge.target_id)
            if target and target.node_type == NodeType.FLOW_VERSION:
                rows.append([
                    f"`{target.api_name}`",
                    edge.edge_type.value if edge.edge_type else "",
                ])
        if not rows:
            return None
        content = self._md.render_table(["Version", "Relation"], rows)
        return Section(
            title="Flow Versions",
            content=content,
            order=4,
            section_type=SectionType.VERSIONS,
        )

    def _build_apex_references(self, node: GraphNode, graph: Graph) -> Section | None:
        rows: list[list[str]] = []
        for edge in graph.get_outgoing_edges(node.key):
            target = graph.get_node(edge.target_id)
            if target:
                rows.append([
                    f"`{target.api_name}`",
                    target.node_type.value if target.node_type else "",
                    edge.edge_type.value if edge.edge_type else "",
                ])
        if not rows:
            return None
        content = self._md.render_table(["Reference", "Type", "Relation"], rows)
        return Section(
            title="Referenced Components",
            content=content,
            order=4,
            section_type=SectionType.DEPENDENCIES,
        )

    def _render_sections(
        self,
        sections: list[Section],
        format: DocumentationFormat,
    ) -> list[Section]:
        if format == DocumentationFormat.MARKDOWN:
            return sections
        if format == DocumentationFormat.HTML:
            rendered: list[Section] = []
            for sec in sections:
                html_content = self._html._md_to_html(sec.content)
                rendered.append(Section(
                    title=sec.title,
                    content=html_content,
                    order=sec.order,
                    section_type=sec.section_type,
                ))
            return rendered
        return sections

    def _render_markdown(self, sections: list[Section]) -> list[Section]:
        return sections

    def _render_html(self, sections: list[Section]) -> list[Section]:
        rendered: list[Section] = []
        for sec in sections:
            html_content = self._html._md_to_html(sec.content)
            rendered.append(Section(
                title=sec.title,
                content=html_content,
                order=sec.order,
                section_type=sec.section_type,
            ))
        return rendered
