"""Unit tests for the citation validator.

The validator is pure and in-memory: it consumes only an ExecutionPlan
and its VerifiedFacts, never touching Salesforce, the search index, the
canonical store, or the graph. These tests drive it with hand-built
plans covering every evidence rule: missing evidence, deleted metadata,
broken relationships, duplicate facts, low/high confidence, coverage,
ranking, ordering, tenant isolation, and concurrency.
"""

import asyncio
import uuid

import pytest

from sfir_backend.application.planner import ExecutionPlan
from sfir_backend.application.validator import (
    CitationValidator,
    MissingEvidence,
    MissingReason,
)
from sfir_backend.domain.entities.verified_fact import (
    SupportingRelationship,
    VerifiedFact,
)


def _relationship(
    identity: str,
    relationship_type: str = "references",
    direction: str = "incoming",
) -> SupportingRelationship:
    return SupportingRelationship(
        identity=identity,
        api_name=identity,
        metadata_type="object",
        relationship_type=relationship_type,
        direction=direction,
    )


def _fact(
    identity: str,
    *,
    confidence: float = 0.9,
    source: str = "search_index,canonical",
    search_score: float = 1.0,
    relationships: tuple[SupportingRelationship, ...] = (),
    metadata: dict | None = None,
) -> VerifiedFact:
    return VerifiedFact(
        identity=identity,
        metadata_type="object",
        api_name=identity,
        developer_name=identity,
        display_name=identity,
        description="desc",
        namespace=None,
        source=source,
        confidence=confidence,
        search_score=search_score,
        relationship_score=1,
        reference_count=0,
        graph_distance=0,
        supporting_relationships=list(relationships),
        supporting_metadata=metadata or {},
    )


def _plan(
    facts: list[VerifiedFact],
    *,
    citations: list[str] | None = None,
    intent: str = "metadata_lookup",
    organization_id: uuid.UUID | None = None,
    question: str = "what is Account",
    confidence: float = 0.9,
) -> ExecutionPlan:
    return ExecutionPlan(
        organization_id=organization_id or uuid.uuid4(),
        question=question,
        intent=intent,
        confidence=confidence,
        retrieved_facts=facts,
        missing_facts=[],
        required_citations=citations or [fact.identity for fact in facts],
        answer_strategy="describe_metadata",
        retry_count=0,
        sources_used=["search_index", "canonical"],
        failures=[],
    )


@pytest.mark.asyncio
async def test_validate_high_confidence_full_coverage() -> None:
    facts = [_fact("obj-Account", confidence=0.9), _fact("obj-Contact", confidence=0.7)]
    package = await CitationValidator().validate(
        _plan(facts, citations=["obj-Account", "obj-Contact"])
    )

    assert [f.identity for f in package.verified_facts] == [
        "obj-Account",
        "obj-Contact",
    ]
    assert package.required_citations == ["obj-Account", "obj-Contact"]
    assert package.coverage == 1.0
    assert package.confidence == 0.8
    assert package.missing_evidence == []
    assert package.supporting_metadata == {
        "obj-Account": {},
        "obj-Contact": {},
    }


@pytest.mark.asyncio
async def test_validate_missing_citation_reported() -> None:
    package = await CitationValidator().validate(
        _plan([_fact("obj-Account")], citations=["obj-Account", "obj-Contact"])
    )

    assert [f.identity for f in package.verified_facts] == ["obj-Account"]
    assert package.coverage == 0.5
    assert package.missing_evidence == [MissingEvidence("obj-Contact", MissingReason.NOT_RETRIEVED)]


@pytest.mark.asyncio
async def test_validate_deleted_metadata_removed() -> None:
    stale = _fact("obj-Account", source="search_index")
    package = await CitationValidator().validate(_plan([stale]))

    assert package.verified_facts == []
    assert package.coverage == 0.0
    assert package.confidence == 0.0
    assert package.missing_evidence == [
        MissingEvidence("obj-Account", MissingReason.METADATA_DELETED)
    ]


@pytest.mark.asyncio
async def test_validate_low_confidence_removed_neighbor_survives() -> None:
    weak = _fact("obj-Account", confidence=0.25)
    neighbor = _fact("trg-BillingProcessor", confidence=0.35, source="graph")
    package = await CitationValidator().validate(
        _plan([weak, neighbor], citations=["obj-Account", "trg-BillingProcessor"])
    )

    assert [f.identity for f in package.verified_facts] == ["trg-BillingProcessor"]
    assert package.coverage == 0.5
    assert package.missing_evidence == [
        MissingEvidence("obj-Account", MissingReason.LOW_CONFIDENCE)
    ]


@pytest.mark.asyncio
async def test_validate_configurable_confidence_threshold() -> None:
    neighbor = _fact("trg-BillingProcessor", confidence=0.35, source="graph")
    validator = CitationValidator(min_fact_confidence=0.5)
    package = await validator.validate(_plan([neighbor]))

    assert package.verified_facts == []
    assert package.missing_evidence == [
        MissingEvidence("trg-BillingProcessor", MissingReason.LOW_CONFIDENCE)
    ]


@pytest.mark.asyncio
async def test_validate_duplicate_facts_keep_strongest() -> None:
    weak = _fact("obj-Account", confidence=0.5)
    strong = _fact("obj-Account", confidence=0.9)
    package = await CitationValidator().validate(_plan([weak, strong]))

    assert [f.identity for f in package.verified_facts] == ["obj-Account"]
    assert package.verified_facts[0].confidence == 0.9
    assert package.missing_evidence == []


