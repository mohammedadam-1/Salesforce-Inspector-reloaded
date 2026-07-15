from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import text

from sfir_backend.config.container import Container
from sfir_backend.domain.observability.models import (
    DiagnosticReport,
    HealthComponentStatus,
    HealthReport,
)
from sfir_backend.infrastructure.observability.manager import ObservabilityManager

router = APIRouter(tags=["Observability"])


def _get_obs(request: Request) -> ObservabilityManager | None:
    try:
        container: Container = request.app.state.container
        return container.get_service("observability")
    except (AttributeError, KeyError):
        return None


@router.get("/health/check")
async def comprehensive_health(request: Request) -> HealthReport:
    obs = _get_obs(request)
    if obs:
        return await obs.health.run_all_checks(
            db_check_fn=_make_db_check(request),
        )
    return HealthReport(overall_status=HealthComponentStatus.UNHEALTHY)


@router.get("/diagnostics")
async def diagnostics_endpoint(request: Request) -> DiagnosticReport:
    obs = _get_obs(request)
    if obs:
        return await obs.diagnostics.generate_report(
            db_check_fn=_make_db_check(request),
        )
    return DiagnosticReport(environment="unknown")


@router.get("/observability/status")
async def observability_status(request: Request) -> dict[str, object]:
    obs = _get_obs(request)
    if not obs:
        return {"observability": "not_available"}

    return {
        "observability": "active",
        "metrics": True,
        "tracing": True,
        "logging": True,
        "health_endpoints": [
            "/health/live", "/health/ready", "/health/status",
            "/health/check", "/diagnostics", "/observability/status",
        ],
        "diagnostics": True,
        "profiler_enabled": obs.profiler.enabled,
        "profiler_statistics": obs.profiler.get_statistics(),
        "active_alerts": len(obs.alerting.get_active_alerts()),
    }


def _make_db_check(request: Request) -> object:
    async def check() -> None:
        container: Container = request.app.state.container
        if container.engine:
            import asyncio
            session = container.create_session()
            try:
                async with asyncio.timeout(3):
                    await session.execute(text("SELECT 1"))
            finally:
                await session.close()
    return check
