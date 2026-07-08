"""AWS Bedrock configuration.

Kept separate from the main ``Settings`` class so that the Bedrock client,
retry handler, and cost tracker can import a focused config object without
pulling in all application settings.

Usage::

    from backend.config.bedrock_config import get_bedrock_config

    cfg = get_bedrock_config()
    client = boto3.client("bedrock-runtime", region_name=cfg.bedrock_region)
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BedrockConfig(BaseSettings):
    """AWS Bedrock client configuration.

    All values are read from environment variables (or the ``.env`` file)
    with the prefix stripped — e.g. ``BEDROCK_REGION`` maps to ``bedrock_region``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Region & endpoint ─────────────────────────────────────────────────
    bedrock_region: str = Field(
        "us-east-1",
        description="AWS region that hosts the Bedrock endpoints. "
        "Must match the region where your model access is approved.",
    )
    bedrock_endpoint_url: str | None = Field(
        None,
        description="Override the default Bedrock endpoint. "
        "Leave blank to use the standard regional endpoint "
        "(https://bedrock-runtime.<region>.amazonaws.com).",
    )

    # ── Model IDs ─────────────────────────────────────────────────────────
    bedrock_model_id_primary: str = Field(
        "anthropic.claude-sonnet-4-5",
        description="Primary reasoning model used by Planner, Orchestrator, "
        "Insight, Critic, Recommendation, and Report agents. "
        "Highest quality; higher cost and latency.",
    )
    bedrock_model_id_fast: str = Field(
        "anthropic.claude-haiku-4-5",
        description="Fast, cost-efficient model used by Intent, Schema, SQL, "
        "Validation, and Security agents where latency matters "
        "more than reasoning depth.",
    )
    bedrock_embedding_model_id: str = Field(
        "amazon.titan-embed-text-v2:0",
        description="Embeddings model for RAG vector indexing. "
        "Produces 1536-dimensional vectors; configurable to 256/512.",
    )

    # ── Inference parameters ──────────────────────────────────────────────
    bedrock_max_tokens: int = Field(
        4096,
        ge=1,
        le=8192,
        description="Maximum tokens in the assistant response. "
        "Sonnet 4.5 supports up to 8192 output tokens.",
    )
    bedrock_temperature: float = Field(
        0.1,
        ge=0.0,
        le=1.0,
        description="Sampling temperature. Low value (0.1) gives deterministic, "
        "structured outputs suitable for JSON generation. "
        "Use higher values only for creative narrative tasks.",
    )
    bedrock_top_p: float = Field(
        0.95,
        ge=0.0,
        le=1.0,
        description="Nucleus sampling probability. Works in conjunction with temperature.",
    )

    # ── Retry / throttle handling ─────────────────────────────────────────
    bedrock_max_retries: int = Field(
        5,
        ge=1,
        le=10,
        description="Maximum retry attempts on ThrottlingException, "
        "ModelNotReadyException, and other transient errors.",
    )
    bedrock_retry_base_delay_seconds: float = Field(
        2.0,
        ge=0.1,
        description="Base delay for exponential backoff. "
        "Actual delay = base * 2^(attempt-1) + jitter, "
        "capped at bedrock_retry_max_delay_seconds.",
    )
    bedrock_retry_max_delay_seconds: float = Field(
        60.0,
        ge=1.0,
        description="Upper bound on retry backoff delay.",
    )

    # ── Cost alerts ───────────────────────────────────────────────────────
    bedrock_cost_alert_threshold_per_session: float = Field(
        0.50,
        ge=0.0,
        description="Emit a warning log when estimated Bedrock cost for a "
        "single analysis session exceeds this USD amount.",
    )
    bedrock_cost_alert_threshold_daily: float = Field(
        50.00,
        ge=0.0,
        description="Emit a critical alert when estimated daily Bedrock cost "
        "across all sessions exceeds this USD amount.",
    )

    # ── IRSA ─────────────────────────────────────────────────────────────
    bedrock_irsa_role_arn: str = Field(
        "",
        description="IAM Role ARN for IRSA (IAM Roles for Service Accounts) "
        "in EKS. When set, the Bedrock client assumes this role via "
        "the pod's projected service account token. "
        "Leave blank in local development — the default credential "
        "chain (env vars → ~/.aws/credentials) is used instead.",
    )

    # ── Guardrails ────────────────────────────────────────────────────────
    bedrock_guardrail_id: str = Field(
        "",
        description="Bedrock Guardrail ID for content filtering applied to "
        "agent I/O in production. Leave blank to disable. "
        "Requires bedrock:ApplyGuardrail IAM permission.",
    )
    bedrock_guardrail_version: str = Field(
        "DRAFT",
        description="Guardrail version to apply ('DRAFT' or a numeric version string).",
    )

    # ── Validators ────────────────────────────────────────────────────────

    @field_validator("bedrock_model_id_primary", "bedrock_model_id_fast")
    @classmethod
    def validate_model_id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Model ID must not be blank")
        return v

    # ── Derived helpers ───────────────────────────────────────────────────

    @property
    def guardrails_enabled(self) -> bool:
        """True when a Guardrail ID is configured."""
        return bool(self.bedrock_guardrail_id)

    @property
    def use_custom_endpoint(self) -> bool:
        """True when a non-default Bedrock endpoint URL is configured."""
        return bool(self.bedrock_endpoint_url)

    def boto3_client_kwargs(self) -> dict:
        """Return keyword arguments for ``boto3.client('bedrock-runtime', ...)``.

        The caller should unpack these directly::

            import boto3
            client = boto3.client("bedrock-runtime", **cfg.boto3_client_kwargs())
        """
        kwargs: dict = {"region_name": self.bedrock_region}
        if self.bedrock_endpoint_url:
            kwargs["endpoint_url"] = self.bedrock_endpoint_url
        return kwargs

    def converse_inference_config(
        self,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> dict:
        """Return the ``inferenceConfig`` block for a Bedrock Converse API call."""
        return {
            "maxTokens": max_tokens or self.bedrock_max_tokens,
            "temperature": temperature if temperature is not None else self.bedrock_temperature,
            "topP": self.bedrock_top_p,
        }


@lru_cache(maxsize=1)
def get_bedrock_config() -> BedrockConfig:
    """Return the cached Bedrock configuration singleton.

    Call ``get_bedrock_config.cache_clear()`` in tests that need to
    vary Bedrock settings between test cases.
    """
    return BedrockConfig()
