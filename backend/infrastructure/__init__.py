"""DataPilot infrastructure layer — concrete adapters for all real-time external systems.

Every adapter in this package is designed for the WebSocket-first, streaming
application model. Latency targets are documented per sub-package because in
a real-time pipeline where users watch progress token-by-token, a slow adapter
anywhere on the hot path makes the whole experience feel broken.

Dependency rule
---------------
Implements backend.application.ports interfaces.
Injected at backend.api.dependencies (the composition root).
Never imported by backend.domain or backend.application.

Hot-path latency budget (per WebSocket message round-trip, target < 300ms)
──────────────────────────────────────────────────────────────────────────
  SecurityAgent injection check     <   2ms  (pure regex, sync)
  RedisCacheAdapter.get_json()      <   1ms  (O(1) GET from Redis)
  BedrockEmbeddingService.embed()   ~  80ms  (Titan Embed v2, InvokeModel)
  QdrantAdapter.search()            ~  10ms  (ANN vector search)
  IntentAgent (Claude Haiku)        ~ 200ms  (Converse API, 400 tokens)
  RAG retriever total               ~  90ms  (embed + search + rerank)
  BedrockStreamAdapter first token  ~ 300ms  (Sonnet, first token arrival)
  Total chat turn (streaming)       ~ 400ms  (first token visible in browser)

Sub-packages
============

persistence/                                               Postgres + SQLAlchemy
────────────────────────────────────────────────────────────────────────────────
database.py
    Async engine singleton (create_async_engine + lru_cache).
    pool_pre_ping=True   — reconnects after DB restarts without crashing workers.
    pool_recycle=3600    — refreshes connections every hour (avoids cloud firewall drops).
    expire_on_commit=False — objects remain usable after commit (avoids lazy-load errors
                             in async code where there is no implicit session).
    get_session()        — asynccontextmanager; commits on success, rollback on error.
    get_db_session()     — FastAPI Depends() generator; same commit/rollback behaviour.
    health_check()       — SELECT 1; used by /ready endpoint.
    dispose_engine()     — called in FastAPI lifespan shutdown to drain the pool cleanly.

models/
    DatasetModel          — datasets table; schema_json JSONB; soft-delete via deleted_at;
                            partial index ix_datasets_active WHERE deleted_at IS NULL.
    SessionModel          — analysis_sessions; profile_json + cleaning_report_json JSONB;
                            anomaly_ids JSONB array.
    InsightReportModel    — insight_reports; report_json JSONB with GIN index for @> queries.
    ConversationModel     — conversations; messages JSONB array with GIN index for content
                            search; partial composite index (dataset_id, is_closed)
                            WHERE deleted_at IS NULL.
    MessageModel          — messages (optional normalised table; off by default).
    AgentExecutionModel   — agent_executions; append-only audit; partial index for LLM
                            cache lookups WHERE success=TRUE AND input_hash IS NOT NULL.

repositories/
    PostgresDatasetRepository     — get_by_id, save (upsert), delete (soft),
                                    get_by_project, get_by_status, get_by_checksum,
                                    count_by_project.
    PostgresSessionRepository     — get_by_id, save, get_by_dataset_id,
                                    get_latest_by_dataset_id, get_by_status.
    PostgresInsightRepository     — get_by_id, save, get_by_dataset_id,
                                    get_by_session_id, list_by_dataset.
    PostgresConversationRepository— get_by_id, save, delete (soft),
                                    get_by_dataset_id, get_active_by_dataset_id,
                                    search_by_content (ILIKE on JSONB cast to TEXT).

migrations/                        Alembic async (asyncpg + NullPool for migrations)
    001_create_datasets.py         — datasets + agent_executions tables + indexes.
    002_create_sessions.py         — analysis_sessions + insight_reports + GIN index.
    003_create_conversations.py    — conversations + messages + GIN index.
    env.py                         — reads DATABASE_URL from env; asyncio.run() for online mode.

─────────────────────────────────────────────────────────────────────────────────────────

cache/                                                Redis + in-memory fallback
────────────────────────────────────────────────────────────────────────────────
Real-time role:
    Redis is the backbone of the real-time event system.
    Three distinct usage patterns:

    1. JOB STATUS HASH  — Celery tasks write HSET job:<id> {status, progress, step}
                          every few seconds. The /jobs/:id endpoint reads it in < 1ms.
                          Browser can poll at 1Hz with negligible server load.

    2. INSIGHT CACHE    — Completed InsightReport stored as JSON under
                          insights:<dataset_id> with 24-hour TTL.
                          GET /insights/:id hits Redis first; Postgres only on cold miss.
                          Cache is invalidated by on_insight_report_generated() handler.

    3. PUB/SUB BRIDGE   — Workers call publish_json("dataset:<id>", payload).
                          ws_server.py psubscribes("dataset:*") and re-emits to Socket.IO.
                          Latency: < 1ms Redis PUBLISH → browser WebSocket frame.

RedisCacheAdapter
    get(key), set(key, value, ttl), delete(key), exists(key)
    get_json(key) → dict | None          — JSON.loads; returns None on miss or parse error.
    set_json(key, value, ttl)            — JSON.dumps; ignores errors (non-critical writes).
    publish_json(channel, payload) → int — PUBLISH; returns subscriber count.
    incr(key, ttl) → int                 — atomic INCR + EXPIRE; used by RateLimitMiddleware.
    cache_job_status(job_id, status, progress, step, extra)
    get_job_status(job_id) → dict
    invalidate_insights(dataset_id)
    delete_pattern(pattern) → int        — SCAN + DEL for LLM cache flush.
    ping() → bool

InMemoryCacheAdapter
    dict-backed; same interface as RedisCacheAdapter.
    Used in APP_ENV=test — no Redis process needed.
    clear() called in fixture teardown between tests.

─────────────────────────────────────────────────────────────────────────────────────────

storage/                                              S3 / MinIO / local filesystem
────────────────────────────────────────────────────────────────────────────────────
S3StorageAdapter
    All S3 calls run in a dedicated ThreadPoolExecutor (boto3 is synchronous).
    upload_fileobj(file_obj, key, content_type)  — multipart for > 8MB files.
    download_bytes(key) → bytes                  — single GetObject read.
    delete(key)                                  — DeleteObject.
    exists(key) → bool                           — HeadObject; 404 = False.
    generate_presigned_download_url(key, ttl=900) → str
        Used by ReportAgent after PDF/XLSX/PPTX upload.
        Default TTL: 15 minutes. Stored in Redis for job poller to return.
    ping() → bool                                — HeadBucket on the configured bucket.

LocalStorageAdapter
    Filesystem adapter for development and integration tests.
    Same interface as S3StorageAdapter.
    base_path defaults to /tmp/datapilot_storage/.
    clear() removes all files under base_path (used in test fixtures).

─────────────────────────────────────────────────────────────────────────────────────────

messaging/                                            Kafka + Avro event bus
──────────────────────────────────────────────────────────────────────────────
Real-time role:
    Kafka decouples the API server from the Celery analytics workers.
    UseCase publishes a domain event → Kafka → KafkaConsumer → event_handler
    → RedisCacheAdapter.publish_json() → ws_server psubscribe bridge → Socket.IO.

KafkaEventBus
    aiokafka AIOKafkaProducer; created lazily on first publish().
    publish(event, partition_key)   — fire-and-forget; serialises to Avro.
    publish_batch(events)           — single ProduceRequest for bulk publishes.
    start() / stop()                — called in FastAPI lifespan.
    ping() → bool                   — metadata request to broker.

EVENT_TOPIC_MAP (12 events → 8 topics):
    DatasetUploaded      → datapilot.datasets.uploaded
    DatasetReady         → datapilot.datasets.lifecycle
    DatasetFailed        → datapilot.datasets.lifecycle
    ProfilingCompleted   → datapilot.analytics.completed
    CleaningCompleted    → datapilot.analytics.completed
    InsightReportGenerated→datapilot.insights.generated
    MessageSent          → datapilot.conversations.messages
    ConversationCreated  → datapilot.conversations.lifecycle

KafkaConsumer (base class)
    _handle(event) abstract method; subclasses implement business logic.
    Auto-reconnects with exponential backoff on broker disconnect.
    Commits offsets only after _handle() returns successfully.

Consumers (one asyncio.Task each, started in FastAPI lifespan):
    DatasetUploadedConsumer  → calls on_dataset_uploaded() event handler.
    AnalyticsCompletedConsumer→calls on_analytics_completed() event handler.
    InsightGeneratedConsumer → calls on_insight_report_generated() handler.

serializer.py
    Avro schema registry per event type.
    serialize(event) → bytes; deserialize(bytes) → DomainEvent.

─────────────────────────────────────────────────────────────────────────────────────────

llm/                                                  AWS Bedrock adapters
──────────────────────────────────────────────────────────────────────────
Real-time role:
    Two distinct LLM interaction modes:

    BATCH (BedrockConverseAdapter)
        Used by: PlannerAgent, InsightAgent, CriticAgent, SchemaAgent, SQLAgent.
        Returns the full response string after the model finishes.
        Retry: @with_bedrock_retry decorator — jittered exponential backoff
               for ThrottlingException, ServiceUnavailableException, etc.
               Non-retryable: AccessDeniedException, ValidationException.

    STREAMING (BedrockStreamAdapter)
        Used by: NarrativeGenerator (executive summary typewriter effect).
        stream(prompt) async generator → yields text tokens as they arrive.
        Bridges synchronous boto3 EventStream to asyncio via Queue(maxsize=512)
        + run_in_executor reader thread.
        Each token is emitted as insight:summary_token Socket.IO event.

bedrock/
    bedrock_client.py       @lru_cache singleton; reads IRSA credentials in EKS;
                            reset_client() for test mocking.
    bedrock_converse_adapter.py
        complete(prompt, system, model_id, max_tokens, temperature,
                 response_format) → str
        complete_with_metadata() → LLMResponse VO
        converse_multi_turn(messages, system) → str  (full chat history)
        Appends JSON-only suffix to system prompt when response_format=dict.

    bedrock_stream_adapter.py
        stream(prompt, system, model_id) → AsyncGenerator[str, None]
        stream_to_string() → str  (accumulates tokens; no Socket.IO)

    bedrock_embedding_adapter.py
        embed(text, dimensions=1536) → list[float]
        embed_batch_serial(texts) → list[list[float]]
        Runs InvokeModel in dedicated ThreadPoolExecutor(max_workers=4).

    bedrock_retry_handler.py
        @with_bedrock_retry / @with_bedrock_retry(max_retries=N)
        RETRYABLE: ThrottlingException, ServiceUnavailableException,
                   ModelNotReadyException, InternalServerException.
        NON_RETRYABLE: AccessDeniedException, ValidationException,
                       ModelErrorException, ResourceNotFoundException.

    bedrock_cost_tracker.py
        record_invocation(model_id, input_tokens, output_tokens) → float
        session_cost_usd, cost_by_model(), summary()
        emit_cloudwatch_metrics() — PutMetricData to DataPilot/Bedrock namespace.

    model_configs/
        claude_sonnet.py   MODEL_ID, pricing ($3/$15 per 1M), CONTEXT_WINDOW=200k,
                           PRIMARY_AGENT_ROLES frozenset, estimate_cost(),
                           converse_inference_config().
        claude_haiku.py    MODEL_ID, pricing ($0.25/$1.25), FAST_AGENT_ROLES frozenset.
        titan_embed.py     MODEL_ID, DIMENSION_HIGH=1536, build_request_body(),
                           NORMALIZE=True.

llm_port.py
    ILLMService ABC: complete, converse, stream, embed.
    BedrockLLMService  — production (composes the three adapters above).
    MockLLMService     — test double; set_response(substring, canned_response);
                         records all calls in .calls for assertion.
    NullLLMService     — always returns ""; used when AI features are disabled.

token_tracker.py       Thread-safe accumulator; ModelUsage per model_id;
                       snapshot_and_reset(); emit_prometheus_metrics().
model_id_registry.py   get_model_id(role) → FAST_ROLES → Haiku, else Sonnet.
llm_response_cache.py  Redis SHA-256(model_id:prompt) cache; 24-hour TTL;
                       hit_rate property; invalidate_all() for cache flush.

─────────────────────────────────────────────────────────────────────────────────────────

vector_store/                                         Qdrant + Bedrock Embeddings
────────────────────────────────────────────────────────────────────────────────────
Real-time role:
    RAG retrieval is on the hot path of every chat message.
    Target: embed query + search Qdrant + rerank < 100ms combined.

    Indexing runs asynchronously after schema inference completes,
    concurrent with profiling. By the time the user sends the first chat
    message the knowledge base is already indexed and ready.

bedrock_embedding_service.py
    embed(text) → list[float]                — single embed with Redis cache.
    embed_batch(texts, max_concurrent=4)     — asyncio.gather with semaphore;
                                               respects Bedrock rate limits.
    Cache key: SHA-256(text); TTL: 7 days.
    Cache hit rate typically > 80% for repeated schema column names.

qdrant_adapter.py
    upsert(points: list[dict])               — batch upsert; creates collection
                                               if missing.
    search(vector, dataset_id, top_k) → list[dict]
        Uses must filter on dataset_id payload field to scope results
        to one dataset without separate collections per dataset.
    ensure_collection()                      — idempotent; called on startup.
    delete_by_dataset(dataset_id)            — point filter delete for GDPR.

collection_manager.py
    initialise()                             — creates Qdrant collection on startup.
    recreate()                               — drops and re-creates (dev/test).
    index_dataset(dataset_id, profile)       — builds schema + profile chunks
                                               via ChunkBuilder, embeds all
                                               concurrently, upserts to Qdrant.
                                               Emits rag:indexed Socket.IO event.

─────────────────────────────────────────────────────────────────────────────────────────

job_queue/                                            Celery + Redis broker
──────────────────────────────────────────────────────────────────────────
Three Celery queues with separate worker pools:

    analysis  (4 workers, CPU-bound)   — runs DataProfiler, DataCleaner,
                                         AnomalyDetector in thread pools.
    agents    (2 workers, I/O-bound)   — runs LangGraph pipeline; makes
                                         Bedrock API calls concurrently.
    reports   (1 worker, disk-bound)   — renders PDF/XLSX/PPTX; uploads to S3.

celery_app.py          AIO-compatible Celery app; Redis broker + result backend;
                       task_serializer=json; acks_late=True for at-least-once.

tasks/
    analysis_tasks.py  run_analysis_pipeline(dataset_id, storage_key, correlation_id)
                           → updates job status in Redis at each stage
                           → publishes ProfilingCompleted, CleaningCompleted events.
    agent_tasks.py     run_agent_pipeline(dataset_id, session_id, correlation_id)
                           → invokes LangGraph analysis pipeline graph
                           → publishes InsightReportGenerated on completion.
    report_tasks.py    generate_report(dataset_id, session_id, format, report_id)
                           → loads InsightReport from Redis/Postgres
                           → renders via pdf_generator/excel_exporter/pptx_generator
                           → uploads to S3 → stores presigned URL in Redis
                           → publishes report:ready via Redis pub/sub.

CeleryJobAdapter
    enqueue_analysis(dataset_id, storage_key, correlation_id) → task_id: str
    enqueue_agents(dataset_id, session_id, correlation_id) → task_id: str
    enqueue_report(dataset_id, session_id, format) → task_id: str
    get_task_status(task_id) → dict  (Celery result backend)
    revoke_task(task_id, terminate)

NullJobAdapter          Returns fake UUID task IDs; used in unit tests and
                        integration tests where no Celery broker is running.

─────────────────────────────────────────────────────────────────────────────────────────

observability/                                        OTel + Prometheus + structlog
────────────────────────────────────────────────────────────────────────────────────
structured_logger.py
    configure_logging(log_level) — structlog JSON renderer; binds correlation_id,
    session_id, dataset_id as context vars so every log line in a request
    carries the full trace context.

otel_setup.py
    setup_otel(service_name, endpoint) — OTLP exporter to Grafana Tempo / Jaeger.
    instrument_fastapi(app)            — auto-instruments all HTTP routes.
    Trace IDs included in X-Correlation-ID header for browser→backend correlation.

prometheus_metrics.py
    All metrics defined here; imported by MetricsEmitter:
    datapilot_agent_duration_ms    Histogram  [agent, status]
    datapilot_agent_runs_total     Counter    [agent, status]
    datapilot_llm_tokens_total     Counter    [agent, model, token_type]
    datapilot_llm_cost_usd_total   Counter    [agent, model]
    datapilot_pipeline_duration_ms Histogram
    datapilot_pipeline_runs_total  Counter    [status]
    datapilot_pipeline_cost_usd_total Counter
    datapilot_ws_messages_total    Counter    [event]
    datapilot_rag_retrieval_ms     Histogram
    datapilot_rag_chunks_retrieved Histogram
    datapilot_rag_top_score        Histogram
    websocket_connections_active   Gauge      (inc on connect, dec on disconnect)

audit_logger.py
    Append-only compliance log written to agent_executions Postgres table
    via AgentExecutionModel. Captures: agent_name, session_id, success,
    duration_ms, token_count, cost_usd, model_id, error.
    Written asynchronously by MonitoringAgent (non-blocking pipeline).

─────────────────────────────────────────────────────────────────────────────────────────

analytics_db/                                         ClickHouse (optional)
──────────────────────────────────────────────────────────────────────────────
Enabled when FEATURE_CLICKHOUSE=true.
Stores column-level statistics (mean, stddev, percentiles, null rate per column
per dataset per day) for fast dashboard queries without re-scanning raw data.

ClickHouseClient
    execute(query, params) — clickhouse-driver sync client in executor.
    ensure_schema()        — CREATE TABLE IF NOT EXISTS column_stats.
    ping() → bool

ColumnStatsWriter
    write_profile(dataset_id, profile) — inserts one row per column from DataProfile.
    Called non-blocking (asyncio.ensure_future) after profiling completes.
"""
from __future__ import annotations