@pytest.mark.asyncio
async def test_validate_duplicate_facts_prefer_canonical_source() -> None:
    stale = _fact("obj-Account", confidence=0.95, source="search_index")
    canonical = _fact("obj-Account", confidence=0.9)
    package = await CitationValidator().validate(_plan([stale, canonical]))

    assert package.verified_facts[0].source == "search_index,canonical"
    assert package.missing_evidence == []


@pytest.mark.asyncio
async def test_validate_duplicate_citations_deduped() -> None:
    package = await CitationValidator().validate(
        _plan([_fact("obj-Account")], citations=["obj-Account", "obj-Account"])
    )

    assert package.required_citations == ["obj-Account"]
    assert package.coverage == 1.0


@pytest.mark.asyncio
async def test_validate_broken_relationship_removed() -> None:
    target = _fact("trg-BillingProcessor", source="search_index")
    account = _fact(
        "obj-Account",
        relationships=(_relationship("trg-BillingProcessor"),),
    )
    package = await CitationValidator().validate(_plan([account, target]))

    assert [f.identity for f in package.verified_facts] == ["obj-Account"]
    assert package.supporting_relationships == []
    assert package.missing_evidence == [
        MissingEvidence("trg-BillingProcessor", MissingReason.BROKEN_RELATIONSHIP)
    ]


@pytest.mark.asyncio
async def test_validate_unverified_relationship_removed() -> None:
    account = _fact("obj-Account", relationships=(_relationship("obj-Opportunity"),))
    package = await CitationValidator().validate(_plan([account]))

    assert package.supporting_relationships == []
    assert package.missing_evidence == [
        MissingEvidence("obj-Opportunity", MissingReason.UNVERIFIED_RELATIONSHIP)
    ]


@pytest.mark.asyncio
async def test_validate_relationship_intent_without_relationships() -> None:
    account = _fact("obj-Account")
    package = await CitationValidator().validate(_plan([account], intent="impact_analysis"))

    assert package.supporting_relationships == []
    assert package.missing_evidence == [
        MissingEvidence("obj-Account", MissingReason.MISSING_RELATIONSHIPS)
    ]


@pytest.mark.asyncio
async def test_validate_relationships_kept_deduped_and_ordered() -> None:
    duplicate = _relationship("trg-BillingProcessor", direction="outgoing")
    account = _fact(
        "obj-Account",
        relationships=(duplicate, _relationship("trg-BillingProcessor", direction="outgoing")),
    )
    trigger = _fact("trg-BillingProcessor")
    package = await CitationValidator().validate(_plan([account, trigger]))

    assert len(package.supporting_relationships) == 1
    assert package.supporting_relationships[0].identity == "trg-BillingProcessor"
    assert package.missing_evidence == []


@pytest.mark.asyncio
async def test_validate_evidence_ordering_by_confidence() -> None:
    facts = [
        _fact("obj-Mid", confidence=0.7),
        _fact("obj-High", confidence=0.9),
        _fact("obj-Low", confidence=0.35, source="graph"),
    ]
    package = await CitationValidator().validate(_plan(facts))

    assert [f.identity for f in package.verified_facts] == [
        "obj-High",
        "obj-Mid",
        "obj-Low",
    ]


@pytest.mark.asyncio
async def test_validate_supporting_metadata_merged() -> None:
    fact = _fact("obj-Account", metadata={"label": "Accounts", "description": "Customers"})
    package = await CitationValidator().validate(_plan([fact]))

    assert package.supporting_metadata["obj-Account"] == {
        "label": "Accounts",
        "description": "Customers",
    }


@pytest.mark.asyncio
async def test_validate_no_answer_plan_reports_its_gap() -> None:
    plan = ExecutionPlan(
        organization_id=uuid.uuid4(),
        question="",
        intent="search_query",
        confidence=0.0,
        retrieved_facts=[],
        missing_facts=["empty question"],
        required_citations=[],
        answer_strategy="no_answer",
        retry_count=0,
        sources_used=[],
        failures=[],
    )
    package = await CitationValidator().validate(plan)

    assert package.verified_facts == []
    assert package.coverage == 0.0
    assert package.confidence == 0.0
    assert package.missing_evidence == [
        MissingEvidence("empty question", MissingReason.NOT_RETRIEVED)
    ]


@pytest.mark.asyncio
async def test_validate_tenant_isolation() -> None:
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    validator = CitationValidator()
    package_a = await validator.validate(_plan([_fact("obj-Account")], organization_id=org_a))
    package_b = await validator.validate(_plan([_fact("obj-Contact")], organization_id=org_b))

    assert [f.identity for f in package_a.verified_facts] == ["obj-Account"]
    assert [f.identity for f in package_b.verified_facts] == ["obj-Contact"]
    assert package_a.required_citations == ["obj-Account"]
    assert package_b.required_citations == ["obj-Contact"]


@pytest.mark.asyncio
async def test_validate_concurrent_validation_is_safe() -> None:
    validator = CitationValidator()
    plans = [_plan([_fact("obj-Account", confidence=0.5 + i / 100)]) for i in range(25)]

    packages = await asyncio.gather(*(validator.validate(plan) for plan in plans))

    assert len(packages) == 25
    for index, package in enumerate(packages):
        assert [f.identity for f in package.verified_facts] == ["obj-Account"]
        assert package.coverage == 1.0
        assert package.confidence == round(0.5 + index / 100, 3)
        assert package.missing_evidence == []
