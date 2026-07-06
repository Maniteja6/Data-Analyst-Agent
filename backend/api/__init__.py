"""DataPilot API layer — real-time FastAPI + Socket.IO application.

Built for real-time: every HTTP endpoint has a paired Socket.IO event so
clients never need to poll. Analysis progress, chat tokens, schema inference,
anomaly findings, and report generation all stream to the browser as they happen.

Architecture overview
---------------------
HTTP (FastAPI)          WebSocket (Socket.IO @ /ws)
──────────────          ───────────────────────────
POST /datasets/upload   → triggers analysis pipeline
                          browser subscribes dataset:<id> room
                          receives: job:progress, agent:complete,
                                    profiling:column_complete,
                                    schema:column_classified,
                                    anomaly:detected,
                                    insight:summary_token,
                                    insight:insight_ready,
                                    recommendation:ready,
                                    analysis.complete

POST /conversations     → create conversation
POST /conversations/:id/messages (REST fallback)
                          OR chat_message Socket.IO event
                          receives: chat:token (streaming),
                                    chat:complete,
                                    security:cleared | security:blocked,
                                    validation:approved | validation:flagged

POST /exports/:id       → enqueue report render
                          browser subscribes job:<job_id> room
                          receives: report:render_start,
                                    report:page_complete | report:sheet_complete,
                                    report:uploading,
                                    report:ready (with download_url)

Sub-packages
------------
middleware/
    CorrelationIdMiddleware   — reads X-Correlation-ID or generates UUID;
                                binds to structlog context for full trace
    RequestLoggingMiddleware  — structured access log; skips /health /ready /metrics
    SecurityHeadersMiddleware — OWASP headers (HSTS, X-Frame-Options, etc.)
    RateLimitMiddleware       — Redis INCR sliding window;
                                60 req/min API, 20 uploads/hour per IP
    register_exception_handlers() — maps DomainException codes → HTTP status,
                                    RequestValidationError → 422 with field list

routers/
    health.py         GET /health (200 ok), GET /ready (DB + Redis checks)
    datasets.py       POST /upload, GET /:id, GET /, DELETE /:id
    insights.py       GET /insights/:dataset_id  (Redis-first, 404 if processing)
    conversations.py  POST /, GET /:id, POST /:id/messages, GET /by-dataset/:id
    exports.py        POST /exports/:dataset_id  (202 Accepted, returns job_id)
    jobs.py           GET /jobs/:job_id          (Redis hash → Celery fallback)

schemas/
    common_schemas.py       ErrorResponse, MessageResponse, PaginatedResponse
    dataset_schemas.py      DatasetUploadResponse, DatasetStatusResponse
    insight_schemas.py      InsightReportResponse, InsightNotReadyResponse
    conversation_schemas.py CreateConversationRequest/Response,
                            SendMessageRequest, MessageResponse, ConversationResponse
    export_schemas.py       ExportReportRequest, ExportReportResponse,
                            ExportReadyResponse

websocket/
    ws_server.py        socketio.AsyncServer; mounted at /ws;
                        Redis psubscribe("dataset:*") bridge in background task
    ws_event_router.py  @register decorator + dispatch(sio, sid, event, data)
    ws_handlers/
        connect_handler.py    inc websocket_connections_active gauge; emit connected
        disconnect_handler.py dec gauge
        chat_handler.py       builds SendMessageUseCase per message;
                              emits chat:complete or chat:error
        job_handler.py        enter_room job:<id>; push current Redis status

dependencies.py — composition root
    get_cache()              → RedisCacheAdapter singleton
    get_storage()            → S3StorageAdapter or LocalStorageAdapter
    get_event_bus()          → KafkaEventBus
    get_job_service()        → CeleryJobAdapter
    get_llm_service()        → BedrockLLMService or MockLLMService (APP_ENV=test)
    get_dataset_repo(db)     → PostgresDatasetRepository (request-scoped)
    get_insight_repo(db)     → PostgresInsightRepository
    get_conversation_repo(db)→ PostgresConversationRepository
    get_upload_use_case(...)  → UploadDatasetUseCase (injected)
    get_send_message_use_case → SendMessageUseCase (injected)
    ... (one factory per use case)

main.py — FastAPI lifespan + app assembly
    Startup sequence (8 steps):
        1. structlog JSON configuration
        2. OpenTelemetry tracer + FastAPI instrumentation
        3. SQLAlchemy async engine pool creation
        4. ClickHouse schema (if FEATURE_CLICKHOUSE=true)
        5. Qdrant collection ensure (if FEATURE_RAG=true)
        6. Redis ping warmup
        7. Kafka consumer tasks (if FEATURE_KAFKA=true)
        8. Redis → Socket.IO bridge task

    Middleware stack (outermost → innermost):
        CORSMiddleware → CorrelationIdMiddleware → RequestLoggingMiddleware
        → SecurityHeadersMiddleware → RateLimitMiddleware

    Mounts:
        /metrics  — Prometheus (if FEATURE_PROMETHEUS=true)
        /ws       — Socket.IO ASGI app

Real-time event guarantees
--------------------------
Every operation that takes > 200ms emits at least one Socket.IO event
before it starts and one when it completes:

    Operation               Start event              Complete event
    ──────────────────────────────────────────────────────────────
    File upload             (immediate HTTP 201)      job:progress 5%
    Schema inference        schema:progress           schema:complete
    Profiling               profiling:start           profiling:complete
      Per column            profiling:column_complete (N events)
    Cleaning                cleaning:start            cleaning:complete
    SQL agent               (job:progress 55%)        (job:progress 62%)
    Forecast agent          (job:progress 60%)        (job:progress 67%)
    Insight generation      insight:generation_start  insight:complete
      Executive summary     insight:summary_token (N) insight:summary_complete
      Per insight           insight:insight_ready (5 events)
    Critic validation       critic:reviewing          critic:approved|revision_needed
    Recommendations         recommendation:start      recommendation:complete
      Per recommendation    recommendation:ready (3 events)
    Report render           report:render_start       report:ready (download_url)
    Chat message            (immediate echo)          chat:complete
      Token streaming       chat:token (N events)
    Security check          (< 2ms, no event needed)  security:cleared|blocked

Socket.IO room conventions (enforced by all handlers and agents)
---------------------------------------------------------------
    dataset:<dataset_id>           pipeline progress; all agents; analysis.complete
    conversation:<conversation_id> chat tokens; security/validation (private per user)
    monitoring:<dataset_id>        admin perf dashboard (monitoring:pipeline_report)
    job:<job_id>                   job:status for polling clients
"""
from __future__ import annotations


def get_socket_app():
    """Return the Socket.IO ASGI app (lazy import avoids circular deps at module load).

    Usage in main.py::

        from backend.api import get_socket_app
        app.mount("/ws", get_socket_app())
    """
    from backend.api.websocket.ws_server import socket_app
    return socket_app


def get_fastapi_app():
    """Return the configured FastAPI application instance.

    Usage (uvicorn, gunicorn, or tests)::

        from backend.api import get_fastapi_app
        app = get_fastapi_app()

    The app is fully configured with middleware, routers, exception handlers,
    Prometheus instrumentation, and the Socket.IO mount.
    """
    from backend.api.main import app
    return app


__all__ = [
    "get_socket_app",
    "get_fastapi_app",
]
