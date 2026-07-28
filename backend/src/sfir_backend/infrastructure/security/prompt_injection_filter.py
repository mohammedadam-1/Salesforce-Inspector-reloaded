from __future__ import annotations

import re
from typing import Any

import structlog

from sfir_backend.shared.exceptions.application import AuthorizationFailedError

logger = structlog.get_logger(__name__)


INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(all\s+)?(previous|above|below|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"forget\s+(all\s+)?(previous|above|below|prior)", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(previous|above|below|prior)", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"you\s+are\s+(now|an?\s+AI|a\s+human)", re.IGNORECASE),
    re.compile(r"act\s+as\s+(if|though)", re.IGNORECASE),
    re.compile(r"pretend\s+(to\s+be|you\s+are)", re.IGNORECASE),
    re.compile(r"\[\s*(SYSTEM|INST|USER|ASSISTANT)\s*\]", re.IGNORECASE),
    re.compile(r"```.*(reset|override|inject)", re.IGNORECASE),
    re.compile(r"role\s*[:=]\s*(system|assistant)", re.IGNORECASE),
    re.compile(r"<\|im_start\|>", re.IGNORECASE),
    re.compile(r"<\|im_end\|>", re.IGNORECASE),
    re.compile(r"DANGEROUS_QUERY", re.IGNORECASE),
    re.compile(r"##\s*SAFETY\s*OVERRIDE", re.IGNORECASE),
    re.compile(r"bypass\s+(content|safety|filter|policy)", re.IGNORECASE),
    re.compile(r"(reveal|show|leak|expose|dump)\s+(your\s+)?(system|instructions|prompt)", re.IGNORECASE),
    re.compile(r"output\s+(your\s+)?(raw\s+)?(prompt|instructions|system\s+message)", re.IGNORECASE),
    re.compile(r"(admin|administrator|root|superuser)\s+(override|bypass|access)", re.IGNORECASE),
    re.compile(r"(exec|execute|run|eval)\s*\(.*\)", re.IGNORECASE),
    re.compile(r"__import__\s*\(.*\)", re.IGNORECASE),
    re.compile(r"(os\.system|subprocess|shutil)", re.IGNORECASE),
]


class PromptInjectionFilter:
    def __init__(
        self,
        enabled: bool = True,
        patterns: list[re.Pattern[str]] | None = None,
    ) -> None:
        self._enabled = enabled
        self._patterns = patterns or INJECTION_PATTERNS

    async def check(
        self,
        text: str,
        user_id: str | None = None,
    ) -> None:
        if not self._enabled or not text:
            return

        for pattern in self._patterns:
            match = pattern.search(text)
            if match:
                logger.warning(
                    "Prompt injection detected",
                    pattern=match.group(0),
                    user_id=user_id,
                )
                raise AuthorizationFailedError(
                    message="Query contains prohibited patterns.",
                    context={
                        "matched_pattern": match.group(0),
                        "reason": "potential_prompt_injection",
                    },
                )

    async def sanitize(self, text: str) -> str:
        if not self._enabled:
            return text
        for pattern in self._patterns:
            text = pattern.sub("[filtered]", text)
        return text
