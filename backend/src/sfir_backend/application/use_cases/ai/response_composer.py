from __future__ import annotations

from typing import Any

from sfir_backend.domain.ai.models import ConfidenceScore, SuggestedAction

_DEFAULT_SECTIONS = ["summary", "evidence", "affected_components", "risk", "recommendations"]


class ResponseComposer:
    def compose(
        self,
        content: str,
        citations: list[dict[str, Any]] | None = None,
        confidence: ConfidenceScore | None = None,
        affected_components: list[dict[str, str]] | None = None,
        recommendations: list[str] | None = None,
        next_actions: list[SuggestedAction] | None = None,
        risk: str | None = None,
        query_type: str = "general",
    ) -> str:
        parts: list[str] = []

        summary = self._extract_summary(content)
        if summary:
            parts.append(f"## Summary\n\n{summary}")

        evidence = self._build_evidence(content, citations)
        if evidence:
            parts.append(evidence)

        if affected_components:
            parts.append(self._format_affected_components(affected_components))

        if risk:
            parts.append(f"## Risk Assessment\n\n{risk}")

        if recommendations:
            parts.append(self._format_recommendations(recommendations))

        if next_actions:
            parts.append(self._format_next_actions(next_actions))

        if confidence:
            parts.append(self._format_confidence(confidence))

        if not parts:
            return content

        return "\n\n---\n\n".join(parts)

    def _extract_summary(self, content: str) -> str:
        lines = content.strip().split("\n")
        summary_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                if summary_lines:
                    break
                continue
            if stripped.startswith("#"):
                break
            if any(stripped.startswith(p) for p in ["---", "***", "___"]):
                break
            summary_lines.append(line)
            if len(summary_lines) >= 3:
                break
        return " ".join(summary_lines).strip() if summary_lines else ""

    def _build_evidence(
        self,
        content: str,
        citations: list[dict[str, Any]] | None,
    ) -> str:
        lines: list[str] = ["## Evidence"]
        if citations:
            for c in citations[:10]:
                title = c.get("title") or c.get("source_name", "Reference")
                source_id = c.get("source_id", "")
                source_type = c.get("source_type", "reference")
                lines.append(f"- **{title}** ({source_type}: `{source_id}`)")
            if len(citations) > 10:
                lines.append(f"- *... and {len(citations) - 10} more*")

        has_brackets = "[" in content and "]" in content and ":" in content
        if not citations and not has_brackets:
            lines.append("*No specific references cited.*")

        return "\n".join(lines)

    def _format_affected_components(self, components: list[dict[str, str]]) -> str:
        lines = ["## Affected Components"]
        grouped: dict[str, list[str]] = {}
        for c in components:
            ctype = c.get("component_type", "Unknown")
            cname = c.get("component_name", c.get("name", "Unknown"))
            grouped.setdefault(ctype, []).append(cname)

        for ctype, names in sorted(grouped.items()):
            lines.append(f"- **{ctype}** ({len(names)}): " + ", ".join(sorted(names)[:10]))
            if len(names) > 10:
                lines[-1] += f" +{len(names) - 10} more"

        return "\n".join(lines)

    def _format_recommendations(self, recommendations: list[str]) -> str:
        lines = ["## Recommendations"]
        for i, rec in enumerate(recommendations, 1):
            lines.append(f"{i}. {rec}")
        return "\n".join(lines)

    def _format_next_actions(self, actions: list[SuggestedAction]) -> str:
        lines = ["## Next Steps"]
        for a in actions:
            query_str = f" — `{a.query}`" if a.query else ""
            lines.append(f"- **{a.label}**: {a.description}{query_str}")
        return "\n".join(lines)

    def _format_confidence(self, confidence: ConfidenceScore) -> str:
        level_icon = {"high": "🟢", "medium": "🟡", "low": "🔴"}
        icon = level_icon.get(confidence.level, "⚪")
        reasons = "; ".join(confidence.reasons[:3])
        return f"## Confidence\n\n{icon} **{confidence.level.upper()}** ({confidence.score:.0%})\n\n{reasons}"

    def compute_metadata(
        self,
        content: str,
        citations: list[dict[str, Any]] | None = None,
        confidence: ConfidenceScore | None = None,
        affected_components: list[dict[str, str]] | None = None,
        risk: str | None = None,
        next_actions: list[SuggestedAction] | None = None,
    ) -> dict[str, Any]:
        return {
            "summary": self._extract_summary(content),
            "evidence_count": len(citations) if citations else 0,
            "affected_component_count": len(affected_components) if affected_components else 0,
            "has_risk_assessment": risk is not None,
            "confidence_level": confidence.level if confidence else None,
            "next_action_count": len(next_actions) if next_actions else 0,
        }
