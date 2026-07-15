import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from sfir_backend.config.container import Container

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
    verifying database connectivity.
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

    status_code = 200 if all_ready else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if all_ready else "not_ready",
            "checks": checks,
        },
    )


@router.get("/health/status")
async def detailed_status() -> dict[str, object]:
    """Detailed health status with system information."""
    return {
        "service": "sfir-backend",
        "version": "0.1.0",
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
    }
