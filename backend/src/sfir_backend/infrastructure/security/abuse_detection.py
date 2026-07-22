from __future__ import annotations

import contextlib
import time
import uuid
from collections import defaultdict
from typing import Any

from sfir_backend.domain.security.models import (
    AbusePattern,
    AbusePatternType,
    SecurityEventType,
)


class AbuseDetector:
    def __init__(self) -> None:
        self._patterns: list[AbusePattern] = []
        self._event_store: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._reporters: list[Any] = []

        self._register_default_patterns()

    def _register_default_patterns(self) -> None:
        self.register_pattern(AbusePattern(
            pattern_type=AbusePatternType.BRUTE_FORCE,
            criteria={"event_type": SecurityEventType.USER_LOGIN_FAILED},
            threshold=10,
            window_seconds=300,
            action="temporary_block",
        ))
        self.register_pattern(AbusePattern(
            pattern_type=AbusePatternType.RAPID_FIRE,
            criteria={"event_type": None},
            threshold=100,
            window_seconds=60,
            action="throttle",
        ))
        self.register_pattern(AbusePattern(
            pattern_type=AbusePatternType.TOKEN_REUSE,
            criteria={"event_type": SecurityEventType.TOKEN_REVOKED},
            threshold=5,
            window_seconds=3600,
            action="alert",
        ))
        self.register_pattern(AbusePattern(
            pattern_type=AbusePatternType.SCRAPING,
            criteria={"resource_type": "search"},
            threshold=200,
            window_seconds=300,
            action="temporary_block",
        ))

    def register_pattern(self, pattern: AbusePattern) -> None:
        self._patterns.append(pattern)

    def register_reporter(self, reporter: Any) -> None:
        self._reporters.append(reporter)

    def record_event(
        self,
        user_id: uuid.UUID | None,
        ip_address: str,
        event_type: SecurityEventType | None = None,
        resource_type: str = "",
        metadata: dict | None = None,
    ) -> list[AbusePattern]:
        identifier = str(user_id) if user_id else ip_address
        now = time.time()

        self._event_store[identifier].append({
            "timestamp": now,
            "event_type": event_type,
            "resource_type": resource_type,
            "metadata": metadata or {},
        })

        return self._detect_patterns(identifier, now)

    def _detect_patterns(
        self, identifier: str, now: float,
    ) -> list[AbusePattern]:
        triggered: list[AbusePattern] = []
        events = self._event_store[identifier]

        window_start = now - max(
            (p.window_seconds for p in self._patterns), default=3600,
        )
        recent = [e for e in events if e["timestamp"] > window_start]
        self._event_store[identifier] = recent

        for pattern in self._patterns:
            matching = self._count_matching(recent, pattern.criteria)
            if matching >= pattern.threshold:
                triggered.append(pattern)

        return triggered

    def _count_matching(
        self,
        events: list[dict[str, Any]],
        criteria: dict[str, Any],
    ) -> int:
        count = 0
        for event in events:
            matches = True
            for key, value in criteria.items():
                if value is not None and event.get(key) != value:
                    matches = False
                    break
            if matches:
                count += 1
        return count

    def _notify_reporters(
        self, pattern: AbusePattern, identifier: str,
    ) -> None:
        for reporter in self._reporters:
            with contextlib.suppress(Exception):
                reporter(pattern, identifier)

    def cleanup(self, max_age_seconds: int = 3600) -> None:
        now = time.time()
        cutoff = now - max_age_seconds
        for identifier in list(self._event_store.keys()):
            self._event_store[identifier] = [
                e for e in self._event_store[identifier]
                if e["timestamp"] > cutoff
            ]
            if not self._event_store[identifier]:
                del self._event_store[identifier]
