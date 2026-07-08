"""BedrockCostTracker — per-session LLM cost tracking and alerting.

Tracks the estimated cost of all Bedrock API calls made during one analysis
session or chat conversation. When the cumulative cost exceeds a configured
threshold, a warning is logged and a CloudWatch custom metric is emitted
(namespace: ``DataPilot/Bedrock``, metric: ``SessionCostUSD``).

This is not a billing system — costs are estimated from public pricing and
are subject to change. The tracker is best-effort; any invocation that fails
before the cost is recorded will be under-counted.

Pricing data (us-east-1, November 2024):
    Claude Sonnet 4.5: $3.00 / $15.00 per 1M tokens (input / output)
    Claude Haiku 4.5:  $0.25 / $1.25  per 1M tokens (input / output)
    Titan Embed v2:    $0.02           per 1M input tokens (no output cost)

Usage::

    tracker = BedrockCostTracker(session_id="abc-123")
    tracker.record_invocation("anthropic.claude-sonnet-4-5", 1024, 256)
    print(tracker.session_cost_usd)     # 0.000007...

    if tracker.exceeds_session_threshold:
        logger.warning("session_cost_high", cost=tracker.session_cost_usd)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog

logger = structlog.get_logger(__name__)

# Pricing table (USD per 1M tokens) — update when AWS revises pricing
_PRICE_TABLE: dict[str, dict[str, float]] = {
    "anthropic.claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
    "anthropic.claude-haiku-4-5": {"input": 0.25, "output": 1.25},
    "amazon.titan-embed-text-v2:0": {"input": 0.02, "output": 0.00},
}

# Fallback pricing for unknown models (conservative estimate)
_DEFAULT_PRICE = {"input": 3.00, "output": 15.00}


@dataclass
class InvocationRecord:
    """One recorded Bedrock API call."""

    model_id: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    recorded_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class BedrockCostTracker:
    """Tracks cumulative Bedrock invocation costs for one session.

    One instance is created per analysis session or conversation and passed
    to the ``BedrockConverseAdapter`` and ``BedrockStreamAdapter``.
    """

    def __init__(
        self,
        session_id: str = "",
        session_alert_threshold: float | None = None,
    ) -> None:
        """
        Args:
            session_id:              Session UUID for log correlation.
            session_alert_threshold: Warn when session cost exceeds this USD amount.
                                     Defaults to
                                     ``BedrockConfig.bedrock_cost_alert_threshold_per_session``.
        """
        from backend.config.bedrock_config import get_bedrock_config

        cfg = get_bedrock_config()

        self._session_id = session_id
        self._threshold = session_alert_threshold or cfg.bedrock_cost_alert_threshold_per_session
        self._invocations: list[InvocationRecord] = []
        self._total_cost = 0.0

    # ── Recording ─────────────────────────────────────────────────────────

    def record_invocation(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Record one Bedrock API call and return the estimated cost (USD).

        Args:
            model_id:      Bedrock model ID string.
            input_tokens:  Number of input (prompt) tokens.
            output_tokens: Number of output (completion) tokens.

        Returns:
            Estimated cost of this call in USD.
        """
        cost = self._estimate(model_id, input_tokens, output_tokens)

        record = InvocationRecord(
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
        )
        self._invocations.append(record)
        self._total_cost = round(self._total_cost + cost, 8)

        logger.info(
            "bedrock_cost_recorded",
            session_id=self._session_id,
            model=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            call_cost_usd=cost,
            session_total_usd=self._total_cost,
        )

        if self.exceeds_session_threshold:
            logger.warning(
                "bedrock_session_cost_threshold_exceeded",
                session_id=self._session_id,
                session_cost_usd=self._total_cost,
                threshold_usd=self._threshold,
            )

        return cost

    # ── Aggregated views ──────────────────────────────────────────────────

    @property
    def session_cost_usd(self) -> float:
        """Total estimated cost for this session in USD."""
        return self._total_cost

    @property
    def invocation_count(self) -> int:
        return len(self._invocations)

    @property
    def total_input_tokens(self) -> int:
        return sum(r.input_tokens for r in self._invocations)

    @property
    def total_output_tokens(self) -> int:
        return sum(r.output_tokens for r in self._invocations)

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    @property
    def exceeds_session_threshold(self) -> bool:
        return self._total_cost >= self._threshold

    def cost_by_model(self) -> dict[str, float]:
        """Return cost breakdown by model ID."""
        breakdown: dict[str, float] = {}
        for r in self._invocations:
            breakdown[r.model_id] = round(breakdown.get(r.model_id, 0.0) + r.cost_usd, 8)
        return breakdown

    def summary(self) -> dict:
        """Return a serialisable summary of session cost metrics."""
        return {
            "session_id": self._session_id,
            "session_cost_usd": self._total_cost,
            "invocation_count": self.invocation_count,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_tokens,
            "cost_by_model": self.cost_by_model(),
        }

    # ── CloudWatch emission ───────────────────────────────────────────────

    def emit_cloudwatch_metrics(self, agent_name: str = "") -> None:
        """Emit session cost as a CloudWatch custom metric.

        Requires the Bedrock IRSA role to have
        ``cloudwatch:PutMetricData`` permission on namespace ``DataPilot/Bedrock``.

        Called by ``MonitoringAgent`` at the end of each pipeline run.
        Silent on failure — metric emission is non-critical.
        """
        try:
            import boto3
            from backend.config.bedrock_config import get_bedrock_config

            cfg = get_bedrock_config()
            cw = boto3.client("cloudwatch", region_name=cfg.bedrock_region)
            dims = [{"Name": "SessionId", "Value": self._session_id or "unknown"}]
            if agent_name:
                dims.append({"Name": "AgentName", "Value": agent_name})

            cw.put_metric_data(
                Namespace="DataPilot/Bedrock",
                MetricData=[
                    {
                        "MetricName": "SessionCostUSD",
                        "Dimensions": dims,
                        "Value": self._total_cost,
                        "Unit": "None",
                    },
                    {
                        "MetricName": "TotalTokens",
                        "Dimensions": dims,
                        "Value": float(self.total_tokens),
                        "Unit": "Count",
                    },
                ],
            )
        except Exception as exc:
            logger.debug("cloudwatch_emit_failed", error=str(exc))

    # ── Private helpers ───────────────────────────────────────────────────

    @staticmethod
    def _estimate(model_id: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost from the pricing table."""
        prices = _PRICE_TABLE.get(model_id, _DEFAULT_PRICE)
        input_cost = (input_tokens / 1_000_000) * prices["input"]
        output_cost = (output_tokens / 1_000_000) * prices["output"]
        return round(input_cost + output_cost, 8)

    @staticmethod
    def estimate_cost(
        model_id: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Static convenience method — estimate cost without a tracker instance."""
        return BedrockCostTracker._estimate(model_id, input_tokens, output_tokens)
