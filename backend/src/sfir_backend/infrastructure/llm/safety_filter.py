from __future__ import annotations

import re
from typing import Any

import structlog

from sfir_backend.domain.ai.models import SafetyCheckResult

logger = structlog.get_logger(__name__)


BLOCKED_PATTERNS: list[re.Pattern] = [
    re.compile(r"(?i)(connect|login|authenticate)\s+(to\s+)?salesforce"),
    re.compile(r"(?i)(parse|extract)\s+(metadata|sobject|sObject)"),
    re.compile(r"(?i)build\s+(a\s+)?dependency\s+graph"),
    re.compile(r"(?i)calculate\s+(impact|risk)\s+analysis"),
    re.compile(r"(?i)(bypass|override|disable)\s+security"),
    re.compile(r"(?i)(drop|delete|truncate|alter)\s+(table|database|schema)"),
    re.compile(r"(?i)execute\s+(anonymous|raw|arbitrary)\s+(apex|sql|soql)"),
    re.compile(r"(?i)access\s+(production|prod)\s+data"),
]

SENSITIVE_CATEGORIES: list[str] = [
    "data_export",
    "credential_access",
    "data_destruction",
    "privilege_escalation",
]


class SafetyFilter:
    def __init__(self) -> None:
        self._blocked_patterns = list(BLOCKED_PATTERNS)
        self._allowed_domains: list[str] = []

    def add_blocked_pattern(self, pattern: str) -> None:
        self._blocked_patterns.append(re.compile(pattern))

    def add_allowed_domain(self, domain: str) -> None:
        self._allowed_domains.append(domain)

    def check_input(self, query: str) -> SafetyCheckResult:
        for pattern in self._blocked_patterns:
            match = pattern.search(query)
            if match:
                logger.warning(
                    "safety_input_blocked",
                    pattern=pattern.pattern,
                    match=match.group(),
                )
                return SafetyCheckResult(
                    passed=False,
                    reason=f"Blocked by pattern: {pattern.pattern}",
                    categories=["restricted_action"],
                    score=1.0,
                )
        return SafetyCheckResult(passed=True)

    def check_output(self, content: str) -> SafetyCheckResult:
        for pattern in self._blocked_patterns:
            match = pattern.search(content)
            if match:
                logger.warning(
                    "safety_output_blocked",
                    pattern=pattern.pattern,
                    match=match.group(),
                )
                return SafetyCheckResult(
                    passed=False,
                    reason=f"Output blocked by pattern: {pattern.pattern}",
                    categories=["restricted_content"],
                    score=0.9,
                )
        return SafetyCheckResult(passed=True)

    def check_context(self, context: dict[str, Any]) -> SafetyCheckResult:
        for key, value in context.items():
            if isinstance(value, str):
                for pattern in self._blocked_patterns:
                    if pattern.search(value):
                        return SafetyCheckResult(
                            passed=False,
                            reason=f"Context blocked: {key} matched {pattern.pattern}",
                            categories=["restricted_context"],
                            score=0.8,
                        )
        return SafetyCheckResult(passed=True)
