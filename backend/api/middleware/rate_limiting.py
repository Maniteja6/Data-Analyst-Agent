"""RateLimitMiddleware — sliding-window rate limiting via Redis INCR."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

if TYPE_CHECKING:
    from backend.infrastructure.cache.redis_cache_adapter import RedisCacheAdapter

logger = structlog.get_logger(__name__)

SKIP_PATHS = {"/health", "/ready", "/metrics", "/docs", "/redoc", "/openapi.json"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Limits requests per client IP using a 60-second sliding window in Redis.

    Upload endpoints use a per-hour limit; all other endpoints use per-minute.
    Falls back gracefully (allows the request) when Redis is unreachable.
    """

    def __init__(self, app: ASGIApp, cache: RedisCacheAdapter | None = None) -> None:
        super().__init__(app)
        self._cache = cache

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in SKIP_PATHS:
            return await call_next(request)

        cache = self._get_cache()
        if cache is None:
            return await call_next(request)

        from backend.config.settings import get_settings

        settings = get_settings()
        client_ip = request.client.host if request.client else "unknown"
        is_upload = request.url.path.endswith("/upload") and request.method == "POST"

        if is_upload:
            key = f"rate_limit:upload:{client_ip}"
            limit = settings.rate_limit_upload_per_hour
            ttl = 3600
        else:
            key = f"rate_limit:api:{client_ip}"
            limit = settings.rate_limit_requests_per_minute
            ttl = 60

        try:
            count = await cache.incr(key, ttl=ttl)
            if count > limit:
                logger.warning("rate_limit_exceeded", ip=client_ip, count=count, limit=limit)
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "rate_limit_exceeded",
                        "message": (
                            f"Too many requests. Limit: {limit} per "
                            f"{'hour' if is_upload else 'minute'}."
                        ),
                        "code": "RATE_LIMIT_EXCEEDED",
                    },
                    headers={"Retry-After": str(ttl)},
                )
        except Exception as exc:
            logger.debug("rate_limit_redis_error", error=str(exc))

        return await call_next(request)

    def _get_cache(self) -> RedisCacheAdapter | None:
        if self._cache is None:
            try:
                from backend.infrastructure.cache.redis_cache_adapter import get_redis_cache

                self._cache = get_redis_cache()
            except Exception:
                return None
        return self._cache
