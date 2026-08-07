"""Unit tests for the response specification builder.

The builder consumes only an ExecutionPlan and an EvidencePackage — no
LLM, no Salesforce, no repositories, no retrieval engine. These tests
drive it with hand-built plans and packages covering every decision:
answer type, section ordering and support, citation placement, evidence
ordering, formatting, warnings, and confidence presentation, plus tenant
isolation and concurrency.
"""

import asyncio
import uuid

import pytest

from sfir_backend.application.planner import AnswerStrategy, ExecutionPlan
from sfir_backend.application.specification import (
    AnswerType,
    CitationStrategy,
    ConfidenceLevel,
    ConfidenceStyle,
    FormattingRule,
    ResponseSpecificationBuilder,
    Section,
    SectionState,
    WarningCode,
)
from sfir_backend.application.validator import (
    EvidencePackage,
    MissingEvidence,
    MissingReason,
)
from sfir_backend.domain.entities.verified_fact import (
    SupportingRelationship,
    VerifiedFact,
)

BUILDER = ResponseSpecificationBuilder()


def _fact(
    identity: str,
    *,
    confidence: float = 0.9,
    description: str = "desc",
    relationships: tuple[SupportingRelationship, ...] = (),
) -> VerifiedFact:
    return VerifiedFact(
        identity=identity,
        metadata_type="object",
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


def _relationship(identity: str) -> SupportingRelationship:
    return SupportingRelationship(
        identity=identity,
        api_name=identity,
        metadata_type="object",
        relationship_type="references",
        direction="incoming",
    )


def _plan(
    *,
    strategy: AnswerStrategy = AnswerStrategy.DESCRIBE_METADATA,
    organization_id: uuid.UUID | None = None,
    failures: list[str] | None = None,
) -> ExecutionPlan:
    return ExecutionPlan(
        organization_id=organization_id or uuid.uuid4(),
        question="what is Account",
        intent="metadata_lookup",
        confidence=0.9,
        retrieved_facts=[],
        missing_facts=[],
        required_citations=[],
        answer_strategy=strategy,
        retry_count=0,
        sources_used=["search_index", "canonical"],
        failures=failures or [],
    )


def _package(
    facts: list[VerifiedFact],
    *,
    missing: list[MissingEvidence] | None = None,
    confidence: float | None = None,
    relationships: list[SupportingRelationship] | None = None,
) -> EvidencePackage:
    return EvidencePackage(
        verified_facts=facts,
        supporting_relationships=relationships
        or [rel for fact in facts for rel in fact.supporting_relationships],
        supporting_metadata={fact.identity: {} for fact in facts},
        required_citations=[fact.identity for fact in facts],
        confidence=(
            round(sum(f.confidence for f in facts) / len(facts), 3)
            if confidence is None and facts
            else (confidence or 0.0)
        ),
        coverage=1.0 if facts else 0.0,
        missing_evidence=missing or [],
    )


@pytest.mark.asyncio
async def test_spec_metadata_lookup_correct_structure() -> None:
    plan = _plan()
    package = _package([_fact("obj-Account", confidence=0.9)])

    spec = await BUILDER.build(plan, package)

    assert spec.answer_type is AnswerType.METADATA_DESCRIPTION
    assert [(s.section, s.state) for s in spec.sections] == [
        (Section.SUMMARY, SectionState.REQUIRED),
        (Section.METADATA_DETAILS, SectionState.REQUIRED),
        (Section.CITATIONS, SectionState.REQUIRED),
        (Section.WARNINGS, SectionState.OPTIONAL),
    ]
    assert spec.evidence_ordering == ["obj-Account"]
    assert spec.citation_strategy is CitationStrategy.FOOTNOTE
    assert spec.formatting_rules == [
        FormattingRule.PARAGRAPH_BODY,
        FormattingRule.CODE_API_NAMES,
        FormattingRule.FOOTNOTE_CITATIONS,
    ]
    assert spec.warnings == []
    assert spec.confidence_display.level is ConfidenceLevel.HIGH
    assert spec.confidence_display.style is ConfidenceStyle.PERCENTAGE
    assert spec.confidence_display.value == 0.9


@pytest.mark.asyncio
async def test_spec_missing_evidence_warns_and_downgrades_style() -> None:
    plan = _plan()
    package = _package(
        [_fact("obj-Account")],
        missing=[MissingEvidence("obj-Contact", "not_retrieved")],
        confidence=0.9,
    )

    spec = await BUILDER.build(plan, package)

    assert spec.answer_type is AnswerType.METADATA_DESCRIPTION
    assert WarningCode.EVIDENCE_INCOMPLETE in spec.warnings
    assert spec.confidence_display.style is ConfidenceStyle.QUALITATIVE
    assert spec.confidence_display.level is ConfidenceLevel.HIGH


@pytest.mark.asyncio
async def test_spec_low_confidence_warns() -> None:
    plan = _plan()
    package = _package([_fact("obj-Account", confidence=0.3)], confidence=0.3)

    spec = await BUILDER.build(plan, package)

    assert spec.confidence_display.level is ConfidenceLevel.LOW
    assert spec.confidence_display.style is ConfidenceStyle.QUALITATIVE
    assert WarningCode.LOW_CONFIDENCE in spec.warnings


@pytest.mark.asyncio
async def test_spec_high_confidence_clean() -> None:
    plan = _plan()
    package = _package([_fact("obj-Account", confidence=0.95)], confidence=0.95)

    spec = await BUILDER.build(plan, package)

    assert spec.confidence_display.level is ConfidenceLevel.HIGH
    assert spec.confidence_display.style is ConfidenceStyle.PERCENTAGE
    assert spec.warnings == []


@pytest.mark.asyncio
async def test_spec_partial_evidence_keeps_structure() -> None:
    plan = _plan()
    package = _package(
        [_fact("obj-Account")],
        missing=[MissingEvidence("obj-Contact", MissingReason.NOT_RETRIEVED)],
        confidence=0.9,
    )

    spec = await BUILDER.build(plan, package)

    assert spec.answer_type is AnswerType.METADATA_DESCRIPTION
    metadata = [s for s in spec.sections if s.section is Section.METADATA_DETAILS]
    assert metadata[0].state is SectionState.REQUIRED
    assert WarningCode.EVIDENCE_INCOMPLETE in spec.warnings


@pytest.mark.asyncio
async def test_spec_impact_unsupported_when_relationships_missing() -> None:
    plan = _plan(strategy=AnswerStrategy.IMPACT_SUMMARY)
    package = _package(
        [_fact("obj-Account")],
        missing=[MissingEvidence("obj-Account", MissingReason.MISSING_RELATIONSHIPS)],
        relationships=[],
        confidence=0.9,
    )

    spec = await BUILDER.build(plan, package)

    assert spec.answer_type is AnswerType.IMPACT_SUMMARY
    impact = [s for s in spec.sections if s.section is Section.IMPACT_LIST]
    assert impact[0].state is SectionState.UNSUPPORTED
    assert WarningCode.RELATIONSHIPS_UNVERIFIED in spec.warnings
    assert spec.citation_strategy is CitationStrategy.GROUPED_BY_SECTION
    assert spec.evidence_ordering == ["obj-Account"]


@pytest.mark.asyncio
async def test_spec_no_facts_becomes_no_answer() -> None:
    plan = _plan()
    package = _package(
        [],
        missing=[MissingEvidence("metadata for Account", "not_retrieved")],
        confidence=0.0,
    )

    spec = await BUILDER.build(plan, package)

    assert spec.answer_type is AnswerType.NO_ANSWER
    assert [(s.section, s.state) for s in spec.sections] == [
        (Section.SUMMARY, SectionState.REQUIRED),
        (Section.WARNINGS, SectionState.REQUIRED),
    ]
    assert spec.citation_strategy is CitationStrategy.NONE
    assert spec.evidence_ordering == []
    assert WarningCode.NO_EVIDENCE in spec.warnings
    assert WarningCode.EVIDENCE_INCOMPLETE in spec.warnings
    assert spec.confidence_display.style is ConfidenceStyle.HIDDEN


@pytest.mark.asyncio
async def test_spec_relationship_subject_leads_evidence_ordering() -> None:
    plan = _plan(strategy=AnswerStrategy.IMPACT_SUMMARY)
    neighbor = _fact(
        "trg-BillingProcessor",
        confidence=0.35,
        relationships=(_relationship("obj-Account"),),
    )
    subject = _fact(
        "obj-Account",
        confidence=0.9,
        relationships=(
            _relationship("trg-BillingProcessor"),
            _relationship("trg-DebtCollector"),
        ),
    )
    package = _package([neighbor, subject], confidence=0.625)

    spec = await BUILDER.build(plan, package)

    assert spec.evidence_ordering == [
        "obj-Account",
        "trg-BillingProcessor",
    ]


@pytest.mark.asyncio
async def test_spec_navigation_single_target() -> None:
    plan = _plan(strategy=AnswerStrategy.NAVIGATE_TO)
    package = _package(
        [_fact("obj-Account"), _fact("obj-Contact", confidence=0.8)],
        confidence=0.85,
    )

    spec = await BUILDER.build(plan, package)

    assert spec.answer_type is AnswerType.NAVIGATION
    assert spec.evidence_ordering == ["obj-Account"]
    assert spec.citation_strategy is CitationStrategy.FOOTNOTE
    target = [s for s in spec.sections if s.section is Section.NAVIGATION_TARGET]
    assert target[0].state is SectionState.REQUIRED


@pytest.mark.asyncio
async def test_spec_search_formatting() -> None:
    plan = _plan(strategy=AnswerStrategy.SEARCH_RESULTS)
    package = _package(
        [_fact("obj-Account"), _fact("obj-Contact", confidence=0.8)],
        confidence=0.85,
    )

    spec = await BUILDER.build(plan, package)

    assert spec.answer_type is AnswerType.SEARCH_RESULTS
    assert spec.citation_strategy is CitationStrategy.INLINE_PER_ITEM
    assert FormattingRule.MAX_RESULTS_10 in spec.formatting_rules
    assert spec.evidence_ordering == ["obj-Account", "obj-Contact"]


@pytest.mark.asyncio
async def test_spec_documentation_unsupported_without_description() -> None:
    plan = _plan(strategy=AnswerStrategy.DOCUMENTATION_SUMMARY)
    package = _package([_fact("obj-Account", description="")], confidence=0.9)

    spec = await BUILDER.build(plan, package)

    assert spec.answer_type is AnswerType.DOCUMENTATION
    body = [s for s in spec.sections if s.section is Section.DOCUMENTATION_BODY]
    assert body[0].state is SectionState.UNSUPPORTED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("strategy", "expected"),
    [
        (AnswerStrategy.DESCRIBE_METADATA, AnswerType.METADATA_DESCRIPTION),
        (AnswerStrategy.IMPACT_SUMMARY, AnswerType.IMPACT_SUMMARY),
        (AnswerStrategy.DEPENDENCY_SUMMARY, AnswerType.DEPENDENCY_SUMMARY),
        (AnswerStrategy.RELATIONSHIP_SUMMARY, AnswerType.RELATIONSHIP_SUMMARY),
        (AnswerStrategy.SEARCH_RESULTS, AnswerType.SEARCH_RESULTS),
        (AnswerStrategy.NAVIGATE_TO, AnswerType.NAVIGATION),
        (AnswerStrategy.DOCUMENTATION_SUMMARY, AnswerType.DOCUMENTATION),
        (AnswerStrategy.NO_ANSWER, AnswerType.NO_ANSWER),
        (AnswerStrategy.NEEDS_MORE_INFO, AnswerType.NO_ANSWER),
    ],
)
async def test_spec_multiple_answer_types(
    strategy: AnswerStrategy,
    expected: AnswerType,
) -> None:
    plan = _plan(strategy=strategy)
    package = _package([_fact("obj-Account")], confidence=0.9)

    spec = await BUILDER.build(plan, package)

    assert spec.answer_type is expected