def get_redis_cache():
    """Return the process-level RedisCacheAdapter singleton.

    Falls back to InMemoryCacheAdapter when REDIS_URL=memory:// (test env).
    Lazy import avoids connecting to Redis at module import time.

    Usage::

        from backend.infrastructure import get_redis_cache
        cache = get_redis_cache()
        await cache.set_json("insights:abc", report_dict, ttl=86400)
    """
    from backend.config.settings import get_settings
    settings = get_settings()
    if settings.redis_url == "memory://":
        from backend.infrastructure.cache.in_memory_cache_adapter import InMemoryCacheAdapter
        return _get_or_create("_in_memory_cache", InMemoryCacheAdapter)
    from backend.infrastructure.cache.redis_cache_adapter import RedisCacheAdapter
    return _get_or_create("_redis_cache", RedisCacheAdapter)


def get_storage():
    """Return the process-level storage adapter (S3 or local).

    Switches to LocalStorageAdapter when s3_endpoint_url == 'local://'
    so development and integration tests run without a real S3 bucket.

    Usage::

        from backend.infrastructure import get_storage
        storage = get_storage()
        url = await storage.generate_presigned_download_url("reports/abc/report.pdf")
    """
    from backend.config.settings import get_settings
    settings = get_settings()
    if getattr(settings, "s3_endpoint_url", "") == "local://":
        from backend.infrastructure.storage.local_storage_adapter import LocalStorageAdapter
        return _get_or_create("_local_storage", LocalStorageAdapter)
    from backend.infrastructure.storage.s3_storage_adapter import S3StorageAdapter
    return _get_or_create("_s3_storage", S3StorageAdapter)


# ---------------------------------------------------------------------------
# Private singleton store
# ---------------------------------------------------------------------------

_singletons: dict = {}


def _get_or_create(key: str, factory):
    if key not in _singletons:
        _singletons[key] = factory()
    return _singletons[key]


def _reset_singletons() -> None:
    """Clear all cached singletons — call in test teardown only."""
    _singletons.clear()


__all__ = [
    "get_redis_cache",
    "get_storage",
    "_reset_singletons",
]