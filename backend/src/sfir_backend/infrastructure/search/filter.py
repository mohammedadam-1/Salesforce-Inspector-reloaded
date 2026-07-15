from __future__ import annotations

from datetime import datetime

from sfir_backend.domain.search.models import SearchDocument, SearchQuery


class SearchFilterEngine:
    def apply(
        self,
        documents: list[SearchDocument],
        query: SearchQuery,
    ) -> list[SearchDocument]:
        result = documents
        if query.metadata_types:
            types = [t.lower() for t in query.metadata_types]
            result = [d for d in result if d.metadata_type.lower() in types]
        if query.organization_id:
            result = [
                d for d in result if d.organization_id == query.organization_id
            ]
        if query.namespace:
            result = [
                d for d in result if d.namespace == query.namespace
            ]
        for f in query.filters:
            result = self._apply_filter(result, f.field, f.value, f.operator)
        return result

    def _apply_filter(
        self,
        documents: list[SearchDocument],
        field: str,
        value: object,
        operator: str,
    ) -> list[SearchDocument]:
        if operator == "eq":
            return [d for d in documents if self._get_field(d, field) == value]
        if operator == "neq":
            return [d for d in documents if self._get_field(d, field) != value]
        if operator == "in":
            if not isinstance(value, list):
                return documents
            return [d for d in documents if self._get_field(d, field) in value]
        if operator == "nin":
            if not isinstance(value, list):
                return documents
            return [d for d in documents if self._get_field(d, field) not in value]
        if operator == "gt":
            return [d for d in documents if self._compare(self._get_field(d, field), value, "gt")]
        if operator == "gte":
            return [d for d in documents if self._compare(self._get_field(d, field), value, "gte")]
        if operator == "lt":
            return [d for d in documents if self._compare(self._get_field(d, field), value, "lt")]
        if operator == "lte":
            return [d for d in documents if self._compare(self._get_field(d, field), value, "lte")]
        if operator == "contains":
            return [
                d for d in documents
                if value and str(value).lower() in str(self._get_field(d, field)).lower()
            ]
        if operator == "startswith":
            return [
                d for d in documents
                if value and str(self._get_field(d, field)).lower().startswith(str(value).lower())
            ]
        if operator == "endswith":
            return [
                d for d in documents
                if value and str(self._get_field(d, field)).lower().endswith(str(value).lower())
            ]
        return documents

    def _get_field(self, doc: SearchDocument, field: str) -> object:
        return getattr(doc, field, None)

    def _compare(
        self,
        a: object,
        b: object,
        operator: str,
    ) -> bool:
        try:
            if isinstance(a, datetime) and isinstance(b, str):
                b_val: object = datetime.fromisoformat(b)
            elif isinstance(b, datetime) and isinstance(a, str):
                a_val: object = datetime.fromisoformat(str(a))
                a = a_val
            else:
                b_val = b
            if operator == "gt":
                return bool(a > b_val) if a is not None else False
            if operator == "gte":
                return bool(a >= b_val) if a is not None else False
            if operator == "lt":
                return bool(a < b_val) if a is not None else False
            if operator == "lte":
                return bool(a <= b_val) if a is not None else False
        except (ValueError, TypeError):
            return False
        return False
