from __future__ import annotations

from sfir_backend.domain.search.models import SearchDocument, SearchQuery

_TYPE_WEIGHTS: dict[str, float] = {
    "object": 1.0,
    "field": 1.0,
    "apex_class": 0.95,
    "trigger": 0.9,
    "flow": 0.9,
    "validation_rule": 0.85,
    "formula": 0.8,
    "permission_set": 0.8,
    "profile": 0.8,
    "layout": 0.75,
    "report": 0.75,
    "dashboard": 0.75,
    "record_type": 0.7,
    "global_value_set": 0.7,
    "custom_metadata": 0.7,
    "custom_setting": 0.7,
    "named_credential": 0.65,
    "role": 0.6,
    "queue": 0.6,
    "public_group": 0.6,
    "sharing_rule": 0.6,
    "lightning_page": 0.65,
    "quick_action": 0.6,
    "email_template": 0.6,
    "connected_app": 0.6,
    "workflow": 0.7,
    "approval_process": 0.7,
}


class SearchRankingEngine:
    def rank(
        self,
        documents: list[SearchDocument],
        query: SearchQuery,
    ) -> list[tuple[SearchDocument, float, list[str]]]:
        scored: list[tuple[SearchDocument, float, list[str]]] = []
        for doc in documents:
            score, matched_fields = self._score(doc, query)
            if score > 0:
                scored.append((doc, score, matched_fields))
        scored.sort(key=lambda x: (-x[1], x[0].api_name))
        return scored

    def _score(
        self,
        doc: SearchDocument,
        query: SearchQuery,
    ) -> tuple[float, list[str]]:
        score = 0.0
        matched_fields: list[str] = []
        q = query.raw_query.lower().strip() if query.raw_query else ""

        if not q and not query.tokens:
            return 1.0, ["all"]

        api_lower = doc.api_name.lower()
        label_lower = doc.label.lower()
        desc_lower = (doc.description or "").lower()

        for token in query.tokens:
            token_lower = token.lower().rstrip("*?")

            if doc.api_name.lower() == token_lower:
                score += 50.0
                matched_fields.append("api_name_exact")

            if api_lower.startswith(token_lower):
                score += 30.0
                if "api_name_exact" not in matched_fields:
                    matched_fields.append("api_name_prefix")

            if token_lower in api_lower:
                score += 20.0
                if "api_name_exact" not in matched_fields \
                        and "api_name_prefix" not in matched_fields:
                    matched_fields.append("api_name_partial")

            if label_lower == token_lower:
                score += 25.0
                matched_fields.append("label_exact")

            if label_lower.startswith(token_lower):
                score += 15.0
                if "label_exact" not in matched_fields:
                    matched_fields.append("label_prefix")

            if token_lower in label_lower:
                score += 10.0
                if "label_exact" not in matched_fields and "label_prefix" not in matched_fields:
                    matched_fields.append("label_partial")

            if token_lower in desc_lower:
                score += 5.0
                matched_fields.append("description")

            if doc.namespace and token_lower in doc.namespace.lower():
                score += 8.0
                matched_fields.append("namespace")

        for phrase in query.exact_phrases:
            if phrase.lower() == api_lower:
                score += 50.0
                matched_fields.append("phrase_api_exact")
            elif phrase.lower() in api_lower:
                score += 25.0
                matched_fields.append("phrase_api_contains")
            if phrase.lower() == label_lower:
                score += 25.0
                matched_fields.append("phrase_label_exact")
            elif phrase.lower() in label_lower:
                score += 15.0
                matched_fields.append("phrase_label_contains")

        for exclude_token in query.exclude_tokens:
            if exclude_token in api_lower or exclude_token in label_lower:
                score = 0.0
                return score, []

        type_weight = _TYPE_WEIGHTS.get(doc.metadata_type, 0.5)
        score *= type_weight

        score += doc.dependency_score * 2.0
        score += doc.popularity_score * 1.0
        score += min(doc.edge_count, 100) * 0.5

        return score, matched_fields
