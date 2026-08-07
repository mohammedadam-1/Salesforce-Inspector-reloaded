"""Unit tests for the rule-based intent detector."""

import pytest

from sfir_backend.application.planner.intent import Intent, IntentDetector

DETECTOR = IntentDetector()


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        ("what is Account", Intent.METADATA_LOOKUP),
        ("describe the Opportunity object", Intent.METADATA_LOOKUP),
        ("what is the impact of deleting Account", Intent.IMPACT_ANALYSIS),
        ("which components are affected by changing Account", Intent.IMPACT_ANALYSIS),
        ("what depends on Account", Intent.DEPENDENCY_DISCOVERY),
        ("where is Account used", Intent.DEPENDENCY_DISCOVERY),
        ("how is Account related to Opportunity", Intent.RELATIONSHIP_QUERY),
        ("what relationship does Account have", Intent.RELATIONSHIP_QUERY),
        ("find components with order in the name", Intent.SEARCH_QUERY),
        ("search for flows", Intent.SEARCH_QUERY),
        ("where is Account in setup", Intent.NAVIGATION_QUERY),
        ("navigate to Account", Intent.NAVIGATION_QUERY),
        ("how do i deploy a flow", Intent.DOCUMENTATION_QUERY),
        ("show me documentation for Account", Intent.DOCUMENTATION_QUERY),
    ],
)
def test_detect_known_intents(question: str, intent: Intent) -> None:
    assert DETECTOR.detect(question).intent is intent


def test_detect_fallback_on_no_pattern_match() -> None:
    detection = DETECTOR.detect("asdfghjkl qwerty")
    assert detection.intent is Intent.SEARCH_QUERY
    assert detection.confidence == 0.4


def test_detect_empty_question_scores_zero() -> None:
    detection = DETECTOR.detect("")
    assert detection.intent is Intent.SEARCH_QUERY
    assert detection.confidence == 0.0


def test_detect_case_insensitive() -> None:
    assert DETECTOR.detect("WHAT IS THE IMPACT OF Account").intent is (
        Intent.IMPACT_ANALYSIS
    )


def test_detect_clear_question_scores_high() -> None:
    detection = DETECTOR.detect("impact of Account")
    assert detection.intent is Intent.IMPACT_ANALYSIS
    assert detection.confidence == 0.95


def test_detect_ambiguous_question_scores_low() -> None:
    detection = DETECTOR.detect("describe the impact and relationship of Account")
    assert detection.intent is Intent.IMPACT_ANALYSIS
    assert detection.confidence < 0.7
    assert detection.confidence > 0.5


def test_detect_confidence_is_deterministic() -> None:
    first = DETECTOR.detect("how is Account related to Opportunity")
    second = DETECTOR.detect("how is Account related to Opportunity")
    assert first.confidence == second.confidence
    assert 0.5 <= first.confidence <= 0.95
