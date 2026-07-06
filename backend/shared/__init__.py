"""Shared kernel — base classes and utilities used across all bounded contexts."""
"""Shared kernel — cross-cutting utilities imported by every backend layer.

Modules (all pure stdlib, zero I/O):
    domain_event.py     — DomainEvent(event_type, aggregate_id, occurred_at,
                            correlation_id, payload) with to_dict() / from_dict()
    exceptions.py       — Exception hierarchy:
                            DomainException        (base, .code attribute)
                              ValidationException  (.field attribute)
                              AgentException       (.agent_name attribute)
                              DatasetNotFoundException
                              InsightReportNotFoundException
                              ConversationNotFoundException
                              DuplicateDatasetError
                              InvalidStatusTransitionError

Sub-packages:
    utils/
        uuid_factory.py    — new_uuid() → str   (uuid4 as string)
        hash_utils.py      — llm_cache_key(model_id, prompt) → SHA-256 hex
                              content_hash(data: bytes) → SHA-256 hex
        datetime_utils.py  — utcnow(), format_iso(), parse_iso()

Dependency rule:
    Zero imports from any other backend sub-package.
    Pure Python stdlib only.
    Safe to import from domain, application, infrastructure, agents,
    and orchestration with no risk of circular dependencies.

Correlation ID threading (real-time observability):
    Every DomainEvent carries correlation_id which propagates through:
        HTTP request header  → CorrelationIdMiddleware → structlog context
        structlog context    → every log line in the request scope
        DomainEvent payload  → Kafka message header
        Kafka message header → KafkaConsumer structlog context
        event_handler        → ICacheService.publish_json() payload
        Redis payload        → Socket.IO event.correlation_id field
        Socket.IO field      → browser DevTools can trace end-to-end

    One field links: HTTP request → Celery task → Kafka event →
    Redis pub/sub → Socket.IO frame → OTel span → Postgres audit row.
"""
