"""DataPilot domain layer — pure business logic for a real-time data analytics platform.

Zero infrastructure dependencies. Python stdlib + Pydantic only.
Every class here is safe to instantiate in a WebSocket handler, a Celery
task, a LangGraph node, or a unit test with no mocking required.

Why a strong domain layer matters for real-time apps
------------------------------------------------------
Real-time pipelines cross many async boundaries: HTTP → Celery → Kafka →
Socket.IO. The domain layer is the only code that runs identically in all
of them. Keeping it infrastructure-free means:

  • State machines (Dataset, Conversation) transition identically whether
    triggered by a REST upload or a Kafka consumer.
  • Domain events carry all the data needed by any event handler without
    coupling the handler to the aggregate that produced it.
  • Business rules (e.g. "a conversation cannot be reopened once closed")
    are enforced in one place regardless of which async path calls them.

Bounded contexts
----------------

analytics/
│   Owns the deterministic analysis pipeline state.
│
├── entities/
│   ├── analysis_session.py   AnalysisSession aggregate root
│   │     Status state machine: pending → running → complete | failed
│   │     Holds DataProfile + CleaningReport after each pipeline stage.
│   │     pull_domain_events() → [ProfilingCompleted, CleaningCompleted]
│   │
│   ├── data_profile.py       DataProfile — full per-column statistics
│   │     row_count, column_count, completeness_score, consistency_score,
│   │     duplicate_count, column_profiles: list[ColumnProfile]
│   │     has_time_series property drives ForecastAgent routing.
│   │
│   ├── column_profile.py     ColumnProfile + ColumnKind enum
│   │     kind: NUMERIC | TEXT | DATETIME | BOOLEAN | UNKNOWN
│   │     stats: StatisticalSummary | None
│   │     histogram: Histogram | None
│   │
│   ├── cleaning_report.py    CleaningReport + CleaningStep + CleaningAction
│   │     Ordered list of steps: REMOVE_DUPLICATES, IMPUTE_MEDIAN,
│   │     IMPUTE_MODE, DROP_HIGH_NULL_COL, COERCE_TO_FLOAT,
│   │     COERCE_TO_DATETIME, CLIP_OUTLIER
│   │
│   └── anomaly_alert.py      AnomalyAlert entity
│         detection_method: ZScore | IQR | IsolationForest | Rule
│         severity: critical | high | medium | low
│         confidence: float
│
├── value_objects/
│   ├── statistical_summary.py  mean, stddev, variance, min/max,
│   │                           P5/P25/P50/P75/P95, skewness, kurtosis
│   ├── histogram.py            Histogram with from_numeric_ranges() and
│   │                           from_value_counts() factories
│   │                           to_vega_spec() → Vega-Lite chart dict
│   └── correlation_coefficient.py  value, column_a, column_b,
│                                   method: PEARSON, sample_size
│
├── repositories/
│   └── session_repository.py   SessionRepository ABC
│         get_by_id, save, delete, get_by_dataset_id,
│         get_latest_by_dataset_id, get_by_status, count_by_dataset
│
└── services/
    └── data_quality_scorer.py  DataQualityScorer domain service
          score(profile) → QualityReport
          completeness_score, consistency_score, validity_score,
          timeliness_score, overall_score, grade (A–F)

─────────────────────────────────────────────────────────────────────────

dataset/
│   Owns the file upload and lifecycle state machine.
│
├── entities/
│   └── dataset.py            Dataset aggregate root
│         State machine (strict transitions enforced, raises
│         InvalidStatusTransitionError on invalid moves):
│
│           uploaded ──► profiling ──► profiled ──► cleaning ──► ready
│                   │                                        │
│                   └────────────────────────────────────────┴──► failed
│
│         Key methods:
│           Dataset.create(...)          → emits DatasetUploaded
│           dataset.begin_profiling()   → UPLOADED → PROFILING
│           dataset.complete_profiling()→ PROFILING → PROFILED
│           dataset.begin_cleaning()    → PROFILED → CLEANING
│           dataset.mark_ready(...)     → CLEANING → READY, emits DatasetReady
│           dataset.mark_failed(msg)    → any → FAILED, emits DatasetFailed
│           dataset.pull_domain_events()→ drains the internal event queue
│
│         Computed properties:
│           has_schema       → schema_json is not None and has columns
│           has_time_series  → schema_json has any datetime column
│           size_mb          → size_bytes / 1024²
│
├── value_objects/
│   └── dataset_status.py     DatasetStatus enum
│         UPLOADED | PROFILING | PROFILED | CLEANING | READY | FAILED
│         VALID_TRANSITIONS dict enforces the state machine
│
├── repositories/
│   └── dataset_repository.py  DatasetRepository ABC
│         get_by_id, save, delete, get_by_project, get_by_status,
│         get_by_checksum (dedup check), count_by_project
│
├── services/
│   └── dataset_service.py    DatasetService domain service
│         validate_file(filename, size_bytes) → raises ValidationError
│         infer_mime_from_extension(filename) → str
│         build_storage_key(dataset_id, filename) → str
│         Enforces: max file size, allowed extensions, filename sanitisation
│
└── exceptions.py
      DatasetNotFoundError(dataset_id)
      DuplicateDatasetError(checksum, existing_id)
      InvalidStatusTransitionError(from_status, to_status)

─────────────────────────────────────────────────────────────────────────

insight/
│   Owns the AI-generated analysis output.
│
├── entities/
│   └── insight_report.py     InsightReport aggregate root
│         executive_summary: str
│         insights: list[Insight]
│         kpis: list[KPI]
│         anomaly_alerts: list[AnomalyAlert]
│         forecasts: list[Forecast]
│         recommendations: list[Recommendation]
│         is_critic_validated: bool
│         has_forecasts, has_anomalies computed properties
│         to_dict() → full JSON-serialisable dict for Socket.IO events
│
├── repositories/
│   └── insight_repository.py  InsightRepository ABC
│         get_by_id, save, delete, get_by_dataset_id,
│         get_by_session_id, list_by_dataset
│
├── services/
│   └── kpi_calculator.py     KPICalculator domain service
│         calculate(report_id, profile) → list[KPI]
│         Always produces: Total Rows, Columns, Completeness, Duplicates
│         Currency columns produce: Avg <column_name> KPI
│
└── exceptions.py
      InsightReportNotFoundException(dataset_id)

─────────────────────────────────────────────────────────────────────────

intelligence/
│   Owns the AI agent execution model.
│
├── entities/
│   ├── execution_plan.py     ExecutionPlan aggregate root
│   │     tasks: list[TaskNode]
│   │     Status state machine: draft → running → complete | failed
│   │     get_ready_tasks(completed_ids) → tasks whose deps are satisfied
│   │     create_default(has_datetime, numeric_cols) → default 9–11 task plan
│   │     to_ws_event() → plan:ready Socket.IO payload with full topology
│   │     validate() → topological sort; raises ValueError on cycle
│   │
│   └── task_node.py          TaskNode entity
│         agent: AgentName enum
│         depends_on: list[str]   (other task_ids)
│         status: PENDING → RUNNING → SUCCEEDED | FAILED | SKIPPED
│         mark_running() / mark_succeeded() / mark_failed(error)
│         duration_ms computed from started_at / finished_at
│
├── value_objects/
│   ├── llm_response.py       LLMResponse value object
│   │     content: str
│   │     as_json() → strips markdown fences, parses JSON
│   │     as_json_safe(default) → returns default on parse error
│   │     as_sql() → strips ```sql fences
│   │     was_truncated → stop_reason == "max_tokens"
│   │     estimated_cost_usd → from _PRICE_TABLE[model_id]
│   │
│   └── intent_classification.py  IntentClassification value object
│         intent: Intent enum (10 types)
│         entities: IntentEntities (column, metric, time_range, filter_val, top_n)
│         requires_sql, requires_rag, requires_forecast, requires_viz
│         routing_label → "SQL + RAG" string for logging
│         fallback() class method for error recovery
│
└── services/  (empty — plan logic lives in entities)

─────────────────────────────────────────────────────────────────────────

workspace/
    Owns the real-time chat conversation model.

├── entities/
│   ├── conversation.py       Conversation aggregate root
│   │     Real-time design: stores messages as an in-memory list that
│   │     maps to JSONB in Postgres, avoiding JOIN overhead on every
│   │     WebSocket message. Memory compression happens in MemoryAgent
│   │     before this list overflows the LLM context window.
│   │
│   │     messages: list[Message]
│   │     memory_summary: str | None   (compressed history from MemoryAgent)
│   │     is_closed: bool
│   │
│   │     add_message(message) → appends + emits MessageSent
│   │     build_bedrock_messages() → [{role, content:[{text}]}] format
│   │       ready to pass directly to BedrockConverseAdapter.converse()
│   │     build_system_prompt(schema_summary, rag_context) → str
│   │       combines dataset schema + RAG context into the system turn
│   │     pull_domain_events() → drains MessageSent events
│   │
│   └── message.py            Message entity
│         role: MessageRole value object (USER | ASSISTANT | SYSTEM)
│         content: str
│         citations: list[dict]        (source references)
│         visualizations: list[dict]   (Vega-Lite specs)
│         to_dict() → Bedrock Converse API message dict
│         user_message(conversation_id, content) class method
│         assistant_message(conversation_id, content, citations,
│                           visualizations) class method
│
├── value_objects/
│   └── message_role.py       MessageRole value object
│         Role enum: USER | ASSISTANT | SYSTEM
│         from_string("user") → MessageRole class method
│
├── repositories/
│   └── conversation_repository.py  ConversationRepository ABC
│         get_by_id, save, delete, get_by_dataset_id,
│         get_by_project_id, get_active_by_dataset_id,
│         count_by_dataset, search_by_content
│
└── exceptions.py
      ConversationNotFoundError(conversation_id)
      ConversationClosedError(conversation_id)

─────────────────────────────────────────────────────────────────────────

Domain events (flow: aggregate → UseCase → IEventBus → Kafka → handler →
               Redis pub/sub → Socket.IO bridge → browser room)
─────────────────────────────────────────────────────────────────────────
Event                       Source aggregate    Handler
──────────────────────────────────────────────────────────────────────────
DatasetUploaded             Dataset.create()    on_dataset_uploaded
                                                → Redis job status 0%
DatasetReady                dataset.mark_ready()→ (no handler; status=ready)
DatasetFailed               dataset.mark_failed()→(no handler; status=failed)
ProfilingCompleted          AnalysisSession     on_profiling_completed
                                                → Redis job status 30%
CleaningCompleted           AnalysisSession     on_analytics_completed
                                                → enqueue Celery agent task
                                                → Redis job status 65%
InsightReportGenerated      InsightReport.create→on_insight_report_generated
                                                → invalidate Redis insight cache
                                                → Redis job status 100%
                                                → publish analysis.complete
MessageSent                 Conversation        (no Kafka; direct Socket.IO
                            .add_message()       from SendMessageUseCase)
ConversationCreated         Conversation.create (no handler; in-memory only)
"""

from __future__ import annotations

from backend.shared.domain_event import DomainEvent  # noqa: F401 — re-export for convenience

__all__ = ["DomainEvent"]
