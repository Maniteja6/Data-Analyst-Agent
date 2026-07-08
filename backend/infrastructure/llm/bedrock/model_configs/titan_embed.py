"""Amazon Titan Embeddings Text v2 model configuration.

Used exclusively by ``BedrockEmbeddingAdapter`` and ``BedrockEmbeddingService``
to embed schema chunks, profile summaries, and user chat queries for RAG.

Titan Embed v2 improvements over v1:
- Configurable output dimensions (1536 / 512 / 256) for storage/quality tradeoff
- Built-in L2 normalisation (set ``normalize=True``)
- Better multilingual coverage

Pricing (us-east-1, as of Q4 2024):
    $0.02 / 1M input tokens (no output tokens — embeddings only)
"""

from __future__ import annotations

# ── Identity ──────────────────────────────────────────────────────────────
MODEL_ID = "amazon.titan-embed-text-v2:0"
DISPLAY_NAME = "Amazon Titan Embeddings Text v2"
PROVIDER = "Amazon"

# ── Input limits ──────────────────────────────────────────────────────────
MAX_INPUT_TOKENS = 8_192
MAX_INPUT_CHARS = 32_000  # safe character ceiling at ~4 chars/token

# ── Output configuration ──────────────────────────────────────────────────
# Supported output dimensions — trade storage cost vs retrieval quality.
DIMENSION_HIGH = 1536  # best quality; default; Qdrant stores 1536-dim vectors
DIMENSION_MEDIUM = 512  # 66% storage saving; minimal quality loss for most RAG tasks
DIMENSION_LOW = 256  # maximum compression; use only for prototype / very large collections

DEFAULT_DIMENSIONS = DIMENSION_HIGH
NORMALIZE = True  # L2 normalise vectors (required for cosine similarity in Qdrant)

# ── Pricing (USD per 1M input tokens — no output cost for embeddings) ────
PRICE_PER_1M_INPUT_USD = 0.02
PRICE_PER_1M_OUTPUT_USD = 0.00  # embeddings have no output token cost

# ── Capability flags ──────────────────────────────────────────────────────
SUPPORTS_STREAMING = False  # InvokeModel only; no streaming for embeddings
SUPPORTS_BATCHING = False  # no native batch endpoint; use embed_batch() helper

# ── Bedrock InvokeModel request body factory ─────────────────────────────


def build_request_body(text: str, dimensions: int = DEFAULT_DIMENSIONS) -> dict:
    """Build the JSON request body for a Titan Embeddings InvokeModel call.

    Args:
        text:       Input text to embed. Truncated to ``MAX_INPUT_CHARS`` if longer.
        dimensions: Output vector size (1536, 512, or 256).

    Returns:
        Dict ready for ``json.dumps()`` and passing as the ``body`` parameter
        to ``bedrock_client.invoke_model()``.
    """
    return {
        "inputText": text[:MAX_INPUT_CHARS],
        "dimensions": dimensions,
        "normalize": NORMALIZE,
    }


def estimate_cost(input_tokens: int) -> float:
    """Return estimated USD cost for one InvokeModel embedding call."""
    return round((input_tokens / 1_000_000) * PRICE_PER_1M_INPUT_USD, 8)
