"""Tests for search engine: index, query parser, ranking, filter, autocomplete, services, engine."""

from datetime import UTC, datetime

from sfir_backend.domain.search.models import (
    SearchDocument,
    SearchFilter,
    SearchPagination,
    SearchQuery,
    SearchSort,
)
from sfir_backend.infrastructure.search import (
    AutocompleteService,
    InvertedIndex,
    MetadataSearchService,
    QueryParser,
    SearchEngine,
    SearchFilterEngine,
    SearchIndex,
    SearchRankingEngine,
    SearchResultFormatter,
    SearchStatistics,
)


def make_doc(
    api_name: str,
    metadata_type: str = "object",
    label: str = "",
    description: str = "",
    namespace: str | None = None,
    org_id: str = "",
    status: str = "active",
) -> SearchDocument:
    return SearchDocument(
        id=f"{metadata_type}:{api_name}",
        api_name=api_name,
        label=label or api_name,
        description=description,
        metadata_type=metadata_type,
        namespace=namespace,
        organization_id=org_id,
        status=status,
    )


# ─── InvertedIndex ──────────────────────────────────────────────

class TestInvertedIndex:
    def test_index_and_search_term(self) -> None:
        idx = InvertedIndex()
        idx.index_document("1", "Account Contact", "default")
        idx.index_document("2", "Account Opportunity", "default")
        assert "1" in idx.search_term("account")
        assert "2" in idx.search_term("account")
        assert "1" in idx.search_term("contact")
        assert "2" not in idx.search_term("contact")

    def test_search_prefix(self) -> None:
        idx = InvertedIndex()
        idx.index_document("1", "AccountObject", "default")
        idx.index_document("2", "AccountContact", "default")
        idx.index_document("3", "ApexClass", "default")
        result = idx.search_prefix("acc")
        assert "1" in result
        assert "2" in result
        assert "3" not in result

    def test_search_suffix(self) -> None:
        idx = InvertedIndex()
        idx.index_document("1", "MyController", "default")
        idx.index_document("2", "OtherController", "default")
        idx.index_document("3", "MyClass", "default")
        result = idx.search_suffix("controller")
        assert "1" in result
        assert "2" in result
        assert "3" not in result

    def test_search_wildcard(self) -> None:
        idx = InvertedIndex()
        idx.index_document("1", "Account", "default")
        idx.index_document("2", "AccountHistory", "default")
        idx.index_document("3", "ApexClass", "default")
        result = idx.search_wildcard("Account*")
        assert "1" in result
        assert "2" in result
        assert "3" not in result

    def test_field_filtered_search(self) -> None:
        idx = InvertedIndex()
        idx.index_document("1", "Account", "api_name")
        idx.index_document("2", "Account", "description")
        assert "1" in idx.search_term("account", "api_name")
        assert "2" not in idx.search_term("account", "api_name")

    def test_clear(self) -> None:
        idx = InvertedIndex()
        idx.index_document("1", "test", "default")
        assert idx.total_documents == 1
        idx.clear()
        assert idx.total_documents == 0

    def test_all_documents(self) -> None:
        idx = InvertedIndex()
        idx.index_document("1", "a", "default")
        idx.index_document("2", "b", "default")
        assert idx.all_documents() == {"1", "2"}


# ─── SearchIndex ────────────────────────────────────────────────

