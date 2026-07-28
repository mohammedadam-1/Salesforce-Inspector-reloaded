from __future__ import annotations

import re

from sfir_backend.domain.documentation.models import (
    DocumentationPage,
    Section,
    SectionType,
)


class MarkdownRenderer:
    def render_page(self, page: DocumentationPage) -> str:
        lines: list[str] = []
        lines.append(f"# {page.title}")
        lines.append("")
        if page.api_name:
            lines.append(f"**API Name:** `{page.api_name}`  ")
        if page.component_type:
            lines.append(f"**Type:** `{page.component_type}`  ")
        lines.append("")
        lines.append("---")
        lines.append("")
        for section in sorted(page.sections, key=lambda s: s.order):
            lines.extend(self._render_section(section))
        return "\n".join(lines)

    def _render_section(self, section: Section) -> list[str]:
        lines: list[str] = []
        lines.append(f"## {section.title}")
        lines.append("")
        if section.content:
            lines.append(section.content)
            lines.append("")
        return lines

    def render_table(
        self,
        headers: list[str],
        rows: list[list[str]],
    ) -> str:
        if not headers:
            return ""
        col_count = len(headers)
        lines: list[str] = []
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * col_count) + " |")
        for row in rows:
            padded = row + [""] * (col_count - len(row))
            lines.append("| " + " | ".join(padded[:col_count]) + " |")
        return "\n".join(lines)

    def render_bullet_list(self, items: list[str]) -> str:
        return "\n".join(f"- {item}" for item in items)

    def render_code_block(self, code: str, language: str = "") -> str:
        lang_tag = language if language else ""
        return f"```{lang_tag}\n{code}\n```"

    def render_properties_table(
        self,
        properties: dict[str, str],
    ) -> str:
        rows = [[k, v] for k, v in properties.items()]
        return self.render_table(["Property", "Value"], rows)

    def render_section_content(
        self,
        title: str,
        content: str,
        order: int = 0,
    ) -> Section:
        return Section(
            title=title,
            content=content,
            order=order,
            section_type=SectionType.CUSTOM,
        )


class HTMLRenderer:
    CSS = """
<style>
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    line-height: 1.6;
    max-width: 960px;
    margin: 0 auto;
    padding: 20px;
    color: #333;
  }
  h1 { border-bottom: 2px solid #1a73e8; padding-bottom: 8px; color: #1a73e8; }
  h2 { border-bottom: 1px solid #ddd; padding-bottom: 4px; margin-top: 24px; color: #444; }
  table { border-collapse: collapse; width: 100%; margin: 8px 0; }
  th, td { border: 1px solid #ddd; padding: 8px 12px; text-align: left; }
  th { background-color: #f5f5f5; font-weight: 600; }
  tr:nth-child(even) { background-color: #fafafa; }
  code { background: #f0f0f0; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; }
  pre { background: #f5f5f5; padding: 12px; border-radius: 4px; overflow-x: auto; }
  .badge {
    display: inline-block;
    background: #e8f0fe;
    color: #1a73e8;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 0.8em;
    font-weight: 500;
  }
  .meta { color: #666; font-size: 0.9em; }
  hr { border: none; border-top: 1px solid #ddd; margin: 24px 0; }
</style>
"""

    def render_page(self, page: DocumentationPage) -> str:
        parts: list[str] = [
            "<!DOCTYPE html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="UTF-8">',
            f"<title>{self._escape(page.title)}</title>",
            self.CSS,
            "</head>",
            "<body>",
            f"<h1>{self._escape(page.title)}",
        ]
        if page.component_type:
            parts.append(
                f' <span class="badge">{self._escape(page.component_type)}</span>',
            )
        parts.append("</h1>")
        parts.append(
            f'<p class="meta">API Name: <code>{self._escape(page.api_name)}</code>'
            f' &middot; Generated: {page.generated_at.isoformat()}</p>',
        )
        parts.append("<hr>")
        for section in sorted(page.sections, key=lambda s: s.order):
            parts.append(f"<h2>{self._escape(section.title)}</h2>")
            if section.content:
                parts.append(f"<div>{self._md_to_html(section.content)}</div>")
        parts.append("</body>")
        parts.append("</html>")
        return "\n".join(parts)

    def render_table(
        self,
        headers: list[str],
        rows: list[list[str]],
    ) -> str:
        parts: list[str] = ["<table>", "<tr>"]
        for h in headers:
            parts.append(f"<th>{self._escape(h)}</th>")
        parts.append("</tr>")
        for row in rows:
            parts.append("<tr>")
            for cell in row:
                parts.append(f"<td>{self._escape(cell)}</td>")
            parts.append("</tr>")
        parts.append("</table>")
        return "\n".join(parts)

    def render_bullet_list(self, items: list[str]) -> str:
        parts = ["<ul>"]
        for item in items:
            parts.append(f"<li>{self._escape(item)}</li>")
        parts.append("</ul>")
        return "\n".join(parts)

    def render_code_block(self, code: str, language: str = "") -> str:
        cls = f' class="language-{language}"' if language else ""
        return f"<pre><code{cls}>{self._escape(code)}</code></pre>"

    def render_properties_table(self, properties: dict[str, str]) -> str:
        rows = [[k, v] for k, v in properties.items()]
        return self.render_table(["Property", "Value"], rows)

    def render_section_content(
        self,
        title: str,
        content: str,
        order: int = 0,
    ) -> Section:
        return Section(
            title=title,
            content=content,
            order=order,
            section_type=SectionType.CUSTOM,
        )

    def _escape(self, text: str) -> str:
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def _md_to_html(self, md: str) -> str:
        html = md
        html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
        html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
        html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
        html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
        html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)
        html = re.sub(r"`(.+?)`", r"<code>\1</code>", html)
        html = re.sub(r"^- (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)
        html = re.sub(r"^---$", r"<hr>", html, flags=re.MULTILINE)
        html = re.sub(
            r"\|(.+)\|\n\|[-| ]+\|\n((?:\|.+\|\n?)*)",
            self._convert_table,
            html,
        )
        return html

    def _convert_table(self, match: re.Match) -> str:
        lines = match.group(0).strip().split("\n")
        if len(lines) < 2:
            return match.group(0)
        header_cells = [c.strip() for c in lines[0].strip("|").split("|")]
        body_rows = []
        for line in lines[2:]:
            cells = [c.strip() for c in line.strip("|").split("|")]
            body_rows.append(cells)
        return self.render_table(header_cells, body_rows)
