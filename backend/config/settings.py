"""Application settings — loaded from environment variables via Pydantic Settings.

All configuration lives here. Nothing reads ``os.environ`` directly in
application code — it always goes through ``get_settings()``.

The ``@lru_cache`` decorator means settings are parsed once per process.
Tests that need different values should use ``get_settings.cache_clear()``
or monkeypatch the environment before importing.

Usage::

    from backend.config.settings import get_settings

    settings = get_settings()
    print(settings.database_url)
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Main application settings.

    Values are read (in priority order) from:
      1. Environment variables
      2. ``.env`` file in the working directory
      3. Default values defined below
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # silently ignore unknown env vars
    )

    # ── Application ───────────────────────────────────────────────────────
    app_env: str = Field(
        "development", description="Runtime environment: development | staging | production"
    )
    app_name: str = Field("DataPilot", description="Application display name")
    app_version: str = Field("1.0.0", description="Semver release version")
    debug: bool = Field(
        False, description="Enable debug mode (verbose SQL, stack traces in API responses)"
    )
    log_level: str = Field("INFO", description="Root log level: DEBUG | INFO | WARNING | ERROR")
    secret_key: str = Field(
        "change-me-to-a-random-64-char-string-in-production",
        description="Used for signing internal tokens",
    )

    # ── API server ────────────────────────────────────────────────────────
    api_host: str = Field("0.0.0.0", description="Bind address for uvicorn")  # noqa: S104  # nosec B104 — intentional: containers must bind all interfaces to expose the port
    api_port: int = Field(8000, ge=1, le=65535, description="Bind port for uvicorn")
    api_workers: int = Field(4, ge=1, description="Number of uvicorn worker processes")
    api_reload: bool = Field(False, description="Enable hot-reload (development only)")
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default=["http://localhost:3000", "http://localhost:5173"],
        description="Allowed CORS origins for the browser frontend",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, v: object) -> list[str]:
        """Accept a comma-separated string (the .env format) as well as a
        real list, instead of requiring JSON-array syntax in .env files."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v  # type: ignore[return-value]

    enable_swagger: bool = Field(
        True, description="Expose /docs and /redoc (disable in production)"
    )

    # ── PostgreSQL ────────────────────────────────────────────────────────
    database_url: str = Field(
        "postgresql+asyncpg://datapilot:datapilot_dev_password@localhost:5432/datapilot",
        description="Async SQLAlchemy connection URL (must use asyncpg driver)",
    )
    database_pool_size: int = Field(10, ge=1, description="SQLAlchemy connection pool size")
    database_max_overflow: int = Field(
        20, ge=0, description="SQLAlchemy max connections above pool_size"
    )

    # ── Redis ─────────────────────────────────────────────────────────────
    redis_url: str = Field(
        "redis://localhost:6379/0",
        description="Redis connection URL (rediss:// for TLS with auth token in production)",
    )
    redis_ttl_seconds: int = Field(86400, ge=1, description="Default cache TTL — 24 hours")
    redis_session_ttl_seconds: int = Field(604800, ge=1, description="Session key TTL — 7 days")

    # ── Celery ────────────────────────────────────────────────────────────
    celery_broker_url: str = Field(
        "redis://localhost:6379/1", description="Celery message broker URL"
    )
    celery_result_backend: str = Field(
        "redis://localhost:6379/2", description="Celery result backend URL"
    )
    celery_worker_concurrency: int = Field(4, ge=1, description="Celery worker process count")
    celery_task_soft_time_limit: int = Field(
        300, ge=1, description="Celery soft task timeout in seconds"
    )
    celery_task_time_limit: int = Field(
        600, ge=1, description="Celery hard task timeout in seconds"
    )

    # ── AWS general ───────────────────────────────────────────────────────
    aws_region: str = Field("us-east-1", description="Primary AWS region")
    aws_access_key_id: str = Field(
        "", description="Leave blank when using IRSA or instance profiles"
    )
    aws_secret_access_key: str = Field(
        "", description="Leave blank when using IRSA or instance profiles"
    )

    # ── S3 / MinIO ────────────────────────────────────────────────────────
    s3_bucket_name: str = Field(
        "datapilot-datasets-dev", description="Primary S3 bucket for uploaded datasets"
    )
    s3_region: str = Field("us-east-1", description="S3 bucket region")
    s3_endpoint_url: str | None = Field(
        None, description="Override endpoint for MinIO (local dev). Leave blank for real AWS S3."
    )
    s3_presigned_url_ttl_seconds: int = Field(
        900, ge=60, description="Presigned download URL expiry — 15 minutes"
    )
    s3_datasets_prefix: str = Field(
        "datasets/", description="S3 key prefix for uploaded dataset files"
    )
    s3_reports_prefix: str = Field(
        "reports/", description="S3 key prefix for generated report files"
    )
    s3_temp_prefix: str = Field(
        "tmp/",
        description=(
            "S3 key prefix for temporary processing files — lifecycle rule expires after 7 days"
        ),
    )

    # ── Kafka ─────────────────────────────────────────────────────────────
    kafka_bootstrap_servers: str = Field(
        "localhost:9092", description="Comma-separated Kafka broker list"
    )
    kafka_security_protocol: str = Field("PLAINTEXT", description="PLAINTEXT | SSL | SASL_SSL")
    kafka_sasl_mechanism: str = Field("", description="PLAIN | SCRAM-SHA-256 (blank for PLAINTEXT)")
    kafka_sasl_username: str = Field("", description="Kafka SASL username")
    kafka_sasl_password: str = Field("", description="Kafka SASL password")
    kafka_schema_registry_url: str = Field(
        "http://localhost:8081", description="Confluent / Glue Schema Registry URL"
    )
    kafka_consumer_group_id: str = Field(
        "datapilot-analytics-engine", description="Consumer group for the analytics pipeline"
    )
    kafka_auto_offset_reset: str = Field("earliest", description="earliest | latest")
    kafka_session_timeout_ms: int = Field(
        30000, description="Consumer session timeout in milliseconds"
    )

    # ── Kafka topics ──────────────────────────────────────────────────────
    kafka_topic_dataset_uploaded: str = Field("dataset.uploaded")
    kafka_topic_schema_inferred: str = Field("dataset.schema-inferred")
    kafka_topic_dataset_ready: str = Field("dataset.ready")
    kafka_topic_profiling_complete: str = Field("analytics.profiling-complete")
    kafka_topic_cleaning_complete: str = Field("analytics.cleaning-complete")
    kafka_topic_insight_generated: str = Field("insight.report-generated")
    kafka_topic_anomaly_detected: str = Field("anomaly.detected")
    kafka_topic_chat_message: str = Field("chat.message")
    kafka_topic_agent_result: str = Field("agent.result")
    kafka_topic_audit_events: str = Field("audit.events")

    # ── ClickHouse ────────────────────────────────────────────────────────
    clickhouse_host: str = Field("localhost", description="ClickHouse server hostname")
    clickhouse_port: int = Field(9000, description="ClickHouse native TCP port")
    clickhouse_http_port: int = Field(
        8123, description="ClickHouse HTTP port (used by some clients)"
    )
    clickhouse_db: str = Field("datapilot_analytics", description="ClickHouse database name")
    clickhouse_user: str = Field("default")
    clickhouse_password: str = Field("")
    clickhouse_secure: bool = Field(False, description="Enable TLS for ClickHouse connection")

    # ── Qdrant ────────────────────────────────────────────────────────────
    qdrant_host: str = Field("localhost", description="Qdrant server hostname")
    qdrant_port: int = Field(6333, description="Qdrant REST/gRPC port")
    qdrant_grpc_port: int = Field(6334)
    qdrant_api_key: str = Field(
        "", description="Qdrant API key (blank for local unauthenticated instance)"
    )
    qdrant_collection_name: str = Field(
        "datapilot_chunks", description="Collection storing dataset chunk embeddings"
    )
    qdrant_vector_size: int = Field(1536, description="Titan Embed v2 output dimension")

    # ── DuckDB ────────────────────────────────────────────────────────────
    duckdb_memory_limit: str = Field("2GB", description="DuckDB per-connection memory limit")
    duckdb_threads: int = Field(4, ge=1, description="DuckDB parallelism")

    # ── File upload limits ────────────────────────────────────────────────
    max_upload_size_bytes: int = Field(
        2 * 1024 * 1024 * 1024,  # 2 GB
        description="Maximum accepted upload size in bytes",
    )
    max_rows_in_memory: int = Field(
        5_000_000,
        description="Row count above which profiling switches to streaming / DuckDB to avoid OOM",
    )

    # ── Analytics engine ──────────────────────────────────────────────────
    anomaly_zscore_threshold: float = Field(
        3.0, description="Z-score threshold for outlier detection"
    )
    anomaly_iqr_multiplier: float = Field(1.5, description="IQR fence multiplier (Tukey method)")
    anomaly_isolation_forest_contamination: float = Field(0.05, ge=0.0, le=0.5)
    profiling_sample_size: int = Field(
        100_000, description="Max rows sampled for histogram computation"
    )
    profiling_top_n_values: int = Field(
        20, description="Top-N value frequencies stored per categorical column"
    )

    # ── Agent configuration ───────────────────────────────────────────────
    agent_max_retries: int = Field(
        3, ge=1, description="Maximum agent execution attempts before failure"
    )
    agent_retry_backoff_seconds: float = Field(
        2.0, description="Base exponential backoff delay between retries"
    )
    agent_llm_cache_ttl_seconds: int = Field(86400, description="LLM response cache TTL — 24 hours")
    sql_agent_row_limit: int = Field(
        10_000, description="Maximum rows returned by the SQL agent per query"
    )
    sql_agent_timeout_seconds: int = Field(30, description="DuckDB query execution timeout")
    python_agent_timeout_seconds: int = Field(60, description="Sandboxed Python execution timeout")
    python_agent_memory_limit_mb: int = Field(
        512, description="Memory ceiling for sandboxed Python subprocess"
    )
    rag_chunk_size: int = Field(512, description="Approximate token count per RAG chunk")
    rag_chunk_overlap: int = Field(64, description="Token overlap between consecutive chunks")
    rag_top_k: int = Field(8, description="Number of chunks retrieved per RAG query")
    rag_similarity_threshold: float = Field(
        0.72, description="Minimum cosine similarity score for a retrieved chunk to be used"
    )
    critic_max_revision_rounds: int = Field(
        2, ge=1, description="Maximum Critic→Insight revision cycles"
    )

    # ── Security ──────────────────────────────────────────────────────────
    pii_detection_enabled: bool = Field(
        True, description="Enable Presidio PII detection on user input and agent output"
    )
    pii_score_threshold: float = Field(
        0.7, ge=0.0, le=1.0, description="Minimum Presidio confidence score to flag as PII"
    )
    pii_redaction_placeholder: str = Field(
        "<REDACTED>", description="String substituted for detected PII in outputs"
    )
    injection_detection_enabled: bool = Field(
        True, description="Enable prompt injection detection on user messages"
    )
    injection_score_threshold: float = Field(
        0.6, ge=0.0, le=1.0, description="Minimum injection score to block a request"
    )
    rate_limit_requests_per_minute: int = Field(
        60, ge=1, description="API rate limit per client IP"
    )
    rate_limit_upload_per_hour: int = Field(
        20, ge=1, description="Dataset upload rate limit per client IP"
    )

    # ── JWT ───────────────────────────────────────────────────────────────
    jwt_algorithm: str = Field("RS256", description="JWT signing algorithm")
    jwt_access_token_ttl_minutes: int = Field(15, ge=1)
    jwt_refresh_token_ttl_days: int = Field(7, ge=1)
    jwt_public_key: str = Field(
        "", description="RS256 public key PEM (blank in local dev with no auth)"
    )
    jwt_private_key: str = Field(
        "", description="RS256 private key PEM (blank in local dev with no auth)"
    )

    # ── Observability ─────────────────────────────────────────────────────
    otel_enabled: bool = Field(True, description="Enable OpenTelemetry tracing")
    otel_service_name: str = Field("datapilot-api")
    otel_exporter_otlp_endpoint: str = Field(
        "http://localhost:4317", description="OTLP gRPC collector endpoint"
    )
    otel_exporter_otlp_protocol: str = Field("grpc", description="grpc | http/protobuf")
    prometheus_enabled: bool = Field(True, description="Expose /metrics endpoint")
    prometheus_port: int = Field(9090)
    sentry_dsn: str = Field("", description="Sentry DSN (blank to disable)")
    sentry_traces_sample_rate: float = Field(0.1, ge=0.0, le=1.0)
    audit_log_enabled: bool = Field(True)

    # ── MLflow ────────────────────────────────────────────────────────────
    mlflow_tracking_uri: str = Field("http://localhost:5000")
    mlflow_experiment_name: str = Field("datapilot-forecasting")
    mlflow_s3_artifact_root: str = Field("s3://datapilot-datasets-dev/mlflow/")

    # ── Validators ────────────────────────────────────────────────────────

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}, got '{v}'")
        return upper

    @field_validator("app_env")
    @classmethod
    def validate_app_env(cls, v: str) -> str:
        allowed = {"development", "test", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"app_env must be one of {allowed}, got '{v}'")
        return v

    @model_validator(mode="after")
    def warn_insecure_defaults_in_production(self) -> Settings:
        if self.app_env == "production":
            if self.secret_key.startswith("change-me"):
                raise ValueError("secret_key must be changed from the default in production")
            if self.enable_swagger:
                import warnings

                warnings.warn(
                    "enable_swagger=True in production exposes API internals", stacklevel=2
                )
        return self

    # ── Derived properties ────────────────────────────────────────────────

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def kafka_topic_map(self) -> dict[str, str]:
        """Returns the full event-type → topic mapping used by the Kafka event bus."""
        return {
            "DatasetUploaded": self.kafka_topic_dataset_uploaded,
            "SchemaInferred": self.kafka_topic_schema_inferred,
            "DatasetReady": self.kafka_topic_dataset_ready,
            "ProfilingCompleted": self.kafka_topic_profiling_complete,
            "CleaningCompleted": self.kafka_topic_cleaning_complete,
            "InsightReportGenerated": self.kafka_topic_insight_generated,
            "AnomaliesDetected": self.kafka_topic_anomaly_detected,
            "MessageAdded": self.kafka_topic_chat_message,
            "AgentResultReady": self.kafka_topic_agent_result,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings singleton.

    The first call parses all environment variables and validates them.
    Subsequent calls return the cached instance with zero overhead.

    In tests, call ``get_settings.cache_clear()`` before monkeypatching
    environment variables to force re-parsing.
    """
    return Settings()
