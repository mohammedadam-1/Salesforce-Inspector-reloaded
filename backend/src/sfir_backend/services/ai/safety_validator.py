"""Safety validator — prevents hallucination and ensures response quality.

Checks:
- Response references actual metadata from the provided context
- No fabricated API names or metadata components
- Risk-appropriate response for modification requests
- Citation accuracy
"""

import re
from typing import Any

import structlog

from sfir_backend.infrastructure.llm.base import LLMResponse

logger = structlog.get_logger(__name__)


class SafetyReport:
    passed: bool
    issues: list[dict[str, Any]]
    risk_level: str

    def __init__(
        self,
        passed: bool = True,
        issues: list[dict[str, Any]] | None = None,
        risk_level: str = "low",
    ) -> None:
        self.passed = passed
        self.issues = issues or []
        self.risk_level = risk_level

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "issues": self.issues,
            "risk_level": self.risk_level,
        }


class SafetyValidator:
    """Validates LLM responses for safety, accuracy, and hallucination prevention."""

    def __init__(self) -> None:
        self._known_api_name_pattern = re.compile(
            r"\b([A-Z][a-zA-Z0-9_]+(?:\.[a-zA-Z][a-zA-Z0-9_]*)?)\b"
        )

    async def validate(
        self,
        response: LLMResponse,
        context: str,
    ) -> SafetyReport:
        """Validate the LLM response against provided context."""
        issues: list[dict[str, Any]] = []
        content = response.content

        # Check 1: Extract API names from response that should be in context
        api_names = self._extract_api_names(content)
        context_api_names = self._extract_api_names(context)

        for name in api_names:
            if name not in context_api_names:
                if self._looks_like_metadata(name):
                    issues.append({
                        "type": "unverified_reference",
                        "severity": "warning",
                        "message": f"Response references '{name}' which was not found in the provided metadata context",
                        "detail": "This may be a hallucination or inferred metadata",
                    })

        # Check 2: Validate citations match actual context
        citation_issues = self._check_citations(content, context)
        issues.extend(citation_issues)

        # Check 3: Check for modification instructions without safety disclaimers
        mod_issues = self._check_modification_safety(content)
        issues.extend(mod_issues)

        # Assess risk level
        risk_level = self._assess_risk(issues)

        return SafetyReport(
            passed=len([i for i in issues if i.get("severity") == "error"]) == 0,
            issues=issues,
            risk_level=risk_level,
        )

    def _extract_api_names(self, text: str) -> set[str]:
        """Extract potential API names from text."""
        names = set()
        patterns = [
            r"\b[A-Z][a-zA-Z0-9]*(?:__c|__r)\b",
            r"\b[A-Z][a-zA-Z0-9]*(?:\.[A-Z][a-zA-Z0-9_]*)?\b",
            r"\b[A-Z][a-zA-Z0-9_]*\b",
        ]
        for pattern in patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                name = match.group(0)
                if name and len(name) > 1:
                    names.add(name)
        return names

    def _looks_like_metadata(self, name: str) -> bool:
        return name.endswith("__c") or name.endswith("__r") or name[0].isupper()

    def _check_citations(self, content: str, context: str) -> list[dict[str, Any]]:
        issues = []
        citation_pattern = re.compile(r"\[([^\]]+)\]")
        citations = citation_pattern.findall(content)
        for citation in citations:
            if citation not in context:
                issues.append({
                    "type": "citation_not_in_context",
                    "severity": "warning",
                    "message": f"Citation '{citation}' not found in provided metadata context",
                })
        return issues

    def _check_modification_safety(self, content: str) -> list[dict[str, Any]]:
        issues = []
        mod_patterns = [
            r"\b(?:modify|change|update|delete|remove|create|add)\s+(?:field|object|metadata)",
            r"\b(?:deploy|push|migrate)\s+(?:to\s+)?(?:production|sandbox)",
        ]
        has_disclaimer = bool(re.search(r"(?:safety|validation|preview|approval|rollback|backup)", content, re.IGNORECASE))
        for pattern in mod_patterns:
            if re.search(pattern, content, re.IGNORECASE) and not has_disclaimer:
                issues.append({
                    "type": "modification_without_disclaimer",
                    "severity": "warning",
                    "message": "Response suggests metadata modification without mentioning safety validation or approval process",
                })
        return issues

    def _assess_risk(self, issues: list[dict[str, Any]]) -> str:
        error_count = len([i for i in issues if i.get("severity") == "error"])
        warning_count = len([i for i in issues if i.get("severity") == "warning"])
        if error_count > 0:
            return "high"
        elif warning_count > 3:
            return "medium"
        return "low"
