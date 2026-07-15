from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import orjson


class CacheSerializer:
    def serialize(self, value: Any) -> bytes:
        return orjson.dumps(
            value,
            default=self._serialize_default,
            option=orjson.OPT_SERIALIZE_NUMPY | orjson.OPT_NAIVE_UTC,
        )

    def deserialize(self, data: bytes) -> Any:
        try:
            return orjson.loads(data)
        except orjson.JSONDecodeError:
            return data.decode("utf-8") if isinstance(data, bytes) else data

    def _serialize_default(self, obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, set):
            return list(obj)
        if isinstance(obj, bytes):
            return obj.decode("utf-8", errors="replace")
        raise TypeError(f"Type {type(obj)} not serializable")
