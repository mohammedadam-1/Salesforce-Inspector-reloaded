from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from sfir_backend.api.deps import (
    get_current_org_id,
    get_current_user_id,
    get_documentation_engine,
    get_graph_service,
    get_rbac_service,
)
from sfir_backend.api.dto.documentation import (
    DocumentationExportResponse,
    DocumentationGenerateRequest,
    DocumentationItem,
    DocumentationListResponse,
    DocumentationResponse,
)
from sfir_backend.application.use_cases.graph.service import GraphService
from sfir_backend.application.use_cases.rbac import RBACUseCase
from sfir_backend.domain.documentation.models import (
    DocumentationFormat,
    DocumentationPage,
    DocumentationReport,
    GenerateRequest,
    ReportType,
)
from sfir_backend.infrastructure.documentation.engine import DocumentationEngine
from sfir_backend.shared.exceptions.domain import EntityNotFoundError

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/documentation", tags=["Documentation"])


def _parse_format(fmt: str) -> DocumentationFormat:
    try:
        return DocumentationFormat(fmt)
    except ValueError:
        return DocumentationFormat.MARKDOWN


def _page_to_item(page: DocumentationPage) -> DocumentationItem:
    description_text = ""
    for sec in page.sections:
        if sec.content:
            description_text = sec.content[:200]
            break
    return DocumentationItem(
        id=page.id or str(uuid.uuid4()),
        component_type=page.component_type,
        component_name=page.api_name or page.component_key,
        description=description_text or None,
        fields=[
            {"name": sec.title, "value": sec.content[:100]}
            for sec in page.sections[:10]
        ] or None,
        dependencies=[
            {"name": sec.title, "type": sec.section_type.value}
            for sec in page.sections
            if sec.section_type.value in ("dependencies", "references")
        ] or None,
        usage=(
            [sec.content[:100] for sec in page.sections if sec.section_type.value == "references"]
            or None
        ),
        generated_at=page.generated_at,
    )


def _report_to_response(report: DocumentationReport) -> DocumentationResponse:
    return DocumentationResponse(
        id=uuid.uuid5(uuid.NAMESPACE_DNS, report.id or str(datetime.now(tz=UTC))),
        status="completed",
        total_components=len(report.pages),
        components=[_page_to_item(p) for p in report.pages],
        format=report.format.value,
        created_at=report.generated_at,
    )


@router.get("")
async def _list_documentation(
    component_type: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    sort_by: str | None = Query(default=None, pattern=r"^(name|type|updated_at)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    _user_id: uuid.UUID = Depends(get_current_user_id),
    rbac: RBACUseCase = Depends(get_rbac_service),
    engine: DocumentationEngine = Depends(get_documentation_engine),
    graph_service: GraphService = Depends(get_graph_service),
) -> DocumentationListResponse:
    if not org_id:
        return DocumentationListResponse(items=[], total=0)
    await rbac.require_permission(_user_id, org_id, "documentation:generate")
    overview = await asyncio.to_thread(
        engine.component_inventory, component_type,
    )
    items = [_page_to_item(p) for p in overview.pages]

    if search:
        search_lower = search.lower()
        items = [i for i in items if search_lower in i.component_name.lower()]

    if sort_by == "type":
        items.sort(key=lambda i: (i.component_type or "", i.component_name or ""))
    elif sort_by == "updated_at":
        items.sort(key=lambda i: i.generated_at or "", reverse=True)
    else:
        items.sort(key=lambda i: i.component_name or "")

    total = len(items)
    paginated = items[offset:offset + limit]
    return DocumentationListResponse(items=paginated, total=total)


@router.post("/generate")
async def _generate_documentation(
    request: DocumentationGenerateRequest,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    _user_id: uuid.UUID = Depends(get_current_user_id),
    rbac: RBACUseCase = Depends(get_rbac_service),
    engine: DocumentationEngine = Depends(get_documentation_engine),
    graph_service: GraphService = Depends(get_graph_service),
) -> DocumentationResponse:
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")
    await rbac.require_permission(_user_id, org_id, "documentation:generate")
    format_enum = _parse_format(request.format)
    keys: list[str] = []
    if request.component_ids:
        keys.extend(request.component_ids)
    if request.metadata_types:
        inventory = await asyncio.to_thread(engine.component_inventory)
        for page in inventory.pages:
            if page.component_type in request.metadata_types and page.component_key not in keys:
                keys.append(page.component_key)
    sections: list[str] | None = None
    if not request.include_dependencies:
        sections = []
    if not request.include_usage:
        if sections is None:
            sections = []
        sections.append("references")
    gen_req = GenerateRequest(
        component_keys=keys,
        report_type=ReportType.COMPONENT,
        format=format_enum,
        include_sections=sections,
    )
    report = await asyncio.to_thread(engine.generate, gen_req)
    return _report_to_response(report)


@router.get("/export")
async def _export_documentation(
    format: str = Query(default="markdown", pattern=r"^(markdown|html|json)$"),
    component_type: str | None = Query(default=None),
    component_name: str | None = Query(default=None),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    _user_id: uuid.UUID = Depends(get_current_user_id),
    _rbac: RBACUseCase = Depends(get_rbac_service),
    engine: DocumentationEngine = Depends(get_documentation_engine),
) -> DocumentationExportResponse:
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")
    format_enum = _parse_format(format)
    if component_type and component_name:
        component_key = f"{component_type}/{component_name}"
        page = await asyncio.to_thread(
            engine.generate_single, component_key, format_enum,
        )
        content = page
        total = 1
    else:
        report = await asyncio.to_thread(engine.metadata_report)
        content = report
        total = len(report.pages)
    exported = await asyncio.to_thread(
        engine.export_report,
        content if isinstance(content, DocumentationReport)
        else DocumentationReport(
            id=str(uuid.uuid4()),
            pages=[content],
            format=format_enum,
        ),
        format_enum,
    )
    return DocumentationExportResponse(
        format=format,
        content=exported,
        filename=f"documentation-{datetime.now(tz=UTC).strftime('%Y%m%d-%H%M%S')}.{format}",
        total_components=total,
    )


@router.get("/{component_type}/{component_name}")
async def _get_component_documentation(
    component_type: str,
    component_name: str,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    _user_id: uuid.UUID = Depends(get_current_user_id),
    _rbac: RBACUseCase = Depends(get_rbac_service),
    engine: DocumentationEngine = Depends(get_documentation_engine),
) -> DocumentationItem:
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")
    component_key = f"{component_type}/{component_name}"
    try:
        page = await asyncio.to_thread(
            engine.generate_single, component_key, DocumentationFormat.MARKDOWN,
        )
        if not page or (not page.title and not page.api_name):
            raise EntityNotFoundError(f"Documentation not found for {component_key}")
        return _page_to_item(page)
    except EntityNotFoundError:
        raise HTTPException(status_code=404, detail=f"Documentation not found: {component_key}")
    except Exception as exc:
        logger.error("documentation_generate_failed", component_key=component_key, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to generate documentation")
