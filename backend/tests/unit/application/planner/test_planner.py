"""Unit tests for the planner.

The planner must plan and nothing else: these tests drive it with a fake
retrieval engine and assert the exact retrieval requests it builds, the
evidence rules it applies, and the ExecutionPlan it produces. The planner
never touches repositories, Salesforce, or the LLM.
"""

import asyncio
import uuid

import pytest

from sfir_backend.application.planner.execution_plan import AnswerStrategy
from sfir_backend.application.planner.intent import Intent
from sfir_backend.application.planner.planner import Planner, PlanningRequest
from sfir_backend.application.retrieval.retrieval_engine import (
    RetrievalRequest,
    RetrievalResult,
    SourceFailure,
)
from sfir_backend.domain.entities.verified_fact import (
    SupportingRelationship,
    VerifiedFact,
)


def _relationship(identity: str, relationship_type: str, direction: str):
    return SupportingRelationship(
        identity=identity,
        api_name=identity,
        metadata_type="object",
        relationship_type=relationship_type,
        direction=direction,
    )


def _fact(
    identity: str = "Account",
    confidence: float = 0.9,
    description: str = "Account object holding customers.",
    relationships: tuple[SupportingRelationship, ...] = (),
    metadata_type: str = "object",
) -> VerifiedFact:
    return VerifiedFact(
        identity=identity,
        metadata_type=metadata_type,
        api_name=identity,
        developer_name=identity,
        display_name=identity,
        description=description,
        namespace=None,
        source="search_index,canonical",
        confidence=confidence,
        search_score=1.0,
        relationship_score=1,
        reference_count=0,
        graph_distance=0,
        supporting_relationships=list(relationships),
    )


class FakeEngine:
    """Records retrieval requests; serves configured results in order."""

    def __init__(self, *results: RetrievalResult) -> None:
        self._results = list(results) or [RetrievalResult()]
        self.calls: list[RetrievalRequest] = []

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        self.calls.append(request)
        result = self._results.pop(0)
        if not self._results:
            self._results.append(result)
        return result


def _org() -> uuid.UUID:
    return uuid.uuid4()


@pytest.mark.asyncio
async def test_plan_metadata_lookup_builds_exact_request() -> None:
    engine = FakeEngine(RetrievalResult(facts=[_fact(confidence=0.9)]))
    planner = Planner(engine)
    org = _org()

    result = await planner.plan(
        PlanningRequest(organization_id=org, question="what is Account"),
    )

    plan = result.plan
    assert plan.intent == "metadata_lookup"
    assert plan.confidence >= 0.9
    assert plan.answer_strategy == AnswerStrategy.DESCRIBE_METADATA
    assert [f.identity for f in plan.retrieved_facts] == ["Account"]
    assert plan.required_citations == ["Account"]
    assert plan.retry_count == 0
    assert plan.organization_id == org
    assert len(result.requests_made) == 1
    request = result.requests_made[0]
    assert request.query == "Account"
    assert request.mode == "exact"
    assert request.limit == 10
    assert request.metadata_type is None
    assert request.include_neighbors is True
    assert request.organization_id == org
    assert engine.calls == [request]


@pytest.mark.asyncio
async def test_plan_metadata_type_hint_flows_into_request() -> None:
    engine = FakeEngine(RetrievalResult(facts=[_fact()]))
    planner = Planner(engine)

    result = await planner.plan(
        PlanningRequest(
            organization_id=_org(),
            question="what is the Account object",
        ),
    )

    assert result.requests_made[0].metadata_type == "object"


@pytest.mark.asyncio
async def test_plan_impact_analysis_builds_neighbor_request() -> None:
    rel = _relationship("Opportunity", "references", "incoming")
    engine = FakeEngine(
        RetrievalResult(facts=[_fact(relationships=(rel,))]),
    )
    planner = Planner(engine)

    result = await planner.plan(
        PlanningRequest(
            organization_id=_org(),
            question="what is the impact of deleting Account",
        ),
    )

    plan = result.plan
    assert plan.intent == "impact_analysis"
    assert plan.answer_strategy == AnswerStrategy.IMPACT_SUMMARY
    assert plan.required_citations == ["Account"]
    request = result.requests_made[0]
    assert request.query == "Account"
    assert request.mode == "exact"
    assert request.limit == 30
    assert request.include_neighbors is True


