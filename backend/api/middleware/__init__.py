"""FastAPI middleware stack — outermost to innermost.

CorrelationIdMiddleware   — reads X-Correlation-ID or generates UUID4;
                            binds to structlog context for full request trace.
RequestLoggingMiddleware  — structured JSON access log; skips /health /ready /metrics.
SecurityHeadersMiddleware — OWASP headers: HSTS, X-Frame-Options, X-Content-Type.
RateLimitMiddleware       — Redis INCR sliding window; 60/min API, 20/hr upload.
register_exception_handlers() — DomainError → HTTP status; 422 with field list.
"""

from backend.api.middleware.correlation_id import CorrelationIdMiddleware
from backend.api.middleware.error_handler import register_exception_handlers
from backend.api.middleware.rate_limiting import RateLimitMiddleware
from backend.api.middleware.request_logging import RequestLoggingMiddleware
from backend.api.middleware.security_headers import SecurityHeadersMiddleware

__all__ = [
    "CorrelationIdMiddleware",
    "RequestLoggingMiddleware",
    "SecurityHeadersMiddleware",
    "RateLimitMiddleware",
    "register_exception_handlers",
]
