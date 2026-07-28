from __future__ import annotations

from typing import Any

from sfir_backend.domain.ai.models import SuggestedAction


class NextActionGenerator:
    def generate(
        self,
        query: str,
        response_type: str,
        context: dict[str, Any] | None = None,
    ) -> list[SuggestedAction]:
        actions: list[SuggestedAction] = []
        q = query.lower()

        if "explain" in q or "what is" in q:
            actions.append(self._action("Analyze Impact", "Find what depends on this component", f"Find impact of {self._extract_subject(q)}"))
            actions.append(self._action("View Dependencies", "Show dependency graph", f"Show dependencies for {self._extract_subject(q)}"))
            actions.append(self._action("Generate Documentation", "Create documentation", f"Document {self._extract_subject(q)}"))
        elif "delete" in q or "remove" in q:
            actions.append(self._action("Full Impact Analysis", "Comprehensive deletion impact", f"Analyze deletion impact of {self._extract_subject(q)}"))
            actions.append(self._action("Find Dependencies", "What references this", f"Find dependencies of {self._extract_subject(q)}"))
            actions.append(self._action("Risk Assessment", "Evaluate deployment risk", f"Assess deployment risk for {self._extract_subject(q)}"))
        elif "dependency" in q or "reference" in q or "use" in q:
            actions.append(self._action("Impact Analysis", "What breaks if changed", f"Find impact of {self._extract_subject(q)}"))
            actions.append(self._action("Visualize Graph", "See the dependency graph", f"Show dependency graph for {self._extract_subject(q)}"))
            actions.append(self._action("Reverse Dependencies", "What this depends on", f"Find reverse dependencies of {self._extract_subject(q)}"))
        elif "flow" in q:
            actions.append(self._action("Explain This Flow", "Step-by-step explanation", f"Explain {self._extract_subject(q)}"))
            actions.append(self._action("Flow Dependencies", "What this flow uses", f"Show dependencies of {self._extract_subject(q)}"))
            actions.append(self._action("Find Duplicate Automation", "Detect overlapping flows", "Find duplicate automation"))
        elif "apex" in q or "class" in q:
            actions.append(self._action("Code Review", "Analyze code quality", f"Review {self._extract_subject(q)}"))
            actions.append(self._action("SOQL Performance", "Check query efficiency", f"Check SOQL in {self._extract_subject(q)}"))
            actions.append(self._action("Governor Limits", "Check limit usage", f"Check governor limits in {self._extract_subject(q)}"))
        elif "security" in q or "permission" in q:
            actions.append(self._action("Security Audit", "Review security posture", f"Audit security for {self._extract_subject(q)}"))
            actions.append(self._action("Permission Analysis", "Who can access what", f"Analyze permissions for {self._extract_subject(q)}"))
            actions.append(self._action("Field Accessibility", "Check field-level security", f"Check field accessibility for {self._extract_subject(q)}"))
        elif "document" in q or "documentation" in q:
            actions.append(self._action("Export Documentation", "Download as document", f"Export documentation for {self._extract_subject(q)}"))
            actions.append(self._action("Architecture Overview", "View system architecture", f"Show architecture overview for {self._extract_subject(q)}"))
            actions.append(self._action("Relationship Map", "See component relationships", f"Show relationships for {self._extract_subject(q)}"))
        elif "deploy" in q or "risk" in q:
            actions.append(self._action("Detailed Risk Report", "Full risk breakdown", f"Analyze deployment risk for {self._extract_subject(q)}"))
            actions.append(self._action("Change Simulation", "Simulate the change", f"Simulate changes to {self._extract_subject(q)}"))
            actions.append(self._action("Rollback Plan", "Prepare rollback strategy", f"Create rollback plan for {self._extract_subject(q)}"))
        elif "soql" in q or "query" in q or "performance" in q:
            actions.append(self._action("Query Plan", "View query execution plan", f"Show query plan for {self._extract_subject(q)}"))
            actions.append(self._action("Index Analysis", "Check index usage", f"Analyze indexes for {self._extract_subject(q)}"))
            actions.append(self._action("Optimization Suggestions", "Improve query performance", f"Optimize {self._extract_subject(q)}"))
        elif "validation" in q or "formula" in q:
            actions.append(self._action("Field References", "Find field usage", f"Find field references in {self._extract_subject(q)}"))
            actions.append(self._action("Cross-Object Impact", "Check related objects", f"Check cross-object impact of {self._extract_subject(q)}"))
            actions.append(self._action("Duplicate Detection", "Find similar rules", "Find duplicate automation"))
        elif "find" in q or "search" in q or "where" in q:
            actions.append(self._action("Advanced Search", "Narrow the search", f"Search {self._extract_subject(q)}"))
            actions.append(self._action("Global Search", "Search all metadata", f"Global search for {self._extract_subject(q)}"))
            actions.append(self._action("View in Graph", "See in dependency graph", f"Show {self._extract_subject(q)} in dependency graph"))
        else:
            actions.append(self._action("Explain", "Understand this component", f"Explain {self._extract_subject(q) or 'this'}"))
            actions.append(self._action("Find Dependencies", "What references this", f"Find dependencies of {self._extract_subject(q) or 'this'}"))
            actions.append(self._action("Generate Documentation", "Create documentation", f"Document {self._extract_subject(q) or 'this'}"))

        return actions[:4]

    def _action(self, label: str, description: str, query: str | None = None) -> SuggestedAction:
        return SuggestedAction(label=label, description=description, query=query or label)

    def _extract_subject(self, query: str) -> str:
        import re
        patterns = [
            r"(?:explain|analyze|review|document|find|show|check)\s+(?:the\s+)?([A-Z][a-zA-Z0-9_.]+)",
            r"(?:delete|remove|rename|change|modify)\s+(?:the\s+)?([A-Z][a-zA-Z0-9_.]+)",
            r"(?:impact|dependencies|references)\s+(?:of|for|on)\s+(?:the\s+)?([A-Z][a-zA-Z0-9_.]+)",
            r"(?:what|who|which)\s+(?:is|uses|references|depends)\s+([A-Z][a-zA-Z0-9_.]+)",
            r"\b([A-Z][a-zA-Z0-9_]{2,})\b",
        ]
        for pattern in patterns:
            m = re.search(pattern, query)
            if m:
                return m.group(1)
        return ""
