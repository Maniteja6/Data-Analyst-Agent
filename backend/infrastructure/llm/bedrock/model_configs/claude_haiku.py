"""Claude Haiku 4.5 model configuration — fast, cost-efficient model.

Used by agents where latency and cost matter more than reasoning depth:
IntentAgent, SchemaAgent, SQLAgent (generation only), ValidationAgent,
SecurityAgent.

Pricing (us-east-1, as of Q4 2024):
    Input:  $0.25  / 1M tokens
    Output: $1.25  / 1M tokens

Claude Haiku is ~12× cheaper than Claude Sonnet for input tokens and
~12× faster for time-to-first-token. For classification tasks (intent,
semantic type, SQL generation) it performs comparably to Sonnet.
"""

from __future__ import annotations

# ── Identity ──────────────────────────────────────────────────────────────
MODEL_ID = "anthropic.claude-haiku-4-5"
DISPLAY_NAME = "Claude Haiku 4.5"
PROVIDER = "Anthropic"

# ── Context and output limits ─────────────────────────────────────────────
CONTEXT_WINDOW_TOKENS = 200_000
MAX_OUTPUT_TOKENS = 4_096

# ── Default inference parameters ─────────────────────────────────────────
DEFAULT_TEMPERATURE = 0.1
DEFAULT_TOP_P = 0.95
DEFAULT_MAX_TOKENS = 2_048  # generous for classification + SQL generation

# ── Bedrock pricing (USD per 1M tokens) ──────────────────────────────────
PRICE_PER_1M_INPUT_USD = 0.25
PRICE_PER_1M_OUTPUT_USD = 1.25

# ── Cross-region inference profile ID ────────────────────────────────────
INFERENCE_PROFILE_US = "us.anthropic.claude-haiku-4-5-20241022-v1:0"

# ── Capability flags ──────────────────────────────────────────────────────
SUPPORTS_VISION = True
SUPPORTS_TOOL_USE = True
SUPPORTS_STREAMING = True
SUPPORTS_SYSTEM_PROMPT = True
SUPPORTS_JSON_MODE = False

# ── Agent role assignments ────────────────────────────────────────────────
FAST_AGENT_ROLES = frozenset(
    {
        "intent",
        "schema",
        "sql",
        "validation",
        "security",
    }
)


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    """Return estimated USD cost for one Converse API call."""
    input_cost = (input_tokens / 1_000_000) * PRICE_PER_1M_INPUT_USD
    output_cost = (output_tokens / 1_000_000) * PRICE_PER_1M_OUTPUT_USD
    return round(input_cost + output_cost, 8)


def converse_inference_config(
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> dict:
    """Return the ``inferenceConfig`` block for a Bedrock Converse API call."""
    return {
        "maxTokens": max_tokens or DEFAULT_MAX_TOKENS,
        "temperature": temperature if temperature is not None else DEFAULT_TEMPERATURE,
        "topP": DEFAULT_TOP_P,
    }
