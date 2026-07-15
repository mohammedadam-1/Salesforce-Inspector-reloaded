from sfir_backend.api.dto.admin import (
    AdminAuditEntryResponse,
    AdminConfigResponse,
    AdminOrganizationResponse,
    AdminSystemResponse,
    AdminUserResponse,
    CacheStatisticsResponse,
)
from sfir_backend.api.dto.documentation import (
    DocumentationGenerateRequest,
    DocumentationItem,
    DocumentationListResponse,
    DocumentationResponse,
)
from sfir_backend.api.dto.impact import (
    ImpactAnalysisRequest,
    ImpactSimulateRequest,
    ImpactedComponent,
)
from sfir_backend.api.dto.search import (
    AutocompleteItem,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
)


class TestSearchDTOs:
    def test_search_request(self) -> None:
        r = SearchRequest(query="test")
        assert r.query == "test"
        assert r.limit == 50
        assert r.offset == 0

    def test_search_response(self) -> None:
        r = SearchResponse(items=[], total=0, limit=10, offset=0, query="q")
        assert r.query == "q"

    def test_search_result_item(self) -> None:
        item = SearchResultItem(
            id="123", component_type="ApexClass",
            component_name="MyClass", score=0.95,
        )
        assert item.score == 0.95

    def test_autocomplete_item(self) -> None:
        item = AutocompleteItem(
            id="1", component_name="Account",
            component_type="CustomObject", label="Account (CustomObject)",
        )
        assert item.label == "Account (CustomObject)"


class TestImpactDTOs:
    def test_impact_request(self) -> None:
        r = ImpactAnalysisRequest(
            component_type="ApexClass", component_name="MyClass",
        )
        assert r.max_depth == 3
        assert r.include_details is True

    def test_simulate_request(self) -> None:
        r = ImpactSimulateRequest(
            component_type="ApexClass", component_name="MyClass",
        )
        assert r.change_type == "modify"

    def test_impacted_component(self) -> None:
        c = ImpactedComponent(
            component_type="ApexClass", component_name="Dep",
            component_id="id1", impact_depth=1,
        )
        assert c.impact_depth == 1


class TestDocumentationDTOs:
    def test_generate_request(self) -> None:
        r = DocumentationGenerateRequest()
        assert r.format == "markdown"
        assert r.include_dependencies is True

    def test_documentation_item(self) -> None:
        item = DocumentationItem(
            id="1", component_type="ApexClass", component_name="Test",
        )
        assert item.description is None

    def test_list_response(self) -> None:
        r = DocumentationListResponse(items=[], total=50)
        assert r.total == 50

    def test_response(self) -> None:
        from datetime import datetime, UTC
        import uuid
        r = DocumentationResponse(
            id=uuid.uuid4(),
            status="completed",
            total_components=10,
            components=[],
            format="json",
            created_at=datetime.now(UTC),
        )
        assert r.status == "completed"


class TestAdminDTOs:
    def test_user_response(self) -> None:
        import uuid
        r = AdminUserResponse(
            id=uuid.uuid4(), email="test@test.com",
            display_name="Test", status="active",
            is_locked=False, login_attempts=0,
        )
        assert r.email == "test@test.com"

    def test_org_response(self) -> None:
        import uuid
        r = AdminOrganizationResponse(
            id=uuid.uuid4(), name="TestOrg",
            slug="test-org", status="active",
        )
        assert r.slug == "test-org"

    def test_audit_entry(self) -> None:
        import uuid
        from datetime import datetime, UTC
        r = AdminAuditEntryResponse(
            id=uuid.uuid4(), user_id=uuid.uuid4(),
            organization_id=uuid.uuid4(), action="user.login",
            resource_type="user", resource_id="123",
            details={"ip": "127.0.0.1"}, ip_address="127.0.0.1",
            created_at=datetime.now(UTC),
        )
        assert r.action == "user.login"

    def test_system_response(self) -> None:
        r = AdminSystemResponse(environment="testing")
        assert r.environment == "testing"

    def test_config_response(self) -> None:
        r = AdminConfigResponse(
            environment="testing", log_level="INFO",
            cors_origins=["*"], rate_limit_default=1000,
        )
        assert r.rate_limit_default == 1000

    def test_cache_statistics(self) -> None:
        r = CacheStatisticsResponse()
        assert r.hits == 0
