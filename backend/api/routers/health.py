"""Health and readiness check endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str
    checks: dict


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/ready", response_model=HealthResponse)
async def readiness() -> HealthResponse:
    from backend.config.settings import get_settings
    from backend.infrastructure.cache.redis_cache_adapter import get_redis_cache
    from backend.infrastructure.persistence.database import health_check as db_health

    settings = get_settings()
    checks = {}

    # Database
    try:
        checks["database"] = "ok" if await db_health() else "error"
    except Exception as exc:
        checks["database"] = f"error: {exc}"

    # Redis
    try:
        cache = get_redis_cache()
        checks["redis"] = "ok" if await cache.ping() else "error"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return HealthResponse(status=overall, version=settings.app_version, checks=checks)