class TestSearchIndex:
    def test_index_and_retrieve(self) -> None:
        idx = SearchIndex()
        doc = make_doc("Account", label="Account Object")
        idx.index_document(doc)
        assert idx.total_documents == 1
        retrieved = idx.get_document(doc.id)
        assert retrieved is not None
        assert retrieved.api_name == "Account"

    def test_search_tokens(self) -> None:
        idx = SearchIndex()
        idx.index_document(make_doc("Account", label="Account Object"))
        idx.index_document(make_doc("Contact", label="Contact Object"))
        result = idx.search(["account"])
        assert len(result) == 1

    def test_search_and_operator(self) -> None:
        idx = SearchIndex()
        idx.index_document(make_doc("Account", label="Account Object"))
        idx.index_document(make_doc("AccountHistory", label="Account History"))
        result = idx.search(["account", "history"], operator="AND")
        assert len(result) == 1
        assert "object:AccountHistory" in result

    def test_search_or_operator(self) -> None:
        idx = SearchIndex()
        idx.index_document(make_doc("Account"))
        idx.index_document(make_doc("Contact"))
        result = idx.search(["account", "contact"], operator="OR")
        assert len(result) == 2

    def test_search_by_type(self) -> None:
        idx = SearchIndex()
        idx.index_document(make_doc("Account", metadata_type="object"))
        idx.index_document(make_doc("MyClass", metadata_type="apex_class"))
        objects = idx.search_by_type("object")
        assert len(objects) == 1
        assert objects[0].api_name == "Account"

    def test_suggest(self) -> None:
        idx = SearchIndex()
        idx.index_document(make_doc("Account"))
        idx.index_document(make_doc("AccountContact"))
        idx.index_document(make_doc("ApexClass"))
        suggestions = idx.suggest("acc", limit=5)
        assert len(suggestions) >= 1
        assert any("acc" in s.lower() for s in suggestions)

    def test_count_by_type(self) -> None:
        idx = SearchIndex()
        idx.index_document(make_doc("Account", metadata_type="object"))
        idx.index_document(make_doc("MyClass", metadata_type="apex_class"))
        counts = idx.count_by_type()
        assert counts.get("object") == 1
        assert counts.get("apex_class") == 1

    def test_clear(self) -> None:
        idx = SearchIndex()
        idx.index_document(make_doc("Account"))
        assert idx.total_documents == 1
        idx.clear()
        assert idx.total_documents == 0


# ─── QueryParser ────────────────────────────────────────────────

class TestQueryParser:
    def test_parse_simple(self) -> None:
        parser = QueryParser()
        q = parser.parse("Account")
        assert q.raw_query == "Account"
        assert len(q.tokens) >= 1
        assert "account" in q.tokens

    def test_parse_phrase(self) -> None:
        parser = QueryParser()
        q = parser.parse('"Account Object"')
        assert len(q.exact_phrases) == 1
        assert q.exact_phrases[0] == "Account Object"

    def test_parse_exclude(self) -> None:
        parser = QueryParser()
        q = parser.parse("Account -Contact")
        assert len(q.exclude_tokens) >= 1
        assert "contact" in q.exclude_tokens

    def test_parse_multiple_tokens(self) -> None:
        parser = QueryParser()
        q = parser.parse("Account Contact")
        assert len(q.tokens) >= 2
        assert "account" in q.tokens
        assert "contact" in q.tokens

    def test_parse_with_filters(self) -> None:
        parser = QueryParser()
        q = parser.parse(
            "Account",
            filters=[{"field": "status", "value": "active", "operator": "eq"}],
        )
        assert len(q.filters) == 1
        assert q.filters[0].field == "status"

    def test_parse_with_sort(self) -> None:
        parser = QueryParser()
        q = parser.parse("Account", sort_field="api_name", sort_direction="asc")
        assert q.sort.field == "api_name"
        assert q.sort.direction == "asc"

    def test_parse_with_pagination(self) -> None:
        parser = QueryParser()
        q = parser.parse("Account", offset=20, limit=10)
        assert q.pagination.offset == 20
        assert q.pagination.limit == 10

    def test_parse_with_metadata_types(self) -> None:
        parser = QueryParser()
        q = parser.parse("Account", metadata_types=["object", "field"])
        assert "object" in q.metadata_types
        assert "field" in q.metadata_types

    def test_parse_empty(self) -> None:
        parser = QueryParser()
        q = parser.parse("")
        assert q.tokens == []

    def test_parse_saved_query(self) -> None:
        parser = QueryParser()
        tokens = parser.parse_saved_query("Account Contact")
        assert "account" in tokens
        assert "contact" in tokens