@pytest.mark.asyncio
async def test_plan_navigation_disables_neighbors_and_limits() -> None:
    engine = FakeEngine(RetrievalResult(facts=[_fact()]))
    planner = Planner(engine)

    result = await planner.plan(
        PlanningRequest(organization_id=_org(), question="where is Account"),
    )

    assert result.plan.intent == "navigation_query"
    assert result.plan.answer_strategy == AnswerStrategy.NAVIGATE_TO
    request = result.requests_made[0]
    assert request.mode == "fuzzy"
    assert request.limit == 5
    assert request.include_neighbors is False


@pytest.mark.asyncio
async def test_plan_search_uses_fuzzy_entity_query() -> None:
    engine = FakeEngine(RetrievalResult(facts=[_fact()]))
    planner = Planner(engine)

    result = await planner.plan(
        PlanningRequest(organization_id=_org(), question="search for flows"),
    )

    assert result.plan.intent == "search_query"
    request = result.requests_made[0]
    assert request.query == "flows"
    assert request.mode == "fuzzy"


@pytest.mark.asyncio
async def test_plan_retries_exact_with_fuzzy_on_empty() -> None:
    engine = FakeEngine(
        RetrievalResult(facts=[]),
        RetrievalResult(facts=[_fact(confidence=0.8)]),
    )
    planner = Planner(engine)

    result = await planner.plan(
        PlanningRequest(organization_id=_org(), question="what is Account"),
    )

    assert len(result.requests_made) == 2
    assert result.requests_made[0].mode == "exact"
    assert result.requests_made[1].mode == "fuzzy"
    assert result.plan.retry_count == 1
    assert result.plan.answer_strategy == AnswerStrategy.DESCRIBE_METADATA


@pytest.mark.asyncio
async def test_plan_no_retry_when_first_attempt_finds_facts() -> None:
    engine = FakeEngine(RetrievalResult(facts=[_fact()]))
    planner = Planner(engine)

    result = await planner.plan(
        PlanningRequest(organization_id=_org(), question="what is Account"),
    )

    assert len(result.requests_made) == 1
    assert result.plan.retry_count == 0


@pytest.mark.asyncio
async def test_plan_disables_retry_with_max_retries_zero() -> None:
    engine = FakeEngine(RetrievalResult(facts=[]))
    planner = Planner(engine)

    result = await planner.plan(
        PlanningRequest(
            organization_id=_org(),
            question="what is Account",
            max_retries=0,
        ),
    )

    assert len(result.requests_made) == 1
    assert result.plan.retry_count == 0
    assert result.plan.answer_strategy == AnswerStrategy.NEEDS_MORE_INFO
    assert result.plan.missing_facts == ["metadata for Account"]
    assert result.plan.required_citations == []
    assert result.plan.confidence < 0.7


@pytest.mark.asyncio
async def test_plan_relationship_intent_without_relationships_is_incomplete() -> None:
    engine = FakeEngine(RetrievalResult(facts=[_fact(relationships=())]))
    planner = Planner(engine)

    result = await planner.plan(
        PlanningRequest(
            organization_id=_org(),
            question="what is the impact of deleting Account",
        ),
    )

    plan = result.plan
    assert plan.answer_strategy == AnswerStrategy.NEEDS_MORE_INFO
    assert plan.missing_facts == ["dependents of Account"]
    assert plan.confidence < 0.8


@pytest.mark.asyncio
async def test_plan_dependency_strategy() -> None:
    rel = _relationship("Opportunity", "references", "incoming")
    engine = FakeEngine(RetrievalResult(facts=[_fact(relationships=(rel,))]))
    planner = Planner(engine)

    result = await planner.plan(
        PlanningRequest(organization_id=_org(), question="what depends on Account"),
    )

    assert result.plan.intent == "dependency_discovery"
    assert result.plan.answer_strategy == AnswerStrategy.DEPENDENCY_SUMMARY


@pytest.mark.asyncio
async def test_plan_documentation_requires_description() -> None:
    engine = FakeEngine(RetrievalResult(facts=[_fact(description="")]))
    planner = Planner(engine)

    result = await planner.plan(
        PlanningRequest(
            organization_id=_org(),
            question="show me documentation for Account",
        ),
    )

    plan = result.plan
    assert plan.intent == "documentation_query"
    assert plan.answer_strategy == AnswerStrategy.NEEDS_MORE_INFO
    assert plan.missing_facts == ["documentation for Account"]


