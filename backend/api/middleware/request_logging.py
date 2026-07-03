"""RequestLoggingMiddleware — structured access log for every HTTP request."""
from __future__ import annotations

import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import structlog

logger = structlog.get_logger("datapilot.access")

SKIP_PATHS = {"/health", "/ready", "/metrics"}


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in SKIP_PATHS:
            return await call_next(request)

        start   = time.monotonic()
        response = await call_next(request)
        duration = round((time.monotonic() - start) * 1000, 2)

        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration,
            client=request.client.host if request.client else "-",
        )
        response.headers["X-Response-Time-Ms"] = str(duration)
        return response
