"""Tests for search domain models."""

from datetime import UTC, datetime

from sfir_backend.domain.search.models import (
    RecentSearch,
    SavedSearch,
    SearchDocument,
    SearchFilter,
    SearchPagination,
    SearchQuery,
    SearchResponse,
    SearchResult,
    SearchSort,
    SearchSuggestion,
    SearchableType,
)


class TestSearchableType:
    def test_values(self) -> None:
        assert SearchableType.OBJECT == "object"
        assert SearchableType.FIELD == "field"
        assert SearchableType.APEX_CLASS == "apex_class"

    def test_all_types_present(self) -> None:
        types = {t.value for t in SearchableType}
        assert "object" in types
        assert "field" in types
        assert "apex_class" in types
        assert "trigger" in types
        assert "flow" in types
        assert "global" in types
        assert "dependency" in types


class TestSearchFilter:
    def test_defaults(self) -> None:
        f = SearchFilter()
        assert f.field == ""
        assert f.value is None
        assert f.operator == "eq"

    def test_full(self) -> None:
        f = SearchFilter(field="type", value="object", operator="eq")
        assert f.field == "type"
        assert f.value == "object"


class TestSearchSort:
    def test_defaults(self) -> None:
        s = SearchSort()
        assert s.field == ""
        assert s.direction == "desc"


class TestSearchPagination:
    def test_defaults(self) -> None:
        p = SearchPagination()
        assert p.offset == 0
        assert p.limit == 20
        assert p.max_limit == 100


class TestSearchQuery:
    def test_defaults(self) -> None:
        q = SearchQuery()
        assert q.raw_query == ""
        assert q.tokens == []
        assert q.organization_id == ""

    def test_has_query_empty(self) -> None:
        assert SearchQuery().has_query() is False

    def test_has_query_with_text(self) -> None:
        assert SearchQuery(raw_query="Account").has_query() is True

    def test_has_query_with_tokens(self) -> None:
        assert SearchQuery(tokens=["Account"]).has_query() is True


class TestSearchDocument:
    def test_defaults(self) -> None:
        d = SearchDocument()
        assert d.id == ""
        assert d.api_name == ""
        assert d.dependency_score == 0.0

    def test_searchable_text(self) -> None:
        d = SearchDocument(
            api_name="Account",
            label="Account Object",
            description="Standard object",
            namespace="ns",
        )
        text = d.searchable_text()
        assert "Account" in text
        assert "Account Object" in text
        assert "Standard object" in text
        assert "ns" in text

    def test_key(self) -> None:
        d = SearchDocument(api_name="Account", metadata_type="object")
        assert d.key == "object:Account"


class TestSearchResult:
    def test_defaults(self) -> None:
        r = SearchResult()
        assert r.score == 0.0
        assert r.rank == 0
        assert r.matched_fields == []
        assert r.highlights == {}


class TestSearchResponse:
    def test_defaults(self) -> None:
        r = SearchResponse()
        assert r.results == []
        assert r.total_count == 0
        assert r.took_ms == 0.0


class TestSearchSuggestion:
    def test_defaults(self) -> None:
        s = SearchSuggestion()
        assert s.text == ""
        assert s.score == 0.0


class TestSavedSearch:
    def test_defaults(self) -> None:
        s = SavedSearch()
        assert s.id == ""
        assert s.name == ""


class TestRecentSearch:
    def test_defaults(self) -> None:
        r = RecentSearch()
        assert r.id == ""
        assert r.query == ""
