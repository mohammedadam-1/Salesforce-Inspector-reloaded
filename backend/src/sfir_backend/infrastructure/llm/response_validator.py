from __future__ import annotations

import json
import re
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class ResponseValidator:
    def __init__(self, max_length: int = 50_000) -> None:
        self._max_length = max_length

    def validate_json_structure(self, content: str, required_sections: list[str] | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {"valid": True, "errors": []}

        if not content or not content.strip():
            result["valid"] = False
            result["errors"].append("Empty response")
            return result

        if len(content) > self._max_length:
            result["valid"] = False
            result["errors"].append(f"Response too long: {len(content)} chars (max {self._max_length})")
        if required_sections:
            for section in required_sections:
                if f"#{section}" not in content and section.lower() not in content.lower():
                    result["errors"].append(f"Missing required section: {section}")
                    result["valid"] = False
        return result

    def validate_json(self, content: str) -> dict[str, Any]:
        result: dict[str, Any] = {"valid": True, "errors": []}
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            result["valid"] = False
            result["errors"].append(f"Invalid JSON: {e.msg}")
        return result

    def check_empty_or_refusal(self, content: str) -> bool:
        refusal_patterns = [
            r"(?i)^(i'?m (sorry|unable|not able)|i cannot|cannot|as an? (ai|language model))",
            r"(?i)^(i don't have|i do not have|no information|insufficient)",
        ]
        for pattern in refusal_patterns:
            if re.match(pattern, content.strip()):
                return True
        return False

    def check_length_limits(self, content: str, max_chars: int | None = None) -> dict[str, Any]:
        limit = max_chars or self._max_length
        if len(content) > limit:
            return {
                "valid": False,
                "length": len(content),
                "max_length": limit,
                "error": f"Response exceeds length limit ({len(content)} > {limit})",
            }
        return {"valid": True, "length": len(content)}


class ResponseFormatter:
    def format_markdown(self, content: str) -> str:
        lines = content.split("\n")
        formatted: list[str] = []
        in_code_block = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                formatted.append(line)
                continue
            if not in_code_block and stripped.startswith("- ") and not stripped.startswith("  "):
                formatted.append(line)
            elif not in_code_block and re.match(r"^\d+\.\s", stripped):
                formatted.append(line)
            elif not in_code_block and stripped and not stripped.startswith("#"):
                formatted.append(f"{line}\n")
            else:
                formatted.append(line)
        return "\n".join(formatted)

    def trim_to_token_limit(self, content: str, max_tokens: int = 4000) -> str:
        tokens = content.split()
        if len(tokens) <= max_tokens:
            return content
        return " ".join(tokens[:max_tokens]) + "\n\n[Response truncated due to length...]"


class ResponseStreamer:
    def __init__(self) -> None:
        self._cancelled: set[str] = set()

    def cancel(self, request_id: str) -> None:
        self._cancelled.add(request_id)

    def is_cancelled(self, request_id: str) -> bool:
        return request_id in self._cancelled

    async def stream_response(
        self,
        content: str,
        request_id: str,
    ) -> str:
        accumulated = ""
        words = content.split(" ")
        for word in words:
            if self.is_cancelled(request_id):
                logger.info("stream_cancelled", request_id=request_id)
                break
            accumulated += word + " "
        return accumulated.strip()
