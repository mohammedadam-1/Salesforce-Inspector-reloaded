from __future__ import annotations

from typing import Any

from sfir_backend.domain.ai.models import Citation, ConfidenceScore


class ConfidenceScorer:
    VOTE_HIGH = 1.0
    VOTE_MEDIUM = 0.5
    VOTE_LOW = 0.0

    def score_from_citations(
        self,
        citations: list[Citation],
        hallucination_warnings: list[str] | None = None,
    ) -> ConfidenceScore:
        if not citations:
            return ConfidenceScore(
                level="low",
                score=0.2,
                reasons=["No citations available to verify the response."],
            )

        valid_count = sum(1 for c in citations if c.relevance > 0.5)
        total = len(citations)
        ratio = valid_count / total if total > 0 else 0

        if hallucination_warnings and len(hallucination_warnings) > 0:
            ratio *= 0.5
            reasons = [
                f"{total} citation(s) found, {valid_count} highly relevant.",
                f"{len(hallucination_warnings)} potential hallucination(s) detected.",
            ]
        else:
            reasons = [f"{total} citation(s) found, {valid_count} highly relevant."]

        if ratio >= 0.8 and total >= 3:
            return ConfidenceScore(level="high", score=0.8 + (ratio * 0.2), reasons=reasons)
        if ratio >= 0.4 and total >= 1:
            return ConfidenceScore(level="medium", score=0.4 + (ratio * 0.4), reasons=reasons)
        return ConfidenceScore(level="low", score=0.1 + (ratio * 0.3), reasons=reasons)

    def score_from_tool_execution(
        self,
        tool_results: list[dict[str, Any]],
    ) -> ConfidenceScore:
        if not tool_results:
            return ConfidenceScore(
                level="low",
                score=0.1,
                reasons=["No tools were executed."],
            )

        succeeded = sum(1 for r in tool_results if r.get("status") == "completed")
        failed = sum(1 for r in tool_results if r.get("status") == "failed")
        total = len(tool_results)

        if total == 0:
            return ConfidenceScore(level="low", score=0.1, reasons=["No tool results."])

        success_rate = succeeded / total
        reasons = [f"{succeeded}/{total} tools completed successfully."]
        if failed > 0:
            reasons.append(f"{failed} tool(s) failed.")

        if success_rate >= 0.8 and succeeded >= 2:
            return ConfidenceScore(level="high", score=0.7 + (success_rate * 0.3), reasons=reasons)
        if success_rate >= 0.5:
            return ConfidenceScore(level="medium", score=0.3 + (success_rate * 0.4), reasons=reasons)
        return ConfidenceScore(level="low", score=0.1 + (success_rate * 0.2), reasons=reasons)

    def score_from_search_results(
        self,
        total_results: int,
        top_score: float = 0.0,
        query_type: str = "metadata",
    ) -> ConfidenceScore:
        if total_results == 0:
            return ConfidenceScore(
                level="low",
                score=0.1,
                reasons=["No search results found."],
            )

        reasons = [f"Found {total_results} result(s)."]

        if query_type == "exact_match":
            return ConfidenceScore(
                level="high",
                score=0.95,
                reasons=["Exact match found in metadata."],
            )

        certainty = min(1.0, (total_results / 10) * 0.5 + top_score * 0.5)
        if certainty >= 0.7:
            return ConfidenceScore(level="high", score=certainty, reasons=reasons)
        if certainty >= 0.4:
            return ConfidenceScore(level="medium", score=certainty, reasons=reasons)
        return ConfidenceScore(level="low", score=certainty, reasons=reasons)

    def score_from_impact_analysis(
        self,
        risk_score: float | None,
        affected_count: int,
        has_cycles: bool = False,
    ) -> ConfidenceScore:
        if risk_score is None:
            return ConfidenceScore(
                level="medium",
                score=0.5,
                reasons=["Impact analysis completed but risk score unavailable."],
            )

        reasons = [f"Risk score: {risk_score:.2f}, {affected_count} component(s) affected."]
        if has_cycles:
            reasons.append("Circular dependencies detected — some paths may be incomplete.")

        if risk_score >= 0 and affected_count >= 0:
            return ConfidenceScore(
                level="high",
                score=0.85,
                reasons=reasons,
            )
        return ConfidenceScore(
            level="medium",
            score=0.5,
            reasons=reasons,
        )

    def aggregate(
        self,
        scores: list[ConfidenceScore | None],
    ) -> ConfidenceScore:
        filtered = [s for s in scores if s is not None]
        if not filtered:
            return ConfidenceScore(level="low", score=0.1, reasons=["Insufficient data to determine confidence."])

        avg_score = sum(s.score for s in filtered) / len(filtered)
        all_reasons: list[str] = []
        for s in filtered:
            all_reasons.extend(s.reasons)

        level: str
        if avg_score >= 0.7:
            level = "high"
        elif avg_score >= 0.4:
            level = "medium"
        else:
            level = "low"

        return ConfidenceScore(level=level, score=round(avg_score, 3), reasons=all_reasons)
