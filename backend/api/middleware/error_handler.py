"""ErrorHandlerMiddleware — converts domain and validation exceptions to JSON responses."""

from __future__ import annotations

import structlog
from backend.shared.exceptions import DomainError, ValidationError
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = structlog.get_logger(__name__)

# Map DomainError error codes → HTTP status codes
_CODE_TO_STATUS: dict[str, int] = {
    "DATASET_NOT_FOUND": 404,
    "SESSION_NOT_FOUND": 404,
    "INSIGHT_REPORT_NOT_FOUND": 404,
    "CONVERSATION_NOT_FOUND": 404,
    "PROJECT_NOT_FOUND": 404,
    "MESSAGE_NOT_FOUND": 404,
    "DUPLICATE_DATASET": 409,
    "INVALID_DATASET_STATUS_TRANSITION": 409,
    "CONVERSATION_CLOSED": 409,
    "INSUFFICIENT_DATA": 422,
    "CONTEXT_WINDOW_EXCEEDED": 422,
    "PROJECT_DATASET_LIMIT": 422,
    "UNSUPPORTED_FILE_TYPE": 415,
    "FILE_TOO_LARGE": 413,
    "INVALID_EXECUTION_PLAN": 422,
    "DAG_CYCLE_DETECTED": 422,
    "AGENT_NOT_REGISTERED": 500,
    "LLM_RESPONSE_PARSING_FAILED": 422,
    "INTENT_CLASSIFICATION_FAILED": 422,
    "CRITIC_VALIDATION_FAILED": 422,
    "FORECAST_MODEL_FAILED": 422,
    "INSIGHT_GENERATION_FAILED": 500,
    "PROFILING_FAILED": 500,
    "SCHEMA_INFERENCE_FAILED": 500,
}


def _domain_error_response(exc: DomainError) -> JSONResponse:
    status = _CODE_TO_STATUS.get(getattr(exc, "code", ""), 400)
    return JSONResponse(
        status_code=status,
        content={
            "error": getattr(exc, "code", "DOMAIN_ERROR"),
            "message": str(exc),
            "details": {},
        },
    )


async def domain_exception_handler(request: Request, exc: DomainError) -> JSONResponse:
    logger.warning(
        "domain_exception", code=getattr(exc, "code", "?"), path=request.url.path, error=str(exc)
    )
    return _domain_error_response(exc)


async def validation_exception_handler(request: Request, exc: ValidationError) -> JSONResponse:
    logger.info("validation_error", field=getattr(exc, "field", "?"), path=request.url.path)
    return JSONResponse(
        status_code=422,
        content={
            "error": "VALIDATION_ERROR",
            "message": str(exc),
            "field": getattr(exc, "field", None),
            "details": {},
        },
    )


async def request_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [
        {"field": " → ".join(str(part) for part in e["loc"]), "message": e["msg"]}
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "error": "REQUEST_VALIDATION_ERROR",
            "message": "Invalid request data.",
            "details": errors,
        },
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_exception", path=request.url.path, error=str(exc), exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "INTERNAL_SERVER_ERROR", "message": "An unexpected error occurred."},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the FastAPI app."""
    app.add_exception_handler(DomainError, domain_exception_handler)
    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.add_exception_handler(RequestValidationError, request_validation_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
