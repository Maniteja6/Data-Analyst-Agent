"""Bedrock adapter implementations — Converse, Stream, Embedding, Retry.

BedrockClient:           @lru_cache boto3 client; IRSA credentials in EKS.
BedrockConverseAdapter:  complete() + converse_multi_turn() batch calls.
BedrockStreamAdapter:    stream() async generator; Queue bridge for boto3 EventStream.
BedrockEmbeddingAdapter: embed() + embed_batch_serial(); dedicated thread pool.
BedrockRetryHandler:     @with_bedrock_retry; 4 retryable / 4 non-retryable errors.
BedrockCostTracker:      session cost accumulator + CloudWatch PutMetricData.
"""

from backend.infrastructure.llm.bedrock.bedrock_converse_adapter import BedrockConverseAdapter
from backend.infrastructure.llm.bedrock.bedrock_embedding_adapter import BedrockEmbeddingAdapter
from backend.infrastructure.llm.bedrock.bedrock_stream_adapter import BedrockStreamAdapter

__all__ = ["BedrockConverseAdapter", "BedrockStreamAdapter", "BedrockEmbeddingAdapter"]
