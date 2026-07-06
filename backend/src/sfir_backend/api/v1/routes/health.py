"""Health check endpoints for liveness, readiness, and metrics."""

import time

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.api.deps import get_db
from sfir_backend.config.settings import get_settings

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["health"])

_startup_time = time.time()


@router.get("/health/live")
async def liveness() -> dict:
    """Liveness probe — process is alive."""
    return {
        "status": "ok",
        "service": "sfir-backend",
        "timestamp": time.time(),
        "uptime_seconds": time.time() - _startup_time,
    }


@router.get("/health/ready")
async def readiness(db: AsyncSession = Depends(get_db)) -> dict:
    """Readiness probe — service can accept traffic."""
    checks = {
        "database": False,
        "redis": False,
    }
    status_code = 200

    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception as e:
        logger.error("readiness_db_failed", error=str(e))
        status_code = 503

    try:
        from sfir_backend.infrastructure.cache.redis import get_redis
        redis = get_redis()
        await redis.ping()
        checks["redis"] = True
    except Exception as e:
        logger.error("readiness_redis_failed", error=str(e))
        status_code = 503

    return {
        "status": "ok" if all(checks.values()) else "degraded",
        "checks": checks,
        "uptime_seconds": time.time() - _startup_time,
        "environment": get_settings().environment,
    }
