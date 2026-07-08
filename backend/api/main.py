"""DataPilot FastAPI application entry point.

Initialisation order (FastAPI lifespan):
  1. Logging (structlog)
  2. OpenTelemetry tracing
  3. Database engine + schema validation
  4. ClickHouse schema (if FEATURE_CLICKHOUSE)
  5. Qdrant collection (if FEATURE_RAG)
  6. Redis connection warmup
  7. Kafka consumer tasks (if FEATURE_KAFKA)
  8. Redis → Socket.IO bridge

Shutdown order (reverse):
  1. Kafka consumers cancelled
  2. Redis bridge cancelled
  3. Database engine disposed
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import structlog
from backend.api.middleware.correlation_id import CorrelationIdMiddleware
from backend.api.middleware.error_handler import register_exception_handlers
from backend.api.middleware.rate_limiting import RateLimitMiddleware
from backend.api.middleware.request_logging import RequestLoggingMiddleware
from backend.api.middleware.security_headers import SecurityHeadersMiddleware
from backend.api.routers.conversations import router as conversations_router
from backend.api.routers.datasets import router as datasets_router
from backend.api.routers.exports import router as exports_router
from backend.api.routers.health import router as health_router
from backend.api.routers.insights import router as insights_router
from backend.api.routers.jobs import router as jobs_router
from backend.api.websocket.ws_server import socket_app
from backend.config.feature_flags import flags
from backend.config.logging_config import configure_logging
from backend.config.settings import get_settings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = structlog.get_logger(__name__)

settings = get_settings()


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup and shutdown lifecycle."""

    # ── 1. Logging ────────────────────────────────────────────────────────
    configure_logging(log_level=settings.log_level)
    logger.info("datapilot_starting", version=settings.app_version, env=settings.app_env)

    # ── 2. OpenTelemetry ──────────────────────────────────────────────────
    if settings.otel_enabled:
        from backend.infrastructure.observability.otel_setup import instrument_fastapi, setup_otel

        setup_otel(
            service_name=settings.otel_service_name, endpoint=settings.otel_exporter_otlp_endpoint
        )
        instrument_fastapi(app)

    # ── 3. Database ───────────────────────────────────────────────────────
    from backend.infrastructure.persistence.database import get_engine

    get_engine()  # initialise connection pool

    # ── 4. ClickHouse ─────────────────────────────────────────────────────
    if flags.clickhouse_enabled:
        try:
            from backend.infrastructure.analytics_db.clickhouse_client import get_clickhouse_client

            await get_clickhouse_client().ensure_schema()
        except Exception as exc:
            logger.warning("clickhouse_init_failed", error=str(exc))

    # ── 5. Qdrant ─────────────────────────────────────────────────────────
    if flags.rag_enabled:
        try:
            from backend.infrastructure.vector_store.collection_manager import CollectionManager

            await CollectionManager().initialise()
        except Exception as exc:
            logger.warning("qdrant_init_failed", error=str(exc))

    # ── 6. Redis warmup ───────────────────────────────────────────────────
    try:
        from backend.infrastructure.cache.redis_cache_adapter import get_redis_cache

        await get_redis_cache().ping()
        logger.info("redis_ready")
    except Exception as exc:
        logger.warning("redis_warmup_failed", error=str(exc))

    # ── 7. Kafka consumers ────────────────────────────────────────────────
    consumer_tasks: list[asyncio.Task] = []
    if flags.kafka_enabled:
        from backend.infrastructure.messaging.consumers.analytics_completed_consumer import (
            AnalyticsCompletedConsumer,
        )
        from backend.infrastructure.messaging.consumers.dataset_uploaded_consumer import (
            DatasetUploadedConsumer,
        )
        from backend.infrastructure.messaging.consumers.insight_generated_consumer import (
            InsightGeneratedConsumer,
        )

        for consumer_cls in [
            DatasetUploadedConsumer,
            AnalyticsCompletedConsumer,
            InsightGeneratedConsumer,
        ]:
            task = asyncio.create_task(consumer_cls().run())
            consumer_tasks.append(task)
        logger.info("kafka_consumers_started", count=len(consumer_tasks))

    # ── 8. Redis → Socket.IO bridge ───────────────────────────────────────
    from backend.api.websocket.ws_server import start_redis_subscriber

    await start_redis_subscriber()

    logger.info("datapilot_ready", version=settings.app_version)

    yield  # application runs here

    # ── Shutdown ──────────────────────────────────────────────────────────
    logger.info("datapilot_shutting_down")

    for task in consumer_tasks:
        task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await task

    from backend.infrastructure.persistence.database import dispose_engine

    await dispose_engine()
    logger.info("datapilot_stopped")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="DataPilot API",
    description=(
        "AI-powered data analytics platform. Upload datasets, chat with your data, "
        "and generate business insights."
    ),
    version=settings.app_version,
    docs_url="/docs" if settings.enable_swagger else None,
    redoc_url="/redoc" if settings.enable_swagger else None,
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Correlation-ID", "X-Response-Time-Ms"],
)

app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
register_exception_handlers(app)

# ── Routers ───────────────────────────────────────────────────────────────
app.include_router(health_router)
app.include_router(datasets_router)
app.include_router(insights_router)
app.include_router(conversations_router)
app.include_router(exports_router)
app.include_router(jobs_router)

# ── Prometheus metrics ────────────────────────────────────────────────────
if settings.prometheus_enabled:
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# ── Socket.IO WebSocket mount ─────────────────────────────────────────────
app.mount("/ws", socket_app)