@pytest.mark.asyncio
async def test_spec_unknown_strategy_falls_back_to_no_answer() -> None:
    plan = _plan(strategy=AnswerStrategy.NO_ANSWER)
    plan.answer_strategy = "made_up_strategy"
    package = _package([_fact("obj-Account")], confidence=0.9)

    spec = await BUILDER.build(plan, package)

    assert spec.answer_type is AnswerType.NO_ANSWER


@pytest.mark.asyncio
async def test_spec_tenant_isolation() -> None:
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    plan_a = _plan(organization_id=org_a)
    plan_b = _plan(organization_id=org_b)
    package_a = _package([_fact("obj-Account")], confidence=0.9)
    package_b = _package([_fact("obj-Contact")], confidence=0.8)

    spec_a = await BUILDER.build(plan_a, package_a)
    spec_b = await BUILDER.build(plan_b, package_b)

    assert spec_a.organization_id == org_a
    assert spec_b.organization_id == org_b
    assert spec_a.evidence_ordering == ["obj-Account"]
    assert spec_b.evidence_ordering == ["obj-Contact"]


@pytest.mark.asyncio
async def test_spec_concurrent_builds_are_deterministic() -> None:
    plan = _plan()
    package = _package([_fact("obj-Account")], confidence=0.9)

    specs = await asyncio.gather(*(BUILDER.build(plan, package) for _ in range(25)))

    assert len(specs) == 25
    first = specs[0]
    for spec in specs:
        assert spec.answer_type is AnswerType.METADATA_DESCRIPTION
        assert spec.sections == first.sections
        assert spec.evidence_ordering == ["obj-Account"]
        assert spec.warnings == []
        assert spec.confidence_display == first.confidence_display
