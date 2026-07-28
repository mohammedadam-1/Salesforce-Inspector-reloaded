"""Cursor-based pagination utilities."""

import base64
import json
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class CursorPage(BaseModel):
    """Generic cursor-based page response."""

    items: list[Any]
    total: int | None = None
    next_cursor: str | None = None
    prev_cursor: str | None = None
    has_more: bool = False

    class Config:
        arbitrary_types_allowed = True


def encode_cursor(value: dict[str, Any]) -> str:
    """Encode a cursor dictionary to a URL-safe string."""
    json_str = json.dumps(value, separators=(",", ":"))
    return base64.urlsafe_b64encode(json_str.encode()).decode()


def decode_cursor(cursor: str) -> dict[str, Any]:
    """Decode a cursor string to a dictionary."""
    try:
        json_str = base64.urlsafe_b64decode(cursor.encode()).decode()
        return json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        return {}
