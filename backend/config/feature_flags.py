"""Runtime feature flags.

Feature flags let us ship code that is disabled in production until
it is ready, run A/B tests, or quickly disable a feature if it
causes issues — without redeploying the service.

All flags are read from environment variables so they can be toggled
per-environment via Kubernetes ConfigMaps without a code change.

Usage::

    from backend.config.feature_flags import flags

    if flags.rag_enabled:
        context = await rag_agent.retrieve(query, dataset_id)

Or the lower-level helper::

    from backend.config.feature_flags import is_enabled

    if is_enabled("RAG"):
        ...

Flag environment variable format:  ``FEATURE_<FLAG_NAME>=true``
Example:  ``FEATURE_RAG=true``, ``FEATURE_ML_AGENT=false``
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Low-level helper
# ---------------------------------------------------------------------------


def is_enabled(flag_name: str, default: bool = False) -> bool:
    """Return True if the ``FEATURE_<FLAG_NAME>`` env var is set to a truthy value.

    Truthy values: ``"1"``, ``"true"``, ``"yes"``, ``"on"`` (case-insensitive).
    All other values (including missing key) are treated as False.

    Args:
        flag_name: Flag identifier without the ``FEATURE_`` prefix.
                   Case-insensitive — ``"rag"`` and ``"RAG"`` are equivalent.
        default:   Value to return when the environment variable is not set.
    """
    raw = os.environ.get(f"FEATURE_{flag_name.upper()}")
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Typed flag container — single source of truth for all flags
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FeatureFlags:
    """Immutable snapshot of all feature flags at startup.

    Flags are read once when the singleton is constructed. Changes to
    environment variables after startup require a process restart.

    To add a new flag:
      1. Add a field here with a sensible default.
      2. Document which team owns it and when it can be removed.
      3. Add a ``FEATURE_<NAME>`` entry to ``.env.example`` and Terraform
         variable definitions.
    """

    # ── AI agents ─────────────────────────────────────────────────────────

    rag_enabled: bool = False
    """Enable RAG (Retrieval-Augmented Generation) for chat queries.
    Indexes dataset chunks into Qdrant and augments prompts with retrieved context.
    Owner: AI team. Remove when RAG is always-on.
    """

    forecasting_enabled: bool = False
    """Enable the Forecast agent (Prophet / AutoARIMA / XGBoost).
    Disabled by default because it requires Prophet + statsforecast which
    have heavy dependencies (Stan compiler).
    Owner: Analytics team.
    """

    ml_agent_enabled: bool = False
    """Enable the AutoML agent (scikit-learn RandomForest cross-validation).
    Computationally expensive — keep disabled for datasets < 10k rows.
    Owner: AI team.
    """

    visualization_agent_enabled: bool = False
    """Enable the Visualization agent (Vega-Lite spec generation).
    Owner: Frontend team. Enable once the frontend Vega renderer is stable.
    """

    critic_enabled: bool = False
    """Enable the Critic agent (LLM self-critique and insight revision).
    Adds ~1-2 Bedrock round-trips per analysis. Disable in cost-constrained envs.
    Owner: AI team.
    """

    # ── Security ──────────────────────────────────────────────────────────

    pii_detection_enabled: bool = False
    """Enable Presidio PII scanning on user messages and agent outputs.
    Requires presidio-analyzer with spaCy model installed.
    Owner: Security team.
    """

    injection_detection_enabled: bool = False
    """Enable heuristic prompt injection detection on user messages.
    Owner: Security team.
    """

    bedrock_guardrails_enabled: bool = False
    """Apply Bedrock Guardrails to agent I/O (content filtering, topic blocking).
    Requires a Guardrail configured in the AWS console and
    BEDROCK_GUARDRAIL_ID to be set.
    Owner: Security team. Production only.
    """

    # ── Infrastructure ────────────────────────────────────────────────────

    kafka_enabled: bool = False
    """Publish domain events to Kafka (MSK) instead of in-process.
    Disable in local development when Kafka is not running.
    Owner: Platform team.
    """

    clickhouse_enabled: bool = False
    """Write column statistics to ClickHouse for cross-dataset analytics.
    Owner: Analytics team.
    """

    mlflow_enabled: bool = False
    """Log forecast / ML model runs to MLflow.
    Owner: AI team.
    """

    # ── API behaviour ─────────────────────────────────────────────────────

    streaming_responses_enabled: bool = False
    """Stream chat responses token-by-token via SSE / Socket.IO.
    Requires BedrockStreamAdapter. Disable to fall back to single-response mode.
    Owner: Frontend team.
    """

    presigned_upload_enabled: bool = False
    """Allow the frontend to upload directly to S3 via a presigned URL,
    bypassing the API server. Reduces upload latency for large files.
    Owner: Platform team.
    """

    @classmethod
    def from_env(cls) -> FeatureFlags:
        """Construct a FeatureFlags instance by reading all env vars."""
        return cls(
            rag_enabled=is_enabled("RAG"),
            forecasting_enabled=is_enabled("FORECASTING"),
            ml_agent_enabled=is_enabled("ML_AGENT"),
            visualization_agent_enabled=is_enabled("VISUALIZATION_AGENT"),
            critic_enabled=is_enabled("CRITIC"),
            pii_detection_enabled=is_enabled("PII_DETECTION"),
            injection_detection_enabled=is_enabled("INJECTION_DETECTION"),
            bedrock_guardrails_enabled=is_enabled("BEDROCK_GUARDRAILS"),
            kafka_enabled=is_enabled("KAFKA"),
            clickhouse_enabled=is_enabled("CLICKHOUSE"),
            mlflow_enabled=is_enabled("MLFLOW"),
            streaming_responses_enabled=is_enabled("STREAMING_RESPONSES"),
            presigned_upload_enabled=is_enabled("PRESIGNED_UPLOAD"),
        )

    def as_dict(self) -> dict[str, bool]:
        """Return all flags as a plain dict (useful for logging / health endpoints)."""
        import dataclasses

        return dataclasses.asdict(self)


# ---------------------------------------------------------------------------
# Singleton — loaded once at import time
# ---------------------------------------------------------------------------

flags: FeatureFlags = FeatureFlags.from_env()
"""Global feature flag snapshot.

Imported and used throughout the codebase::

    from backend.config.feature_flags import flags

    if flags.rag_enabled:
        ...

In tests, rebuild the singleton after patching env vars::

    import os
    from backend.config import feature_flags

    os.environ["FEATURE_RAG"] = "true"
    feature_flags.flags = feature_flags.FeatureFlags.from_env()
"""
