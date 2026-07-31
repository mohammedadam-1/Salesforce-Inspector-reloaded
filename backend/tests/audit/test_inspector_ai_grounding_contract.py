from __future__ import annotations

import re
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent


def read_repo_file(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def registered_salesforce_graph_types() -> set[str]:
    container = read_repo_file("backend/src/sfir_backend/config/container.py")
    body = re.search(
        r"def _make_parser_registry\(self\).*?return registry",
        container,
        re.DOTALL,
    )
    assert body, "Container._make_parser_registry was not found"

    parser_to_metadata_type = {
        "ApexClassParser": "ApexClass",
        "ApexTriggerParser": "ApexTrigger",
        "CustomObjectParser": "CustomObject",
        "LayoutParser": "Layout",
        "ValidationRuleParser": "ValidationRule",
    }
    parser_names = set(re.findall(r"registry\.register\((\w+Parser)\(\)\)", body.group(0)))
    return {
        parser_to_metadata_type[name]
        for name in parser_names
        if name in parser_to_metadata_type
    }


def test_ai_route_and_health_route_contract_is_registered() -> None:
    from sfir_backend.main import app

    paths = set(app.openapi()["paths"])

    assert "/api/v1/health/live" in paths
    assert "/api/v1/health" not in paths
    assert "/api/v1/ai/chat" in paths


def test_backend_auth_scheme_is_bearer_jwt_only() -> None:
    deps = read_repo_file("backend/src/sfir_backend/api/deps.py")
    middleware = read_repo_file("backend/src/sfir_backend/api/middleware.py")
    backend_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (REPO_ROOT / "backend/src/sfir_backend").rglob("*.py")
    )

    assert "authorization: str | None = Header" in deps
    assert "scheme.lower() != \"bearer\"" in deps
    assert "auth_header.startswith(\"Bearer \")" in middleware
    assert "APIKeyHeader" not in backend_source
    assert "X-API-Key" not in backend_source


def test_frontend_ai_clients_send_bearer_token_only() -> None:
    client_files = [
        "addon/services/aiApiClient.js",
        "addon/backend_service.js",
        "addon/components/InspectorAiBackendConfig.js",
    ]
    source = "\n".join(read_repo_file(path) for path in client_files)

    assert "\"Authorization\": \"Bearer \" + config.apiKey" in source
    assert "\"Authorization\": \"Bearer \" + apiKey" in source
    assert "X-API-Key" not in source
    assert "X-Api-Key" not in source


def test_current_graph_parser_coverage_snapshot() -> None:
    assert registered_salesforce_graph_types() == {
        "ApexClass",
        "ApexTrigger",
        "CustomObject",
        "Layout",
        "ValidationRule",
    }


@pytest.mark.xfail(
    strict=True,
    reason="Inspector AI does not yet register parsers for the full requested metadata surface.",
)
def test_parser_registry_covers_required_salesforce_metadata_contract() -> None:
    required_metadata_types = {
        "CustomObject",
        "CustomField",
        "ValidationRule",
        "Flow",
        "ApexClass",
        "ApexTrigger",
        "PermissionSet",
        "PermissionSetGroup",
        "Profile",
        "Role",
        "RecordType",
        "Layout",
        "CompactLayout",
        "FlexiPage",
        "Report",
        "Dashboard",
        "FormulaField",
        "CustomMetadata",
        "CustomSetting",
        "NamedCredential",
        "ConnectedApp",
        "RemoteSiteSetting",
        "EmailTemplate",
        "ApprovalProcess",
        "AssignmentRules",
        "EscalationRules",
        "SharingRule",
        "Queue",
        "Group",
        "PlatformEvent",
        "LightningComponentBundle",
        "AuraDefinitionBundle",
        "ApexPage",
        "StaticResource",
    }

    missing = required_metadata_types - registered_salesforce_graph_types()
    assert not missing, f"Missing parser coverage for: {sorted(missing)}"


@pytest.mark.xfail(
    strict=True,
    reason="AI context retriever is constructed without registered metadata/search/graph retrievers.",
)
def test_ai_context_retriever_is_wired_to_real_backend_fact_sources() -> None:
    container = read_repo_file("backend/src/sfir_backend/config/container.py")
    orchestrator_body = re.search(
        r"def _make_ai_orchestrator\(self\).*?return AIOrchestrator",
        container,
        re.DOTALL,
    )
    assert orchestrator_body, "Container._make_ai_orchestrator was not found"

    required_retrievers = {
        '"metadata"',
        '"search"',
        '"dependency_graph"',
        '"impact_analysis"',
    }
    body = orchestrator_body.group(0)
    missing = [
        retriever
        for retriever in required_retrievers
        if f"register_retriever({retriever}" not in body
    ]
    assert not missing, f"Missing ContextRetriever registrations: {missing}"


def test_engineering_tools_use_authenticated_org_context() -> None:
    engineering_tools = read_repo_file(
        "backend/src/sfir_backend/application/use_cases/ai/engineering_tools.py",
    )

    assert "org_id = uuid.uuid4()" not in engineering_tools


@pytest.mark.xfail(
    strict=True,
    reason="Non-streaming chat asks the LLM directly; deterministic backend tool execution is not enforced.",
)
def test_chat_path_runs_backend_tools_before_provider_response() -> None:
    coordinator = read_repo_file(
        "backend/src/sfir_backend/application/use_cases/ai/coordinator.py",
    )
    process_request_body = re.search(
        r"async def process_request\(.*?async def _retrieve_context",
        coordinator,
        re.DOTALL,
    )
    assert process_request_body, "AIRequestCoordinator.process_request was not found"

    body = process_request_body.group(0)
    assert "tool_registry.execute" in body
    assert "tools=" in body


@pytest.mark.xfail(
    strict=True,
    reason="AI tool calls do not currently emit source citations tied to executed backend facts.",
)
def test_tool_results_emit_citations_and_confidence_from_backend_facts() -> None:
    coordinator = read_repo_file(
        "backend/src/sfir_backend/application/use_cases/ai/coordinator.py",
    )

    assert "tool_complete" in coordinator
    assert "Citation(" in coordinator
    assert "score_from_citations" in coordinator
