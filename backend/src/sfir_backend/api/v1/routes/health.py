from __future__ import annotations

import datetime
import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from sfir_backend.config.container import Container
from sfir_backend.infrastructure.observability.health import (
    HealthCheckManager,
)

router = APIRouter(tags=["Health"])


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    """Liveness probe for Kubernetes.

    Returns 200 if the process is alive.
    """
    return {"status": "healthy", "timestamp": datetime.datetime.now(datetime.UTC).isoformat()}


@router.get("/health/ready")
async def readiness(request: Request) -> JSONResponse:
    """Readiness probe.

    Checks that the application can serve traffic by
    verifying database, Redis, and cache connectivity.
    """
    checks: dict[str, str] = {}
    all_ready = True

    try:
        container: Container = request.app.state.container
    except (AttributeError, KeyError):
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "checks": {"application": "not_initialized"},
            },
        )

    if container.engine:
        try:
            import asyncio

            session = container.create_session()
            try:
                async with asyncio.timeout(3):
                    await session.execute(text("SELECT 1"))
                checks["database"] = "ok"
            except TimeoutError:
                checks["database"] = "timeout"
                all_ready = False
            except Exception:
                checks["database"] = "failed"
                all_ready = False
            finally:
                await session.close()
        except Exception:
            checks["database"] = "unavailable"
            all_ready = False
    else:
        checks["database"] = "not_configured"

    health_manager: HealthCheckManager | None = None
    try:
        health_manager = container.get_service("health_check_manager")
    except (AttributeError, KeyError):
        pass

    if health_manager:
        try:
            redis_check = await health_manager.check_redis()
            checks["redis"] = redis_check.status.value if hasattr(redis_check.status, "value") else str(redis_check.status)
            if redis_check.status.value in ("unhealthy", "degraded"):
                all_ready = False
        except Exception:
            checks["redis"] = "unavailable"
            all_ready = False

        try:
            cache_check = await health_manager.check_cache()
            checks["cache"] = cache_check.status.value if hasattr(cache_check.status, "value") else str(cache_check.status)
            if cache_check.status.value in ("unhealthy", "degraded"):
                all_ready = False
        except Exception:
            checks["cache"] = "unavailable"
            all_ready = False

    status_code = 200 if all_ready else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if all_ready else "not_ready",
            "checks": checks,
        },
    )


@router.get("/health/status")
async def detailed_status(request: Request) -> dict[str, object]:
    """Detailed health status with system information."""
    container: Container | None = None
    try:
        container = request.app.state.container
    except (AttributeError, KeyError):
        pass

    result: dict[str, object] = {
        "service": "sfir-backend",
        "version": "0.1.0",
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
    }

    if container:
        health_manager: HealthCheckManager | None = None
        try:
            health_manager = container.get_service("health_check_manager")
        except (AttributeError, KeyError):
            pass

        if health_manager:
            try:
                report = await health_manager.run_all_checks()
                result["health"] = {
                    "overall": report.overall_status.value if hasattr(report.overall_status, "value") else str(report.overall_status),
                    "checks": [
                        {
                            "component": c.component,
                            "status": c.status.value if hasattr(c.status, "value") else str(c.status),
                            "latency_ms": c.latency_ms,
                            "message": c.message,
                        }
                        for c in report.checks
                    ],
                }
            except Exception as e:
                result["health"] = {"error": str(e)}

    return result


@router.get("/health/checks")
async def run_health_checks(request: Request) -> JSONResponse:
    """Run all health checks and return detailed results."""
    container: Container | None = None
    try:
        container = request.app.state.container
    except (AttributeError, KeyError):
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "message": "Container not initialized"},
        )

    health_manager: HealthCheckManager | None = None
    try:
        health_manager = container.get_service("health_check_manager")
    except (AttributeError, KeyError):
        pass

    if not health_manager:
        return JSONResponse(
            content={
                "status": "degraded",
                "message": "Health check manager not configured",
                "checks": [],
            }
        )

    db_check_fn = None
    if container.engine:
        async def db_check() -> None:
            session = container.create_session()
            try:
                await session.execute(text("SELECT 1"))
            finally:
                await session.close()

        db_check_fn = db_check

    report = await health_manager.run_all_checks(db_check_fn=db_check_fn)

    return JSONResponse(
        status_code=200 if report.overall_status.value in ("healthy", "degraded") else 503,
        content={
            "status": report.overall_status.value if hasattr(report.overall_status, "value") else str(report.overall_status),
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            "checks": [
                {
                    "component": c.component,
                    "status": c.status.value if hasattr(c.status, "value") else str(c.status),
                    "latency_ms": c.latency_ms,
                    "message": c.message,
                    "details": c.details,
                }
                for c in report.checks
            ],
        },
    )