# ─── SearchRankingEngine ────────────────────────────────────────

class TestSearchRankingEngine:
    def test_exact_api_name_ranked_highest(self) -> None:
        engine = SearchRankingEngine()
        docs = [
            make_doc("AccountObject", label="Account History"),
            make_doc("Account", label="Account Object"),
        ]
        q = SearchQuery(raw_query="Account", tokens=["account"])
        ranked = engine.rank(docs, q)
        assert len(ranked) == 2
        assert ranked[0][0].api_name == "Account"

    def test_label_match_scores(self) -> None:
        engine = SearchRankingEngine()
        docs = [
            make_doc("X1", label="Account Object"),
            make_doc("X2", label="Contact Object"),
        ]
        q = SearchQuery(raw_query="Account", tokens=["account"])
        ranked = engine.rank(docs, q)
        assert len(ranked) == 1
        assert ranked[0][0].api_name == "X1"

    def test_description_match(self) -> None:
        engine = SearchRankingEngine()
        docs = [
            make_doc("X1", label="Obj", description="This is an account object"),
            make_doc("X2", label="Obj2", description="Something else"),
        ]
        q = SearchQuery(raw_query="Account", tokens=["account"])
        ranked = engine.rank(docs, q)
        assert len(ranked) == 1
        assert ranked[0][0].api_name == "X1"

    def test_type_weight_applied(self) -> None:
        engine = SearchRankingEngine()
        obj = make_doc("Account", metadata_type="object", label="Account")
        field = make_doc("Account.Name", metadata_type="field", label="Account Name")
        q = SearchQuery(raw_query="Account", tokens=["account"])
        ranked = engine.rank([obj, field], q)
        assert len(ranked) == 2

    def test_exclude_token_removes_result(self) -> None:
        engine = SearchRankingEngine()
        docs = [make_doc("Account", label="Account"), make_doc("Contact", label="Contact")]
        q = SearchQuery(raw_query="Account -Contact", tokens=["account"], exclude_tokens=["contact"])
        ranked = engine.rank(docs, q)
        assert len(ranked) == 1
        assert ranked[0][0].api_name == "Account"

    def test_dependency_boost(self) -> None:
        engine = SearchRankingEngine()
        low = make_doc("Account", label="Account", metadata_type="object")
        high = make_doc("Account", label="Account", metadata_type="object")
        high.dependency_score = 5.0
        high.edge_count = 10
        q = SearchQuery(raw_query="Account", tokens=["account"])
        ranked = engine.rank([low, high], q)
        assert len(ranked) == 2
        assert ranked[0][0].dependency_score >= ranked[1][0].dependency_score

    def test_exact_phrase_boost(self) -> None:
        engine = SearchRankingEngine()
        docs = [
            make_doc("MyController", label="Controller Class"),
            make_doc("OtherController", label="Other Controller"),
        ]
        q = SearchQuery(raw_query='"MyController"', tokens=[], exact_phrases=["MyController"])
        ranked = engine.rank(docs, q)
        assert len(ranked) >= 1
        assert ranked[0][0].api_name == "MyController"

    def test_no_match_returns_empty(self) -> None:
        engine = SearchRankingEngine()
        docs = [make_doc("Account", label="Account")]
        q = SearchQuery(raw_query="Zoo", tokens=["zoo"])
        ranked = engine.rank(docs, q)
        assert len(ranked) == 0


# ─── SearchFilterEngine ─────────────────────────────────────────

