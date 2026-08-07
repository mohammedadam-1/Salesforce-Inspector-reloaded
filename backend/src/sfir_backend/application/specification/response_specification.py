"""Response specification — the structural contract for the answer phase.

The specification layer is the third stage of the planning pipeline:

    ExecutionPlan -> EvidencePackage -> Response Specification -> Prompt Builder

It consumes only the planner's ExecutionPlan and the validator's
EvidencePackage — never an LLM, Salesforce, a repository, or the
retrieval engine. It decides what the answer will look like, not what it
will say: answer type, ordered sections (each required, optional, or
unsupported), evidence ordering for presentation, the citation
placement strategy, formatting rules, warnings the answer must surface,
and how confidence should be displayed.

Every decision is deterministic and derived purely from the plan and
the package, so the builder is stateless and safe under concurrency and
across tenants.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from sfir_backend.application.planner import AnswerStrategy, ExecutionPlan
from sfir_backend.application.validator import EvidencePackage, MissingReason


class AnswerType(StrEnum):
    METADATA_DESCRIPTION = "metadata_description"
    IMPACT_SUMMARY = "impact_summary"
    DEPENDENCY_SUMMARY = "dependency_summary"
    RELATIONSHIP_SUMMARY = "relationship_summary"
    SEARCH_RESULTS = "search_results"
    NAVIGATION = "navigation"
    DOCUMENTATION = "documentation"
    NO_ANSWER = "no_answer"


class Section(StrEnum):
    SUMMARY = "summary"
    METADATA_DETAILS = "metadata_details"
    IMPACT_LIST = "impact_list"
    DEPENDENCY_LIST = "dependency_list"
    RELATIONSHIP_LIST = "relationship_list"
    SEARCH_RESULTS_LIST = "search_results_list"
    NAVIGATION_TARGET = "navigation_target"
    DOCUMENTATION_BODY = "documentation_body"
    CITATIONS = "citations"
    WARNINGS = "warnings"


class SectionState(StrEnum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    UNSUPPORTED = "unsupported"


@dataclass
class SectionSpec:
    section: Section
    state: SectionState


class CitationStrategy(StrEnum):
    NONE = "none"
    FOOTNOTE = "footnote"
    INLINE_PER_ITEM = "inline_per_item"
    GROUPED_BY_SECTION = "grouped_by_section"


class FormattingRule(StrEnum):
    BULLETED_ITEMS = "bulleted_items"
    NUMBERED_ITEMS = "numbered_items"
    PARAGRAPH_BODY = "paragraph_body"
    CODE_API_NAMES = "code_api_names"
    INLINE_CITATIONS = "inline_citations"
    GROUPED_CITATIONS = "grouped_citations"
    FOOTNOTE_CITATIONS = "footnote_citations"
    MAX_RESULTS_10 = "max_results_10"


class WarningCode(StrEnum):
    EVIDENCE_INCOMPLETE = "evidence_incomplete"
    METADATA_DELETED = "metadata_deleted"
    RELATIONSHIPS_UNVERIFIED = "relationships_unverified"
    LOW_CONFIDENCE = "low_confidence"
    NO_EVIDENCE = "no_evidence"
    PARTIAL_SOURCES = "partial_sources"


class ConfidenceLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ConfidenceStyle(StrEnum):
    PERCENTAGE = "percentage"
    QUALITATIVE = "qualitative"
    HIDDEN = "hidden"


@dataclass
class ConfidenceDisplay:
    level: ConfidenceLevel
    value: float
    style: ConfidenceStyle


@dataclass
class ResponseSpecification:
    organization_id: uuid.UUID
    answer_type: AnswerType
    sections: list[SectionSpec] = field(default_factory=list)
    evidence_ordering: list[str] = field(default_factory=list)
    citation_strategy: CitationStrategy = CitationStrategy.NONE
    formatting_rules: list[FormattingRule] = field(default_factory=list)
    warnings: list[WarningCode] = field(default_factory=list)
    confidence_display: ConfidenceDisplay = field(
        default_factory=lambda: ConfidenceDisplay(
            ConfidenceLevel.LOW,
            0.0,
            ConfidenceStyle.HIDDEN,
        )
    )


_STRATEGY_TO_TYPE: dict[AnswerStrategy, AnswerType] = {
    AnswerStrategy.DESCRIBE_METADATA: AnswerType.METADATA_DESCRIPTION,
    AnswerStrategy.IMPACT_SUMMARY: AnswerType.IMPACT_SUMMARY,
    AnswerStrategy.DEPENDENCY_SUMMARY: AnswerType.DEPENDENCY_SUMMARY,
    AnswerStrategy.RELATIONSHIP_SUMMARY: AnswerType.RELATIONSHIP_SUMMARY,
    AnswerStrategy.SEARCH_RESULTS: AnswerType.SEARCH_RESULTS,
    AnswerStrategy.NAVIGATE_TO: AnswerType.NAVIGATION,
    AnswerStrategy.DOCUMENTATION_SUMMARY: AnswerType.DOCUMENTATION,
    AnswerStrategy.NEEDS_MORE_INFO: AnswerType.NO_ANSWER,
    AnswerStrategy.NO_ANSWER: AnswerType.NO_ANSWER,
}

_CITATION_STRATEGY: dict[AnswerType, CitationStrategy] = {
    AnswerType.METADATA_DESCRIPTION: CitationStrategy.FOOTNOTE,
    AnswerType.IMPACT_SUMMARY: CitationStrategy.GROUPED_BY_SECTION,
    AnswerType.DEPENDENCY_SUMMARY: CitationStrategy.GROUPED_BY_SECTION,
    AnswerType.RELATIONSHIP_SUMMARY: CitationStrategy.GROUPED_BY_SECTION,
    AnswerType.SEARCH_RESULTS: CitationStrategy.INLINE_PER_ITEM,
    AnswerType.NAVIGATION: CitationStrategy.FOOTNOTE,
    AnswerType.DOCUMENTATION: CitationStrategy.INLINE_PER_ITEM,
    AnswerType.NO_ANSWER: CitationStrategy.NONE,
}

_FORMATTING_RULES: dict[AnswerType, tuple[FormattingRule, ...]] = {
    AnswerType.METADATA_DESCRIPTION: (
        FormattingRule.PARAGRAPH_BODY,
        FormattingRule.CODE_API_NAMES,
        FormattingRule.FOOTNOTE_CITATIONS,
    ),
    AnswerType.IMPACT_SUMMARY: (
        FormattingRule.BULLETED_ITEMS,
        FormattingRule.CODE_API_NAMES,
        FormattingRule.GROUPED_CITATIONS,
    ),
    AnswerType.DEPENDENCY_SUMMARY: (
        FormattingRule.BULLETED_ITEMS,
        FormattingRule.CODE_API_NAMES,
        FormattingRule.GROUPED_CITATIONS,
    ),
    AnswerType.RELATIONSHIP_SUMMARY: (
        FormattingRule.BULLETED_ITEMS,
        FormattingRule.CODE_API_NAMES,
        FormattingRule.GROUPED_CITATIONS,
    ),
    AnswerType.SEARCH_RESULTS: (
        FormattingRule.NUMBERED_ITEMS,
        FormattingRule.CODE_API_NAMES,
        FormattingRule.INLINE_CITATIONS,
        FormattingRule.MAX_RESULTS_10,
    ),
    AnswerType.NAVIGATION: (
        FormattingRule.CODE_API_NAMES,
        FormattingRule.INLINE_CITATIONS,
    ),
    AnswerType.DOCUMENTATION: (
        FormattingRule.PARAGRAPH_BODY,
        FormattingRule.CODE_API_NAMES,
        FormattingRule.INLINE_CITATIONS,
    ),
    AnswerType.NO_ANSWER: (),
}

_CORE_SECTION: dict[AnswerType, Section] = {
    AnswerType.METADATA_DESCRIPTION: Section.METADATA_DETAILS,
    AnswerType.IMPACT_SUMMARY: Section.IMPACT_LIST,
    AnswerType.DEPENDENCY_SUMMARY: Section.DEPENDENCY_LIST,
    AnswerType.RELATIONSHIP_SUMMARY: Section.RELATIONSHIP_LIST,
    AnswerType.SEARCH_RESULTS: Section.SEARCH_RESULTS_LIST,
    AnswerType.NAVIGATION: Section.NAVIGATION_TARGET,
    AnswerType.DOCUMENTATION: Section.DOCUMENTATION_BODY,
}

_RELATIONSHIP_ANSWER_TYPES = frozenset(
    {
        AnswerType.IMPACT_SUMMARY,
        AnswerType.DEPENDENCY_SUMMARY,
        AnswerType.RELATIONSHIP_SUMMARY,
    },
)

_RELATIONSHIP_REASONS = frozenset(
    {
        MissingReason.BROKEN_RELATIONSHIP,
        MissingReason.UNVERIFIED_RELATIONSHIP,
        MissingReason.MISSING_RELATIONSHIPS,
    },
)


class ResponseSpecificationBuilder:
    def __init__(
        self,
        *,
        high_confidence: float = 0.75,
        medium_confidence: float = 0.5,
    ) -> None:
        self._high_confidence = high_confidence
        self._medium_confidence = medium_confidence

    async def build(
        self,
        plan: ExecutionPlan,
        package: EvidencePackage,
    ) -> ResponseSpecification:
        facts = package.verified_facts
        has_facts = bool(facts)
        has_relationships = bool(package.supporting_relationships)
        has_description = any(bool(fact.description) for fact in facts)

        answer_type = self._answer_type(plan, has_facts)
        level = self._level(package.confidence)
        warnings = self._warnings(
            plan,
            package,
            answer_type,
            has_facts,
            level,
        )
        sections = self._sections(
            answer_type,
            has_facts,
            has_relationships,
            has_description,
            warnings,
        )
        confidence = ConfidenceDisplay(
            level=level,
            value=package.confidence,
            style=self._confidence_style(answer_type, package, warnings),
        )
        return ResponseSpecification(
            organization_id=plan.organization_id,
            answer_type=answer_type,
            sections=sections,
            evidence_ordering=self._evidence_ordering(answer_type, facts),
            citation_strategy=_CITATION_STRATEGY[answer_type],
            formatting_rules=list(_FORMATTING_RULES[answer_type]),
            warnings=warnings,
            confidence_display=confidence,
        )

    @staticmethod
    def _answer_type(plan: ExecutionPlan, has_facts: bool) -> AnswerType:
        try:
            strategy = AnswerStrategy(plan.answer_strategy)
        except ValueError:
            strategy = AnswerStrategy.NO_ANSWER
        declared = _STRATEGY_TO_TYPE.get(strategy, AnswerType.NO_ANSWER)
        if declared is not AnswerType.NO_ANSWER and not has_facts:
            return AnswerType.NO_ANSWER
        return declared

    @staticmethod
    def _warnings(
        plan: ExecutionPlan,
        package: EvidencePackage,
        answer_type: AnswerType,
        has_facts: bool,
        level: ConfidenceLevel,
    ) -> list[WarningCode]:
        reasons = {entry.reason for entry in package.missing_evidence}
        warnings: list[WarningCode] = []
        if package.missing_evidence:
            warnings.append(WarningCode.EVIDENCE_INCOMPLETE)
        if MissingReason.METADATA_DELETED in reasons:
            warnings.append(WarningCode.METADATA_DELETED)
        if reasons & _RELATIONSHIP_REASONS:
            warnings.append(WarningCode.RELATIONSHIPS_UNVERIFIED)
        if plan.failures:
            warnings.append(WarningCode.PARTIAL_SOURCES)
        if not has_facts:
            warnings.append(WarningCode.NO_EVIDENCE)
        if answer_type is not AnswerType.NO_ANSWER and level is ConfidenceLevel.LOW:
            warnings.append(WarningCode.LOW_CONFIDENCE)
        return warnings

    def _sections(
        self,
        answer_type: AnswerType,
        has_facts: bool,
        has_relationships: bool,
        has_description: bool,
        warnings: list[WarningCode],
    ) -> list[SectionSpec]:
        sections = [SectionSpec(Section.SUMMARY, SectionState.REQUIRED)]
        if answer_type is AnswerType.NO_ANSWER:
            sections.append(
                SectionSpec(
                    Section.WARNINGS,
                    (SectionState.REQUIRED if warnings else SectionState.OPTIONAL),
                )
            )
            return sections
        core = _CORE_SECTION[answer_type]
        if answer_type in _RELATIONSHIP_ANSWER_TYPES:
            core_state = SectionState.REQUIRED if has_relationships else SectionState.UNSUPPORTED
        elif core is Section.DOCUMENTATION_BODY:
            core_state = SectionState.REQUIRED if has_description else SectionState.UNSUPPORTED
        else:
            core_state = SectionState.REQUIRED
        sections.append(SectionSpec(core, core_state))
        sections.append(
            SectionSpec(
                Section.CITATIONS,
                (SectionState.REQUIRED if has_facts else SectionState.UNSUPPORTED),
            )
        )
        sections.append(
            SectionSpec(
                Section.WARNINGS,
                (SectionState.REQUIRED if warnings else SectionState.OPTIONAL),
            )
        )
        return sections

    @staticmethod
    def _evidence_ordering(
        answer_type: AnswerType,
        facts: list,
    ) -> list[str]:
        if not facts:
            return []
        if answer_type is AnswerType.NAVIGATION:
            return [facts[0].identity]
        if answer_type in _RELATIONSHIP_ANSWER_TYPES:
            subject = max(
                facts,
                key=lambda fact: len(fact.supporting_relationships),
            )
            return [subject.identity] + [
                fact.identity for fact in facts if fact.identity != subject.identity
            ]
        return [fact.identity for fact in facts]

    @staticmethod
    def _confidence_style(
        answer_type: AnswerType,
        package: EvidencePackage,
        warnings: list[WarningCode],
    ) -> ConfidenceStyle:
        if answer_type is AnswerType.NO_ANSWER or package.confidence == 0.0:
            return ConfidenceStyle.HIDDEN
        if set(warnings) & {
            WarningCode.EVIDENCE_INCOMPLETE,
            WarningCode.LOW_CONFIDENCE,
            WarningCode.RELATIONSHIPS_UNVERIFIED,
        }:
            return ConfidenceStyle.QUALITATIVE
        return ConfidenceStyle.PERCENTAGE

    def _level(self, value: float) -> ConfidenceLevel:
        if value >= self._high_confidence:
            return ConfidenceLevel.HIGH
        if value >= self._medium_confidence:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW
