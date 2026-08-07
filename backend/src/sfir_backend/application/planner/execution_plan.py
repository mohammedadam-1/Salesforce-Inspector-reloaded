"""ExecutionPlan — the planner's only output.

A plan describes what a later answer phase should do: which intent was
detected, how confident the plan is, which verified facts were retrieved
as evidence, what is still missing, which facts must be cited, and which
answer strategy to follow. The planner never produces answers — only
plans.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from sfir_backend.domain.entities.verified_fact import VerifiedFact


class AnswerStrategy(StrEnum):
    DESCRIBE_METADATA = "describe_metadata"
    IMPACT_SUMMARY = "impact_summary"
    DEPENDENCY_SUMMARY = "dependency_summary"
    RELATIONSHIP_SUMMARY = "relationship_summary"
    SEARCH_RESULTS = "search_results"
    NAVIGATE_TO = "navigate_to"
    DOCUMENTATION_SUMMARY = "documentation_summary"
    NEEDS_MORE_INFO = "needs_more_info"
    NO_ANSWER = "no_answer"


@dataclass
class ExecutionPlan:
    organization_id: uuid.UUID
    question: str
    intent: str
    confidence: float
    retrieved_facts: list[VerifiedFact] = field(default_factory=list)
    missing_facts: list[str] = field(default_factory=list)
    required_citations: list[str] = field(default_factory=list)
    answer_strategy: str = AnswerStrategy.NO_ANSWER
    retry_count: int = 0
    sources_used: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