class TestSearchFilterEngine:
    def test_filter_by_metadata_type(self) -> None:
        engine = SearchFilterEngine()
        docs = [make_doc("Account", metadata_type="object"), make_doc("MyClass", metadata_type="apex_class")]
        q = SearchQuery(raw_query="", metadata_types=["object"])
        result = engine.apply(docs, q)
        assert len(result) == 1
        assert result[0].api_name == "Account"

    def test_filter_by_organization(self) -> None:
        engine = SearchFilterEngine()
        docs = [make_doc("Account", org_id="org1"), make_doc("Contact", org_id="org2")]
        q = SearchQuery(raw_query="", organization_id="org1")
        result = engine.apply(docs, q)
        assert len(result) == 1
        assert result[0].api_name == "Account"

    def test_filter_by_namespace(self) -> None:
        engine = SearchFilterEngine()
        docs = [make_doc("Account", namespace="ns1"), make_doc("Contact", namespace="ns2")]
        q = SearchQuery(raw_query="", namespace="ns1")
        result = engine.apply(docs, q)
        assert len(result) == 1
        assert result[0].api_name == "Account"

    def test_filter_eq(self) -> None:
        engine = SearchFilterEngine()
        docs = [make_doc("Account", status="active"), make_doc("Contact", status="inactive")]
        q = SearchQuery(raw_query="", filters=[SearchFilter(field="status", value="active", operator="eq")])
        result = engine.apply(docs, q)
        assert len(result) == 1
        assert result[0].api_name == "Account"

    def test_filter_in(self) -> None:
        engine = SearchFilterEngine()
        docs = [make_doc("Account", metadata_type="object"), make_doc("MyClass", metadata_type="apex_class")]
        q = SearchQuery(
            raw_query="",
            filters=[SearchFilter(field="metadata_type", value=["object", "apex_class"], operator="in")],
        )
        result = engine.apply(docs, q)
        assert len(result) == 2

    def test_filter_contains(self) -> None:
        engine = SearchFilterEngine()
        docs = [make_doc("Account", label="Account Object"), make_doc("Contact", label="Contact")]
        q = SearchQuery(raw_query="", filters=[SearchFilter(field="api_name", value="count", operator="contains")])
        result = engine.apply(docs, q)
        assert len(result) == 1
        assert result[0].api_name == "Account"


# ─── AutocompleteService ────────────────────────────────────────

class TestAutocompleteService:
    def test_suggest_from_index(self) -> None:
        index = SearchIndex()
        index.index_document(make_doc("Account"))
        index.index_document(make_doc("AccountHistory"))
        svc = AutocompleteService(index)
        suggestions = svc.suggest("acc", limit=5)
        assert len(suggestions) >= 1
        assert any("acc" in s.lower() for s in suggestions)

    def test_record_and_recent(self) -> None:
        index = SearchIndex()
        svc = AutocompleteService(index)
        svc.record_search("Account")
        svc.record_search("Contact")
        recent = svc.recent_searches(5)
        assert "account" in recent
        assert "contact" in recent

    def test_popular_suggestions(self) -> None:
        index = SearchIndex()
        svc = AutocompleteService(index)
        svc.record_search("Account")
        svc.record_search("Account")
        svc.record_search("Contact")
        suggestions = svc.suggest("", limit=5)
        assert "account" in suggestions

    def test_clear(self) -> None:
        index = SearchIndex()
        svc = AutocompleteService(index)
        svc.record_search("Account")
        svc.clear()
        assert svc.recent_searches() == []


# ─── SearchResultFormatter ──────────────────────────────────────

