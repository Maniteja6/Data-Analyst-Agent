"""Append-only audit logger for DataPilot.

The audit log records security-relevant and data-access events for:
- SOC 2 Type II compliance (access control, change management)
- GDPR Article 30 (record of processing activities)
- Internal security incident investigation

Design principles:
1. **Append-only** — audit records are never updated or deleted.
   In production the ``audit_events`` Postgres table has a row-level
   security policy that permits only INSERT, and a Kafka consumer streams
   events to S3 for long-term immutable storage.

2. **Structured JSON** — every record is a JSON object so it can be
   ingested by CloudWatch Logs Insights or Splunk without parsing.

3. **Non-blocking** — all methods are ``async`` and use ``structlog``
   which buffers and flushes asynchronously. A write failure must never
   fail the primary request.

4. **No PII in log values** — user-supplied content (SQL queries, chat
   messages) is SHA-256 hashed before logging. Only metadata (lengths,
   column names, agent names) is stored in plain text.

Kafka topic: ``audit.events``

Usage::

    from backend.infrastructure.observability.audit_logger import AuditLogger

    audit = AuditLogger()

    await audit.log_dataset_uploaded(
        dataset_id="ds-123",
        filename="sales_q4.csv",
        size_bytes=4096,
        user_id="u-456",
    )

    await audit.log_agent_execution(
        agent_name="sql",
        session_id="sess-789",
        status="success",
        input_hash="a1b2c3…",
        output_hash="d4e5f6…",
        duration_ms=1230,
    )
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import structlog

from backend.shared.utils.uuid_factory import new_uuid
from backend.shared.utils.hash_utils import sha256_of_string

_audit_log = structlog.get_logger("datapilot.audit")


class AuditLogger:
    """Structured, append-only audit logger.

    All ``log_*`` methods are ``async`` so they can be awaited inside
    FastAPI route handlers without blocking. The underlying structlog
    call is synchronous (structlog itself is not async) but the method
    signature is async to allow future replacement with a fully async
    write path (e.g. ``aiokafka`` producer) without changing call sites.
    """

    # ── Dataset events ────────────────────────────────────────────────────

    async def log_dataset_uploaded(
        self,
        dataset_id: str,
        filename: str,
        size_bytes: int,
        mime_type: str = "",
        user_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """Record a dataset file upload."""
        await self._emit(
            event_type="dataset.uploaded",
            dataset_id=dataset_id,
            filename_hash=sha256_of_string(filename)[:16],  # hash to avoid PII in filename
            size_bytes=size_bytes,
            mime_type=mime_type,
            user_id=user_id,
            correlation_id=correlation_id,
        )

    async def log_dataset_accessed(
        self,
        dataset_id: str,
        action: str,
        user_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """Record read access to a dataset (download, preview, analysis trigger).

        Args:
            action: One of ``'read'``, ``'download'``, ``'analyse'``, ``'delete'``.
        """
        await self._emit(
            event_type="dataset.accessed",
            dataset_id=dataset_id,
            action=action,
            user_id=user_id,
            correlation_id=correlation_id,
        )

    async def log_dataset_deleted(
        self,
        dataset_id: str,
        user_id: str | None = None,
    ) -> None:
        """Record a dataset soft-delete or GDPR erasure request."""
        await self._emit(
            event_type="dataset.deleted",
            dataset_id=dataset_id,
            user_id=user_id,
        )

    # ── Agent / pipeline events ───────────────────────────────────────────

    async def log_agent_execution(
        self,
        agent_name: str,
        session_id: str,
        status: str,
        input_hash: str | None = None,
        output_hash: str | None = None,
        duration_ms: int = 0,
        token_count: int = 0,
        cost_usd: float = 0.0,
        model_id: str = "",
    ) -> None:
        """Record one agent invocation result.

        ``input_hash`` and ``output_hash`` are SHA-256 digests of the
        serialised AgentInput and AgentResult payloads. This lets security
        teams verify that a specific input always produced a specific output
        without storing the raw LLM content in the audit log.
        """
        await self._emit(
            event_type="agent.executed",
            agent_name=agent_name,
            session_id=session_id,
            status=status,             # success | failure | retry
            input_hash=input_hash,
            output_hash=output_hash,
            duration_ms=duration_ms,
            token_count=token_count,
            cost_usd=cost_usd,
            model_id=model_id,
        )

    async def log_pipeline_started(
        self,
        dataset_id: str,
        session_id: str,
        trigger: str,
        correlation_id: str | None = None,
    ) -> None:
        """Record the start of an analysis pipeline run."""
        await self._emit(
            event_type="pipeline.started",
            dataset_id=dataset_id,
            session_id=session_id,
            trigger=trigger,
            correlation_id=correlation_id,
        )

    async def log_pipeline_completed(
        self,
        dataset_id: str,
        session_id: str,
        status: str,
        duration_seconds: float,
        insight_count: int = 0,
        anomaly_count: int = 0,
    ) -> None:
        """Record the completion (or failure) of a full pipeline run."""
        await self._emit(
            event_type="pipeline.completed",
            dataset_id=dataset_id,
            session_id=session_id,
            status=status,
            duration_seconds=duration_seconds,
            insight_count=insight_count,
            anomaly_count=anomaly_count,
        )

    # ── Security events ───────────────────────────────────────────────────

    async def log_pii_detected(
        self,
        session_id: str,
        entity_types: list[str],
        source: str,
        action_taken: str = "blocked",
    ) -> None:
        """Record PII detection by the Security Agent.

        Args:
            entity_types:  List of detected PII entity types (e.g. ``['EMAIL', 'PHONE']``).
            source:        Where PII was found: ``'user_input'`` or ``'agent_output'``.
            action_taken:  ``'blocked'``, ``'redacted'``, or ``'flagged'``.
        """
        await self._emit(
            event_type="security.pii_detected",
            session_id=session_id,
            entity_types=entity_types,
            entity_count=len(entity_types),
            source=source,
            action_taken=action_taken,
        )

    async def log_injection_attempt(
        self,
        session_id: str | None,
        score: float,
        user_id: str | None = None,
        action_taken: str = "blocked",
    ) -> None:
        """Record a detected prompt injection attempt.

        Args:
            score:        Injection classifier confidence (0.0–1.0).
            action_taken: ``'blocked'`` or ``'flagged'``.
        """
        await self._emit(
            event_type="security.injection_attempt",
            session_id=session_id,
            injection_score=round(score, 4),
            user_id=user_id,
            action_taken=action_taken,
        )

    async def log_sql_blocked(
        self,
        session_id: str,
        blocked_keyword: str,
        sql_hash: str | None = None,
    ) -> None:
        """Record a SQL query blocked by the whitelist validator."""
        await self._emit(
            event_type="security.sql_blocked",
            session_id=session_id,
            blocked_keyword=blocked_keyword,
            sql_hash=sql_hash,
        )

    async def log_rate_limit_exceeded(
        self,
        client_ip: str,
        endpoint: str,
        limit_per_minute: int,
    ) -> None:
        """Record a rate limit violation."""
        await self._emit(
            event_type="security.rate_limit_exceeded",
            client_ip_hash=sha256_of_string(client_ip)[:16],  # hash IP for GDPR compliance
            endpoint=endpoint,
            limit_per_minute=limit_per_minute,
        )

    # ── Memory / conversation events ──────────────────────────────────────

    async def log_memory_compressed(
        self,
        conversation_id: str,
        turns_compressed: int,
        dataset_id: str = "",
    ) -> None:
        """Record a conversation memory compression by the MemoryAgent."""
        await self._emit(
            event_type="conversation.memory_compressed",
            conversation_id=conversation_id,
            turns_compressed=turns_compressed,
            dataset_id=dataset_id,
        )

    async def log_report_exported(
        self,
        dataset_id: str,
        session_id: str,
        format: str,
        user_id: str | None = None,
    ) -> None:
        """Record a report export (PDF/XLSX/PPTX/JSON)."""
        await self._emit(
            event_type="report.exported",
            dataset_id=dataset_id,
            session_id=session_id,
            format=format,
            user_id=user_id,
        )

    # ── Insight / data access ─────────────────────────────────────────────

    async def log_insight_viewed(
        self,
        dataset_id: str,
        session_id: str,
        insight_count: int,
        user_id: str | None = None,
    ) -> None:
        """Record a user viewing the insight report (GET /insights/<dataset_id>)."""
        await self._emit(
            event_type="insight.viewed",
            dataset_id=dataset_id,
            session_id=session_id,
            insight_count=insight_count,
            user_id=user_id,
        )

    # ── Internal emit ─────────────────────────────────────────────────────

    async def _emit(
        self,
        event_type: str,
        **fields: Any,
    ) -> None:
        """Write a structured audit log record.

        Every record includes:
        - ``audit_id``     — unique UUID for deduplication and cross-system correlation
        - ``event_type``   — dot-namespaced event identifier
        - ``occurred_at``  — UTC ISO-8601 timestamp

        The underlying structlog call is synchronous. For high-throughput
        scenarios, swap ``_audit_log.info(...)`` with an ``aiokafka``
        producer ``await producer.send(AUDIT_TOPIC, ...)`` without
        changing the public API.

        Failures are silently swallowed — a logging failure must never
        propagate to the application layer.
        """
        try:
            record = {
                "audit_id":    new_uuid(),
                "event_type":  event_type,
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                **{k: v for k, v in fields.items() if v is not None},
            }
            _audit_log.info("audit_event", **record)
        except Exception:
            # Silently swallow — never fail the primary request due to audit logging
            pass

    # ── Batch helper (for bulk imports or migration scripts) ──────────────

    async def log_batch(self, events: list[dict[str, Any]]) -> None:
        """Emit multiple audit events in sequence.

        Each dict must contain at least ``event_type``. All other keys are
        treated as event-specific fields.

        Args:
            events: List of event dicts to emit.
        """
        for event in events:
            event_type = event.pop("event_type", "unknown")
            await self._emit(event_type, **event)
