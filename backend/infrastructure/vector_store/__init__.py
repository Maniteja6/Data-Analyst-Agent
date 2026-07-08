"""Vector store — Qdrant + Bedrock Titan Embed v2.

BedrockEmbeddingService: embed() with Redis SHA-256 cache (7d TTL, >80% hit rate);
                         embed_batch() with asyncio.Semaphore(4) for rate limiting.
QdrantAdapter:           upsert(), search() with dataset_id filter, delete_by_dataset().
CollectionManager:       initialise(), recreate(), index_dataset().
Target:                  embed + search + rerank < 100ms on WebSocket hot path.
"""

from backend.infrastructure.vector_store.bedrock_embedding_service import BedrockEmbeddingService
from backend.infrastructure.vector_store.collection_manager import CollectionManager
from backend.infrastructure.vector_store.qdrant_adapter import QdrantAdapter

__all__ = ["QdrantAdapter", "BedrockEmbeddingService", "CollectionManager"]
