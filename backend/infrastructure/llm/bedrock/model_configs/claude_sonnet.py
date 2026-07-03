"""Claude Sonnet 4.5 model configuration — primary reasoning model.

Used by agents that require deep reasoning, structured output, and long
context: PlannerAgent, OrchestratorAgent, InsightAgent, CriticAgent,
RecommendationAgent, ReportAgent.

Pricing (us-east-1, as of Q4 2024 — update if AWS revises):
    Input:  $3.00  / 1M tokens
    Output: $15.00 / 1M tokens
"""
from __future__ import annotations

# ── Identity ──────────────────────────────────────────────────────────────
MODEL_ID      = "anthropic.claude-sonnet-4-5"
DISPLAY_NAME  = "Claude Sonnet 4.5"
PROVIDER      = "Anthropic"

# ── Context and output limits ─────────────────────────────────────────────
CONTEXT_WINDOW_TOKENS = 200_000   # maximum input context
MAX_OUTPUT_TOKENS     = 8_192     # maximum tokens in a single response

# ── Default inference parameters ─────────────────────────────────────────
DEFAULT_TEMPERATURE  = 0.1    # low temperature for deterministic structured output
DEFAULT_TOP_P        = 0.95
DEFAULT_MAX_TOKENS   = 4_096  # conservative default; set higher for long reports

# ── Bedrock pricing (USD per 1M tokens) ──────────────────────────────────
PRICE_PER_1M_INPUT_USD  = 3.00
PRICE_PER_1M_OUTPUT_USD = 15.00

# ── Cross-region inference profile IDs ───────────────────────────────────
# Use these when on-demand throughput requires cross-region routing.
# Pass as model_id instead of MODEL_ID when using inference profiles.
INFERENCE_PROFILE_US = "us.anthropic.claude-sonnet-4-5-20241022-v1:0"

# ── Capability flags ──────────────────────────────────────────────────────
SUPPORTS_VISION           = True    # image inputs via the Converse API
SUPPORTS_TOOL_USE         = True    # tool/function calling
SUPPORTS_STREAMING        = True    # ConverseStream API
SUPPORTS_SYSTEM_PROMPT    = True    # separate system parameter in Converse
SUPPORTS_JSON_MODE        = False   # no native JSON mode; use system prompt instruction

# ── Agent role assignments ────────────────────────────────────────────────
# Agents in this list call get_model_id("planner") etc. and receive MODEL_ID.
PRIMARY_AGENT_ROLES = frozenset({
    "planner",
    "orchestrator",
    "insight",
    "critic",
    "recommendation",
    "report",
    "rag",
    "python",
    "visualization",
    "memory",
})


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    """Return estimated USD cost for one Converse API call."""
    input_cost  = (input_tokens  / 1_000_000) * PRICE_PER_1M_INPUT_USD
    output_cost = (output_tokens / 1_000_000) * PRICE_PER_1M_OUTPUT_USD
    return round(input_cost + output_cost, 8)


def converse_inference_config(
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> dict:
    """Return the ``inferenceConfig`` block for a Bedrock Converse API call."""
    return {
        "maxTokens":   max_tokens   or DEFAULT_MAX_TOKENS,
        "temperature": temperature  if temperature is not None else DEFAULT_TEMPERATURE,
        "topP":        DEFAULT_TOP_P,
    }
