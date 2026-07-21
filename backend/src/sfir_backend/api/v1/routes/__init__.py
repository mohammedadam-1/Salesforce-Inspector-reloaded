from fastapi import APIRouter

from sfir_backend.api.v1.routes.admin import router as admin_router
from sfir_backend.api.v1.routes.ai import router as ai_router
from sfir_backend.api.v1.routes.auth import router as auth_router
from sfir_backend.api.v1.routes.dependencies import router as deps_router
from sfir_backend.api.v1.routes.documentation import router as doc_router
from sfir_backend.api.v1.routes.graph import router as graph_router
from sfir_backend.api.v1.routes.health import router as health_router
from sfir_backend.api.v1.routes.impact import router as impact_router
from sfir_backend.api.v1.routes.jobs import router as jobs_router
from sfir_backend.api.v1.routes.metadata import router as metadata_router
from sfir_backend.api.v1.routes.metadata_sync import router as sync_router
from sfir_backend.api.v1.routes.observability import router as obs_router
from sfir_backend.api.v1.routes.organizations import router as org_router
from sfir_backend.api.v1.routes.salesforce import router as sf_router
from sfir_backend.api.v1.routes.search import router as search_router
from sfir_backend.api.v1.routes.security import router as security_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(org_router)
api_router.include_router(sf_router)
api_router.include_router(sync_router)
api_router.include_router(metadata_router)
api_router.include_router(graph_router)
api_router.include_router(deps_router)
api_router.include_router(search_router)
api_router.include_router(impact_router)
api_router.include_router(doc_router)
api_router.include_router(ai_router)
api_router.include_router(jobs_router)
api_router.include_router(obs_router)
api_router.include_router(security_router)
api_router.include_router(admin_router)