class TestSearchResultFormatter:
    def test_format_empty(self) -> None:
        formatter = SearchResultFormatter()
        import time
        start = time.time()
        q = SearchQuery(raw_query="test", tokens=["test"])
        response = formatter.format([], q, 0, start)
        assert response.total_count == 0
        assert response.results == []
        assert response.query == "test"

    def test_format_results(self) -> None:
        formatter = SearchResultFormatter()
        import time
        start = time.time()
        doc = make_doc("Account", label="Account Object")
        q = SearchQuery(raw_query="Account", tokens=["account"])
        scored = [(doc, 50.0, ["api_name_exact"])]
        response = formatter.format(scored, q, 1, start)
        assert response.total_count == 1
        assert len(response.results) == 1
        assert response.results[0].score == 50.0
        assert response.results[0].rank == 1

    def test_format_pagination(self) -> None:
        formatter = SearchResultFormatter()
        import time
        start = time.time()
        docs = [make_doc(f"Doc{i}") for i in range(25)]
        q = SearchQuery(
            raw_query="Doc",
            tokens=["doc"],
            pagination=SearchPagination(offset=20, limit=10),
        )
        scored = [(d, float(25 - i), ["matched"]) for i, d in enumerate(docs)]
        response = formatter.format(scored, q, 25, start)
        assert response.total_count == 25
        assert len(response.results) == 5
        assert response.page == 3
        assert response.total_pages == 3

    def test_highlights(self) -> None:
        formatter = SearchResultFormatter()
        import time
        start = time.time()
        doc = make_doc("AccountObject", label="Account Object", description="Standard account object")
        q = SearchQuery(raw_query="Account", tokens=["account"])
        scored = [(doc, 50.0, ["api_name_exact"])]
        response = formatter.format(scored, q, 1, start)
        assert len(response.results) == 1
        highlights = response.results[0].highlights
        assert "api_name" in highlights or "label" in highlights or "description" in highlights


# ─── MetadataSearchService ──────────────────────────────────────

class TestMetadataSearchService:
    def test_search_finds_matching(self) -> None:
        engine = SearchEngine()
        engine.index_components([
            make_doc("Account", metadata_type="object"),
            make_doc("Contact", metadata_type="object"),
        ])
        response = engine.search_metadata("Account")
        assert response.total_count >= 1

    def test_search_by_type_filter(self) -> None:
        engine = SearchEngine()
        engine.index_components([
            make_doc("Account", metadata_type="object"),
            make_doc("MyClass", metadata_type="apex_class"),
        ])
        response = engine.search_metadata("", metadata_types=["apex_class"])
        assert response.total_count >= 1
        assert response.results[0].document.metadata_type == "apex_class"

    def test_search_no_results(self) -> None:
        engine = SearchEngine()
        engine.index_components([make_doc("Account")])
        response = engine.search_metadata("NonExistent")
        assert response.total_count == 0

    def test_search_with_exclusion(self) -> None:
        engine = SearchEngine()
        engine.index_components([
            make_doc("Account", metadata_type="object"),
            make_doc("AccountContact", metadata_type="object"),
        ])
        response = engine.search_metadata("Account -Contact")
        assert response.total_count >= 1
        for r in response.results:
            assert "contact" not in r.document.api_name.lower()


# ─── GlobalSearchService ────────────────────────────────────────

class TestGlobalSearchService:
    def test_global_search(self) -> None:
        engine = SearchEngine()
        engine.index_components([
            make_doc("Account", metadata_type="object"),
            make_doc("MyClass", metadata_type="apex_class"),
            make_doc("Account.Name", metadata_type="field"),
        ])
        response = engine.global_search("Account")
        assert response.total_count >= 2


# ─── SearchEngine ───────────────────────────────────────────────

