"""Salesforce API rate limiter that tracks limits from response headers.

Salesforce returns per-org rolling rate limits via:
    Sforce-Limit-Info: api-request-limit-per-rolling-period=50000, \
                       api-request-limit-per-rolling-period-remaining=48723

This module tracks these limits and prevents requests when the remaining
budget drops below a configurable threshold.
"""

import asyncio
import time
from collections import defaultdict


class SalesforceRateLimiter:
    """Tracks Salesforce API rate limits per organization.

    Uses the Sforce-Limit-Info response header to maintain awareness
    of remaining API call quota.
    """

    def __init__(self, threshold_percentage: int = 75) -> None:
        self._threshold_pct = max(0, min(100, threshold_percentage))
        self._limits: dict[str, dict[str, int]] = defaultdict(
            lambda: {"limit": 50000, "remaining": 50000, "reset_time": 0}
        )

    def update_from_headers(
        self, org_id: str, headers: dict[str, str]
    ) -> None:
        """Update rate limit tracking from response headers."""
        limit_info = headers.get("Sforce-Limit-Info", "")
        if not limit_info:
            return

        parts = limit_info.split(";")
        for part in parts:
            part = part.strip()
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            key = key.strip()
            value = value.strip()

            if "api-request-limit-per-rolling-period-remaining" in key:
                self._limits[org_id]["remaining"] = int(value)
            elif "api-request-limit-per-rolling-period" in key:
                self._limits[org_id]["limit"] = int(value)

        self._limits[org_id]["reset_time"] = time.time() + 60

    def get_remaining(self, org_id: str) -> int:
        return self._limits[org_id]["remaining"]

    def get_limit(self, org_id: str) -> int:
        return self._limits[org_id]["limit"]

    def is_throttled(self, org_id: str) -> bool:
        """Check if requests should be throttled based on remaining budget."""
        info = self._limits[org_id]
        if info["limit"] == 0:
            return False
        usage_pct = 100 - (info["remaining"] / info["limit"]) * 100
        return usage_pct >= self._threshold_pct

    def estimate_wait(self, org_id: str) -> float:
        """Estimate wait time in seconds before next safe request."""
        if not self.is_throttled(org_id):
            return 0.0
        info = self._limits[org_id]
        reset_in = max(0, info["reset_time"] - time.time())
        if reset_in <= 0:
            return 0.0
        return min(reset_in, 60.0)

    async def wait_if_needed(self, org_id: str) -> None:
        """Wait if the rate limit budget is depleted below threshold."""
        wait = self.estimate_wait(org_id)
        if wait > 0:
            await asyncio.sleep(wait)
