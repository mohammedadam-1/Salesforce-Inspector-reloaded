"""Intent detection — rule-based, deterministic, no LLM.

The planner detects the user's intent from the question text alone. The
detector scores each supported intent against keyword patterns and picks
the strongest match; when nothing matches it falls back to a generic
search intent with low confidence. Ambiguity between close patterns is
reflected in a lower confidence, never in guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar


class Intent(StrEnum):
    METADATA_LOOKUP = "metadata_lookup"
    IMPACT_ANALYSIS = "impact_analysis"
    DEPENDENCY_DISCOVERY = "dependency_discovery"
    RELATIONSHIP_QUERY = "relationship_query"
    SEARCH_QUERY = "search_query"
    NAVIGATION_QUERY = "navigation_query"
    DOCUMENTATION_QUERY = "documentation_query"


@dataclass
class IntentDetection:
    intent: Intent
    confidence: float


class IntentDetector:
    """Deterministic, rule-based intent classification.

    Every pattern is a (regex, weight) pair; an intent's score is the
    maximum weight among its matching patterns. The winner is the intent
    with the highest score; confidence grows with the margin between the
    winner and the runner-up, so ambiguous questions score low.
    """

    _PATTERNS: ClassVar[dict[Intent, list[tuple[str, float]]]] = {
        Intent.METADATA_LOOKUP: [
            (r"\bwhat is\b", 1.0),
            (r"\bwhat are\b", 1.0),
            (r"\bdescribe\b", 1.2),
            (r"\bdefinition\b", 1.2),
            (r"\bdetails?\b", 1.0),
            (r"\btell me about\b", 1.0),
            (r"\bmetadata\b", 0.8),
            (r"\bfields?\b", 0.6),
            (r"\bcomponents?\b", 0.6),
        ],
        Intent.IMPACT_ANALYSIS: [
            (r"\bimpact\b", 1.5),
            (r"\baffected\b", 1.2),
            (r"\bwhat breaks?\b", 1.2),
            (r"\bside effects?\b", 1.2),
            (r"\bconsequences?\b", 1.0),
            (r"\bdelete\w*\b", 0.5),
            (r"\bremov\w*\b", 0.4),
            (r"\bchange\w*\b", 0.4),
        ],
        Intent.DEPENDENCY_DISCOVERY: [
            (r"\bdepend\w*\b", 1.5),
            (r"\bused by\b", 1.3),
            (r"\buses\b", 0.5),
            (r"\breferences?\b", 1.0),
            (r"\bconsumers?\b", 1.0),
            (r"\bwhere is \w+ used\b", 1.2),
        ],
        Intent.RELATIONSHIP_QUERY: [
            (r"\brelationship\w*\b", 1.4),
            (r"\brelated to\b", 1.3),
            (r"\bconnected\b", 1.0),
            (r"\blinks?\b", 0.8),
            (r"\bparent of\b", 1.2),
            (r"\bchildren of\b", 1.2),
            (r"\btouches\b", 1.0),
            (r"\btarget of\b", 1.0),
            (r"\bsource of\b", 1.0),
        ],
        Intent.SEARCH_QUERY: [
            (r"\bfind\b", 1.0),
            (r"\bsearch\b", 1.2),
            (r"\blooking for\b", 1.0),
            (r"\bwhere can i find\b", 1.2),
        ],
        Intent.NAVIGATION_QUERY: [
            (r"\bwhere is\b", 1.1),
            (r"\bnavigate\w*\b", 1.3),
            (r"\bgo to\b", 1.0),
            (r"\bopen\b", 0.7),
            (r"\btake me to\b", 1.2),
            (r"\blocation\b", 0.8),
        ],
        Intent.DOCUMENTATION_QUERY: [
            (r"\bdocumentation\b", 1.3),
            (r"\bdocs\b", 1.0),
            (r"\bhow do i\b", 1.1),
            (r"\bhow to\b", 1.0),
            (r"\bguide\b", 0.8),
            (r"\bhelp me understand\b", 1.0),
            (r"\bwhat does it do\b", 1.0),
            (r"\bexplain how\b", 1.1),
        ],
    }

    _FALLBACK = Intent.SEARCH_QUERY
    _FALLBACK_CONFIDENCE = 0.4

    def detect(self, question: str) -> IntentDetection:
        text = (question or "").strip().lower()
        if not text:
            return IntentDetection(self._FALLBACK, 0.0)

        scores: dict[Intent, float] = {}
        for intent, patterns in self._PATTERNS.items():
            best = 0.0
            for pattern, weight in patterns:
                if re.search(pattern, text):
                    best = max(best, weight)
            scores[intent] = best

        winner, top = max(scores.items(), key=lambda item: item[1])
        if top == 0.0:
            return IntentDetection(self._FALLBACK, self._FALLBACK_CONFIDENCE)

        runner_up = max(
            (score for intent, score in scores.items() if intent is not winner),
            default=0.0,
        )
        margin = top - runner_up
        confidence = round(min(0.95, 0.55 + 0.40 * min(1.0, margin)), 3)
        return IntentDetection(winner, confidence)
