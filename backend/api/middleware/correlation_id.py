"""CorrelationIdMiddleware — attaches a tracing ID to every request."""
from __future__ import annotations

import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import structlog

CORRELATION_HEADER = "X-Correlation-ID"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Reads or generates a correlation ID and propagates it through the request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        correlation_id = request.headers.get(CORRELATION_HEADER) or str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
        )
        response = await call_next(request)
        response.headers[CORRELATION_HEADER] = correlation_id
        structlog.contextvars.clear_contextvars()
        return response
