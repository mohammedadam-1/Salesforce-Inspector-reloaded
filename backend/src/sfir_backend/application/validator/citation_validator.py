"""Citation validator — validates an execution plan's evidence in memory.

The validator is the second stage of the planning pipeline:

    ExecutionPlan -> Citation Validator -> EvidencePackage

It consumes only the planner's ExecutionPlan and its VerifiedFacts. It
never queries Salesforce, the search index, the canonical store, or the
dependency graph directly — every signal it needs already lives on the
plan and its facts (source provenance, confidence, supporting
relationships, supporting metadata, required citations).

It verifies every retrieved fact, verifies relationships exist, removes
invalid facts (metadata no longer present, confidence below threshold),
eliminates duplicate evidence, ensures every required citation is
covered, and produces an EvidencePackage with confidence, coverage,
missing evidence, and a deterministic evidence ordering for the answer
phase. It is pure and stateless: no I/O, safe under concurrency and
across tenants.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from sfir_backend.application.planner import ExecutionPlan
from sfir_backend.domain.entities.verified_fact import (
    SupportingRelationship,
    VerifiedFact,
)

_CANONICAL_SOURCE = "canonical"

_RELATIONSHIP_HEAVY = frozenset(
    {"impact_analysis", "dependency_discovery", "relationship_query"},
)


class MissingReason(StrEnum):
    NOT_RETRIEVED = "not_retrieved"
    METADATA_DELETED = "metadata_deleted"
    LOW_CONFIDENCE = "low_confidence"
    BROKEN_RELATIONSHIP = "broken_relationship"
    UNVERIFIED_RELATIONSHIP = "unverified_relationship"
    MISSING_RELATIONSHIPS = "missing_relationships"


@dataclass
class MissingEvidence:
    identity: str
    reason: MissingReason


@dataclass
class EvidencePackage:
    verified_facts: list[VerifiedFact] = field(default_factory=list)
    supporting_relationships: list[SupportingRelationship] = field(
        default_factory=list,
    )
    supporting_metadata: dict[str, dict] = field(default_factory=dict)
    required_citations: list[str] = field(default_factory=list)
    confidence: float = 0.0
    coverage: float = 0.0
    missing_evidence: list[MissingEvidence] = field(default_factory=list)


class CitationValidator:
    def __init__(self, *, min_fact_confidence: float = 0.3) -> None:
        self._min_fact_confidence = min_fact_confidence

    async def validate(self, plan: ExecutionPlan) -> EvidencePackage:
        facts = self._dedupe(plan.retrieved_facts)
        invalid = self._invalidations(facts)

        verified = [fact for fact in facts if fact.identity not in invalid]
        verified.sort(
            key=lambda fact: (
                -fact.confidence,
                -fact.search_score,
                fact.identity,
            ),
        )
        verified_ids = {fact.identity for fact in verified}
        fact_ids = {fact.identity for fact in facts}

        citations = self._unique(plan.required_citations)
        referenced = {
            relationship.identity
            for fact in facts
            for relationship in fact.supporting_relationships
        }
        missing = [
            MissingEvidence(
                identity,
                (MissingReason.BROKEN_RELATIONSHIP if identity in referenced else reason),
            )
            for identity, reason in invalid.items()
        ]
        relationships, more_missing = self._relationships(
            verified,
            fact_ids,
            invalid,
            plan.intent,
        )
        missing.extend(more_missing)
        missing = self._citation_gaps(citations, fact_ids, invalid, missing)
        if not citations:
            missing = self._plan_gaps(plan.missing_facts, missing)

        return EvidencePackage(
            verified_facts=verified,
            supporting_relationships=relationships,
            supporting_metadata=self._metadata(verified),
            required_citations=citations,
            confidence=self._confidence(verified),
            coverage=self._coverage(citations, verified_ids, plan.missing_facts),
            missing_evidence=missing,
        )

    @staticmethod
    def _dedupe(facts: list[VerifiedFact]) -> list[VerifiedFact]:
        """Collapse duplicate facts by identity, keeping the strongest."""
        best: dict[str, VerifiedFact] = {}
        for fact in facts:
            current = best.get(fact.identity)
            if current is None or CitationValidator._stronger(fact, current):
                best[fact.identity] = fact
        return list(best.values())

    @staticmethod
    def _stronger(candidate: VerifiedFact, current: VerifiedFact) -> bool:
        candidate_canonical = _CANONICAL_SOURCE in candidate.source.split(",")
        current_canonical = _CANONICAL_SOURCE in current.source.split(",")
        if candidate_canonical and not current_canonical:
            return True
        return (candidate.confidence, candidate.search_score) > (
            current.confidence,
            current.search_score,
        )

    def _invalidations(
        self,
        facts: list[VerifiedFact],
    ) -> dict[str, MissingReason]:
        invalid: dict[str, MissingReason] = {}
        for fact in facts:
            sources = fact.source.split(",")
            if "search_index" in sources and _CANONICAL_SOURCE not in sources:
                invalid[fact.identity] = MissingReason.METADATA_DELETED
            elif fact.confidence < self._min_fact_confidence:
                invalid[fact.identity] = MissingReason.LOW_CONFIDENCE
        return invalid

    @staticmethod
    def _relationships(
        verified: list[VerifiedFact],
        fact_ids: set[str],
        invalid: dict[str, MissingReason],
        intent: str,
    ) -> tuple[list[SupportingRelationship], list[MissingEvidence]]:
        relationships: dict[tuple[str, str, str], SupportingRelationship] = {}
        missing: list[MissingEvidence] = []
        for fact in verified:
            for relationship in fact.supporting_relationships:
                target = relationship.identity
                if target in invalid:
                    continue
                if target not in fact_ids:
                    missing.append(
                        MissingEvidence(
                            target,
                            MissingReason.UNVERIFIED_RELATIONSHIP,
                        )
                    )
                    continue
                key = (
                    relationship.identity,
                    relationship.relationship_type,
                    relationship.direction,
                )
                relationships.setdefault(key, relationship)
        if intent in _RELATIONSHIP_HEAVY and verified and not relationships:
            missing.append(
                MissingEvidence(
                    verified[0].identity,
                    MissingReason.MISSING_RELATIONSHIPS,
                )
            )
        ordered = sorted(
            relationships.values(),
            key=lambda r: (r.identity, r.relationship_type, r.direction),
        )
        return ordered, missing

    @staticmethod
    def _citation_gaps(
        citations: list[str],
        fact_ids: set[str],
        invalid: dict[str, MissingReason],
        missing: list[MissingEvidence],
    ) -> list[MissingEvidence]:
        seen = {(entry.identity, entry.reason) for entry in missing}
        for citation in citations:
            if citation in invalid:
                continue
            if citation not in fact_ids and (citation, MissingReason.NOT_RETRIEVED) not in seen:
                missing.append(MissingEvidence(citation, MissingReason.NOT_RETRIEVED))
        return missing

    @staticmethod
    def _plan_gaps(
        missing_facts: list[str],
        missing: list[MissingEvidence],
    ) -> list[MissingEvidence]:
        """Surface the plan's declared gaps when no citations exist.

        A plan that found nothing carries no required citations, only
        descriptive missing-fact strings ("metadata for Account"). Those
        gaps are the evidence contract in that case, so they surface as
        missing evidence instead of a vacuously full coverage.
        """
        seen = {(entry.identity, entry.reason) for entry in missing}
        for gap in dict.fromkeys(missing_facts):
            if (gap, MissingReason.NOT_RETRIEVED) not in seen:
                missing.append(MissingEvidence(gap, MissingReason.NOT_RETRIEVED))
        return missing

    @staticmethod
    def _metadata(verified: list[VerifiedFact]) -> dict[str, dict]:
        merged: dict[str, dict] = {}
        for fact in verified:
            existing = merged.setdefault(fact.identity, {})
            existing.update(fact.supporting_metadata or {})
        return merged

    @staticmethod
    def _confidence(verified: list[VerifiedFact]) -> float:
        if not verified:
            return 0.0
        mean = sum(fact.confidence for fact in verified) / len(verified)
        return round(mean, 3)

    @staticmethod
    def _coverage(
        citations: list[str],
        verified_ids: set[str],
        missing_facts: list[str],
    ) -> float:
        if citations:
            covered = sum(1 for citation in citations if citation in verified_ids)
            return round(covered / len(citations), 3)
        if missing_facts:
            return 0.0
        return 1.0

    @staticmethod
    def _unique(values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))