class TestSearchEngine:
    def test_index_components(self) -> None:
        engine = SearchEngine()
        count = engine.index_components([
            make_doc("Account", metadata_type="object"),
            make_doc("Contact", metadata_type="object"),
        ])
        assert count == 2
        assert engine.index.total_documents == 2

    def test_autocomplete(self) -> None:
        engine = SearchEngine()
        engine.index_components([
            make_doc("Account"),
            make_doc("AccountHistory"),
        ])
        suggestions = engine.autocomplete("acc", limit=5)
        assert len(suggestions) >= 1
        assert any("acc" in s.get("text", "").lower() for s in suggestions)

    def test_recent_searches(self) -> None:
        engine = SearchEngine()
        engine.record_search("Account", 5)
        engine.record_search("Contact", 10)
        recent = engine.recent_searches(5)
        assert "account" in recent
        assert "contact" in recent

    def test_search_statistics(self) -> None:
        engine = SearchEngine()
        engine.index_components([make_doc("Account")])
        engine.search_metadata("Account")
        stats = engine.search_statistics()
        assert stats["total_queries"] >= 1
        assert stats["indexed_documents"] >= 1

    def test_index_stats(self) -> None:
        engine = SearchEngine()
        engine.index_components([make_doc("Account", metadata_type="object")])
        stats = engine.index_stats()
        assert stats["total_documents"] == 1
        assert stats["total_types"] == 1

    def test_clear_index(self) -> None:
        engine = SearchEngine()
        engine.index_components([make_doc("Account")])
        assert engine.index.total_documents == 1
        engine.clear_index()
        assert engine.index.total_documents == 0

    def test_search_pagination(self) -> None:
        engine = SearchEngine()
        docs = [make_doc(f"Doc{i}", metadata_type="object") for i in range(30)]
        engine.index_components(docs)
        page1 = engine.global_search("Doc", limit=10, offset=0)
        assert len(page1.results) == 10
        page2 = engine.global_search("Doc", limit=10, offset=10)
        assert len(page2.results) == 10
        page3 = engine.global_search("Doc", limit=10, offset=20)
        assert len(page3.results) == 10

    def test_empty_index_search(self) -> None:
        engine = SearchEngine()
        response = engine.global_search("test")
        assert response.total_count == 0


# ─── SearchStatistics ───────────────────────────────────────────

class TestSearchStatistics:
    def test_record_and_snapshot(self) -> None:
        from sfir_backend.infrastructure.search.index import SearchIndex
        stats = SearchStatistics(SearchIndex())
        stats.record_query("global", 50.0, True)
        stats.record_query("metadata", 100.0, True)
        stats.record_query("dependency", 200.0, False)
        snapshot = stats.snapshot()
        assert snapshot["total_queries"] == 3
        assert snapshot["total_failures"] == 1
        assert snapshot["avg_latency_ms"] > 0
        assert snapshot["query_type_counts"]["global"] == 1

    def test_reset(self) -> None:
        from sfir_backend.infrastructure.search.index import SearchIndex
        stats = SearchStatistics(SearchIndex())
        stats.record_query("global", 50.0)
        stats.reset()
        snapshot = stats.snapshot()
        assert snapshot["total_queries"] == 0


# ─── Large Dataset ──────────────────────────────────────────────

class TestLargeDataset:
    def test_index_1000_documents(self) -> None:
        engine = SearchEngine()
        docs = [
            make_doc(
                f"Object{i}",
                metadata_type="object",
                label=f"Object {i}",
                description=f"Description for object {i}",
            )
            for i in range(1000)
        ]
        count = engine.index_components(docs)
        assert count == 1000

    def test_search_among_1000(self) -> None:
        engine = SearchEngine()
        docs = [
            make_doc(
                f"Object{i}",
                metadata_type="object",
                label=f"Object {i}" if i % 2 == 0 else f"CustomObject{i}",
            )
            for i in range(1000)
        ]
        engine.index_components(docs)
        response = engine.global_search("CustomObject")
        assert response.total_count >= 1

    def test_prefix_search_large(self) -> None:
        engine = SearchEngine()
        docs = [
            make_doc(
                f"Account{i}" if i < 500 else f"Contact{i}",
                metadata_type="object",
            )
            for i in range(1000)
        ]
        engine.index_components(docs)
        response = engine.global_search("Acc*")
        assert response.total_count >= 1

    def test_type_filter_large(self) -> None:
        engine = SearchEngine()
        docs = []
        for i in range(500):
            docs.append(make_doc(f"Obj{i}", metadata_type="object"))
            docs.append(make_doc(f"Field{i}", metadata_type="field"))
        engine.index_components(docs)
        response = engine.search_metadata("", metadata_types=["field"])
        assert response.total_count == 500