@pytest.mark.asyncio
async def test_plan_documentation_with_description_plans_summary() -> None:
    engine = FakeEngine(
        RetrievalResult(facts=[_fact(description="Full usage docs.")]),
    )
    planner = Planner(engine)

    result = await planner.plan(
        PlanningRequest(
            organization_id=_org(),
            question="show me documentation for Account",
        ),
    )

    assert result.plan.answer_strategy == AnswerStrategy.DOCUMENTATION_SUMMARY


@pytest.mark.asyncio
async def test_plan_unknown_question_low_confidence_no_evidence() -> None:
    engine = FakeEngine(RetrievalResult(facts=[]))
    planner = Planner(engine)

    result = await planner.plan(
        PlanningRequest(organization_id=_org(), question="asdfghjkl"),
    )

    plan = result.plan
    assert plan.intent == "search_query"
    assert plan.answer_strategy == AnswerStrategy.NEEDS_MORE_INFO
    assert plan.confidence < 0.4
    assert plan.missing_facts == ["matches for asdfghjkl"]


@pytest.mark.asyncio
async def test_plan_empty_question_returns_no_answer_without_engine_call() -> None:
    engine = FakeEngine()
    planner = Planner(engine)

    result = await planner.plan(
        PlanningRequest(organization_id=_org(), question="   "),
    )

    assert result.plan.answer_strategy == AnswerStrategy.NO_ANSWER
    assert result.plan.confidence == 0.0
    assert result.plan.missing_facts == ["empty question"]
    assert result.requests_made == []
    assert engine.calls == []


@pytest.mark.asyncio
async def test_plan_explicit_intent_overrides_detection() -> None:
    rel = _relationship("Opportunity", "references", "incoming")
    engine = FakeEngine(RetrievalResult(facts=[_fact(relationships=(rel,))]))
    planner = Planner(engine)

    result = await planner.plan(
        PlanningRequest(
            organization_id=_org(),
            question="what is Account",
            intent=Intent.IMPACT_ANALYSIS,
        ),
    )

    assert result.plan.intent == "impact_analysis"
    assert result.plan.answer_strategy == AnswerStrategy.IMPACT_SUMMARY
    assert result.plan.confidence >= 0.7


@pytest.mark.asyncio
async def test_plan_citations_and_sources_collected_from_result() -> None:
    first = _fact(identity="Account")
    second = _fact(identity="Opportunity")
    engine = FakeEngine(
        RetrievalResult(
            facts=[first, second],
            sources_used=["search_index", "canonical", "graph"],
            failures=[SourceFailure(source="search_index", error="search boom")],
        ),
    )
    planner = Planner(engine)

    result = await planner.plan(
        PlanningRequest(organization_id=_org(), question="find Account"),
    )

    assert result.plan.required_citations == ["Account", "Opportunity"]
    assert result.plan.sources_used == ["search_index", "canonical", "graph"]
    assert result.plan.failures == ["search boom"]


@pytest.mark.asyncio
async def test_plan_keeps_organization_isolated() -> None:
    org = _org()
    engine = FakeEngine(RetrievalResult(facts=[_fact()]))
    planner = Planner(engine)

    result = await planner.plan(
        PlanningRequest(organization_id=org, question="what is Account"),
    )

    assert result.plan.organization_id == org
    assert all(
        request.organization_id == org for request in result.requests_made
    )


@pytest.mark.asyncio
async def test_plan_concurrent_requests_are_safe() -> None:
    engine = FakeEngine(RetrievalResult(facts=[_fact()]))
    planner = Planner(engine)

    questions = [f"what is Account{i}" for i in range(25)]
    results = await asyncio.gather(
        *(
            planner.plan(PlanningRequest(organization_id=_org(), question=q))
            for q in questions
        ),
    )

    assert len(results) == 25
    assert len(engine.calls) == 25
    for result, question in zip(results, questions, strict=True):
        assert result.plan.question == question
        assert result.plan.answer_strategy == AnswerStrategy.DESCRIBE_METADATA
        assert result.plan.required_citations == ["Account"]
