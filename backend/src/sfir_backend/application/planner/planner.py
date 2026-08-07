"""Planner — intent detection + retrieval orchestration, planning only.

The planner is the sole consumer of the retrieval engine and never
touches Salesforce, the search index, the graph, or the metadata store
directly. It:

1. detects the question's intent (deterministic, rule-based),
2. extracts the entity the question is about,
3. derives the retrieval request (mode, limit, metadata-type filter),
4. asks the retrieval engine for verified facts,
5. decides whether the evidence is sufficient or a retry is warranted,
6. produces an ExecutionPlan for a downstream answer phase.

The planner never generates answers — only plans.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field

from sfir_backend.application.planner.execution_plan import (
    AnswerStrategy,
    ExecutionPlan,
)
from sfir_backend.application.planner.intent import Intent, IntentDetector
from sfir_backend.application.retrieval.retrieval_engine import (
    RetrievalEngine,
    RetrievalRequest,
    RetrievalResult,
)
from sfir_backend.domain.entities.verified_fact import VerifiedFact

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_.:]*")

_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "can", "component", "components",
        "detail", "details", "description", "docs", "do", "documentation",
        "does", "field", "fields", "find", "for", "guide", "how", "i",
        "in", "is", "it", "me", "metadata", "my", "object", "of", "on",
        "search", "show", "the", "this", "that", "to", "usage", "used",
        "use", "using", "what", "where", "with",
    },
)

_DEFAULT_LIMITS: dict[Intent, int] = {
    Intent.METADATA_LOOKUP: 10,
    Intent.IMPACT_ANALYSIS: 30,
    Intent.DEPENDENCY_DISCOVERY: 30,
    Intent.RELATIONSHIP_QUERY: 30,
    Intent.SEARCH_QUERY: 20,
    Intent.NAVIGATION_QUERY: 5,
    Intent.DOCUMENTATION_QUERY: 10,
}

_METADATA_TYPE_HINTS: list[tuple[str, str]] = [
    ("custom object", "object"),
    ("object", "object"),
    ("apex class", "apex"),
    ("apex", "apex"),
    ("class", "apex"),
    ("trigger", "trigger"),
    ("flow", "flow"),
    ("field", "field"),
    ("profile", "profile"),
    ("permission set", "permission_set"),
    ("permission_set", "permission_set"),
    ("layout", "layout"),
    ("validation rule", "validation_rule"),
    ("dashboard", "dashboard"),
    ("report", "report"),
    ("role", "role"),
    ("queue", "queue"),
    ("email template", "email_template"),
    ("static resource", "static_resource"),
]

_RELATIONSHIP_HEAVY = frozenset(
    {
        Intent.IMPACT_ANALYSIS,
        Intent.DEPENDENCY_DISCOVERY,
        Intent.RELATIONSHIP_QUERY,
    },
)


@dataclass
class PlanningRequest:
    organization_id: uuid.UUID
    question: str
    intent: Intent | None = None
    mode: str | None = None
    limit: int | None = None
    metadata_type: str | None = None
    namespace: str | None = None
    include_neighbors: bool = True
    source_timeout_ms: float = 40.0
    total_timeout_ms: float = 150.0
    max_retries: int = 1


@dataclass
class PlanningResult:
    plan: ExecutionPlan
    elapsed_ms: float = 0.0
    requests_made: list[RetrievalRequest] = field(default_factory=list)


class Planner:
    def __init__(
        self,
        retrieval_engine: RetrievalEngine,
        *,
        intent_detector: IntentDetector | None = None,
    ) -> None:
        self._engine = retrieval_engine
        self._detector = intent_detector or IntentDetector()

    async def plan(self, request: PlanningRequest) -> PlanningResult:
        start = time.monotonic()
        question = (request.question or "").strip()
        if not question:
            return PlanningResult(
                plan=ExecutionPlan(
                    organization_id=request.organization_id,
                    question=request.question or "",
                    intent=Intent.SEARCH_QUERY,
                    confidence=0.0,
                    missing_facts=["empty question"],
                    answer_strategy=AnswerStrategy.NO_ANSWER,
                ),
                elapsed_ms=self._elapsed_ms(start),
            )

        detection = self._detector.detect(question)
        intent = request.intent or detection.intent
        limit = request.limit or _DEFAULT_LIMITS[intent]
        query = self._extract_entity(question)
        mode = request.mode or self._mode_for(intent, query)
        metadata_type = request.metadata_type or self._guess_metadata_type(question)

        requests_made: list[RetrievalRequest] = []
        failures: list[str] = []
        sources_used: list[str] = []
        result = RetrievalResult()
        while len(requests_made) <= request.max_retries:
            current = RetrievalRequest(
                organization_id=request.organization_id,
                query=query,
                mode=mode,
                limit=limit,
                metadata_type=metadata_type,
                namespace=request.namespace,
                source_timeout_ms=request.source_timeout_ms,
                total_timeout_ms=request.total_timeout_ms,
                include_neighbors=(
                    request.include_neighbors and intent is not Intent.NAVIGATION_QUERY
                ),
            )
            requests_made.append(current)
            result = await self._engine.retrieve(current)
            failures.extend(f.error for f in result.failures)
            sources_used.extend(result.sources_used)
            if result.facts:
                break
            if mode == "exact":
                mode = "fuzzy"
                continue
            break

        retry_count = len(requests_made) - 1
        plan = self._build_plan(
            request=request,
            question=question,
            intent=intent,
            detection_confidence=(detection.confidence if request.intent is None else 0.9),
            result=result,
            missing_facts=self._missing_facts(intent, result, query),
            retry_count=retry_count,
            failures=list(dict.fromkeys(failures)),
            sources_used=list(dict.fromkeys(sources_used)),
        )
        return PlanningResult(
            plan=plan,
            elapsed_ms=self._elapsed_ms(start),
            requests_made=requests_made,
        )

    @staticmethod
    def _build_plan(
        *,
        request: PlanningRequest,
        question: str,
        intent: Intent,
        detection_confidence: float,
        result: RetrievalResult,
        missing_facts: list[str],
        retry_count: int,
        failures: list[str],
        sources_used: list[str],
    ) -> ExecutionPlan:
        facts = result.facts
        evidence = Planner._evidence_confidence(intent, facts, missing_facts)
        confidence = round(
            min(0.95, 0.5 * detection_confidence + 0.5 * evidence),
            3,
        )
        return ExecutionPlan(
            organization_id=request.organization_id,
            question=question,
            intent=intent.value,
            confidence=confidence,
            retrieved_facts=facts,
            missing_facts=missing_facts,
            required_citations=[fact.identity for fact in facts],
            answer_strategy=Planner._answer_strategy(intent, facts),
            retry_count=retry_count,
            sources_used=sources_used,
            failures=failures,
        )

    @staticmethod
    def _evidence_confidence(
        intent: Intent,
        facts: list[VerifiedFact],
        missing_facts: list[str],
    ) -> float:
        subject = facts[0] if facts else None
        if subject is None:
            return 0.2
        if intent == Intent.METADATA_LOOKUP:
            return 0.9 if subject.confidence >= 0.7 else 0.5
        if intent in _RELATIONSHIP_HEAVY:
            if not subject.supporting_relationships:
                return 0.5
            return 0.9
        if intent == Intent.NAVIGATION_QUERY:
            return 0.9
        if intent == Intent.DOCUMENTATION_QUERY:
            return 0.9 if subject.description else 0.5
        if intent == Intent.SEARCH_QUERY:
            return 0.9 if facts else 0.2
        return 0.9 if not missing_facts else 0.5

    @staticmethod
    def _answer_strategy(
        intent: Intent,
        facts: list[VerifiedFact],
    ) -> str:
        if not facts:
            return AnswerStrategy.NEEDS_MORE_INFO
        if intent in _RELATIONSHIP_HEAVY and not facts[0].supporting_relationships:
            return AnswerStrategy.NEEDS_MORE_INFO
        if intent == Intent.METADATA_LOOKUP:
            return AnswerStrategy.DESCRIBE_METADATA
        if intent == Intent.IMPACT_ANALYSIS:
            return AnswerStrategy.IMPACT_SUMMARY
        if intent == Intent.DEPENDENCY_DISCOVERY:
            return AnswerStrategy.DEPENDENCY_SUMMARY
        if intent == Intent.RELATIONSHIP_QUERY:
            return AnswerStrategy.RELATIONSHIP_SUMMARY
        if intent == Intent.SEARCH_QUERY:
            return AnswerStrategy.SEARCH_RESULTS
        if intent == Intent.NAVIGATION_QUERY:
            return AnswerStrategy.NAVIGATE_TO
        if intent == Intent.DOCUMENTATION_QUERY:
            if not facts[0].description:
                return AnswerStrategy.NEEDS_MORE_INFO
            return AnswerStrategy.DOCUMENTATION_SUMMARY
        return AnswerStrategy.NEEDS_MORE_INFO

    @staticmethod
    def _missing_facts(
        intent: Intent,
        result: RetrievalResult,
        query: str,
    ) -> list[str]:
        subject = result.facts[0] if result.facts else None
        missing: list[str] = []
        if subject is None:
            if intent == Intent.SEARCH_QUERY:
                missing.append(f"matches for {query}")
            elif intent in _RELATIONSHIP_HEAVY:
                missing.append(f"subject {query}")
            elif intent == Intent.NAVIGATION_QUERY:
                missing.append(f"navigation target {query}")
            elif intent == Intent.DOCUMENTATION_QUERY:
                missing.append(f"documentation for {query}")
            else:
                missing.append(f"metadata for {query}")
            return missing
        if intent in _RELATIONSHIP_HEAVY and not subject.supporting_relationships:
            if intent == Intent.IMPACT_ANALYSIS:
                missing.append(f"dependents of {subject.api_name}")
            elif intent == Intent.DEPENDENCY_DISCOVERY:
                missing.append(f"dependencies of {subject.api_name}")
            else:
                missing.append(f"relationships of {subject.api_name}")
        if intent == Intent.DOCUMENTATION_QUERY and not subject.description:
            missing.append(f"documentation for {subject.api_name}")
        return missing

    @staticmethod
    def _extract_entity(question: str) -> str:
        """Pick the identifier-like token the question is about.

        The retrieval engine matches identifiers, not sentences: "what is
        Account?" becomes the query "Account". Stopwords are skipped so
        trailing filler ("the Account object") cannot win. Falls back to
        the full question when no identifier-like token exists.
        """
        tokens = _IDENTIFIER.findall(question)
        if tokens:
            for token in reversed(tokens):
                if token.lower() not in _STOPWORDS:
                    return token
            return tokens[-1]
        return question

    @staticmethod
    def _mode_for(intent: Intent, query: str) -> str:
        if intent in (Intent.SEARCH_QUERY, Intent.NAVIGATION_QUERY):
            return "fuzzy"
        if intent == Intent.DOCUMENTATION_QUERY:
            return "fuzzy"
        return "exact" if " " not in query else "fuzzy"

    @staticmethod
    def _guess_metadata_type(question: str) -> str | None:
        text = (question or "").strip().lower()
        for hint, metadata_type in _METADATA_TYPE_HINTS:
            if hint in text:
                return metadata_type
        return None

    @staticmethod
    def _elapsed_ms(start: float) -> float:
        return round((time.monotonic() - start) * 1000.0, 2)
