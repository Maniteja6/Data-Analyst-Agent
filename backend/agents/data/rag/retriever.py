"""RAG Retriever — searches Qdrant and returns ranked schema/insight chunks.

Real-time design:
    The retriever is on the hot path of every chat message. Target: < 100ms.
    - Titan Embed v2 embedding: ~80ms
    - Qdrant vector search: ~10ms
    - Total: ~90ms before HyDE expansion adds ~200ms (Haiku)

    To keep the chat experience snappy, the retriever runs concurrently
    with the IntentAgent classification. The chat handler fires both tasks
    with asyncio.gather so embedding and intent classification overlap.

Multi-vector retrieval:
    When ``query_vectors`` (a list) is passed instead of a single vector,
    the retriever searches with each vector and merges results by score,
    deduplicating by chunk ID. This is used with HyDE multi-expansion.

Re-ranking:
    After vector search, results are re-ranked by a simple keyword overlap
    score (BM25-lite) to boost chunks that contain the exact column names
    mentioned in the user's query. This improves precision for narrow queries
    like "what is the average discount_pct?".
"""
from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)

DEFAULT_TOP_K    = 8
MIN_SCORE        = 0.60    # minimum cosine similarity to include in results
RERANK_BOOST     = 0.10    # added to score when chunk contains query terms


class Retriever:
    """Searches Qdrant for relevant chunks and applies lightweight re-ranking.

    Args:
        qdrant:       QdrantAdapter instance.
        embed_service: BedrockEmbeddingService instance.
    """

    def __init__(self, qdrant=None, embed_service=None) -> None:
        if qdrant is None:
            from backend.infrastructure.vector_store.qdrant_adapter import QdrantAdapter
            qdrant = QdrantAdapter()
        if embed_service is None:
            from backend.infrastructure.vector_store.bedrock_embedding_service import BedrockEmbeddingService
            embed_service = BedrockEmbeddingService()

        self._qdrant = qdrant
        self._embed  = embed_service

    async def retrieve(
        self,
        query: str,
        dataset_id: str,
        top_k: int = DEFAULT_TOP_K,
        min_score: float = MIN_SCORE,
    ) -> list[dict]:
        """Embed a query and search Qdrant for the top-k matching chunks.

        Args:
            query:      The user's question (or HyDE-expanded hypothetical answer).
            dataset_id: Dataset UUID — scopes the search to one dataset's chunks.
            top_k:      Maximum chunks to return after re-ranking.
            min_score:  Minimum cosine similarity to include (0.0–1.0).

        Returns:
            List of chunk dicts sorted by relevance score descending.
            Each dict has keys: id, content, chunk_type, column_name, score.
        """
        # Embed query
        vector = await self._embed.embed(query)

        # Vector search
        raw_results = await self._qdrant.search(
            vector=vector,
            dataset_id=dataset_id,
            top_k=top_k * 2,   # fetch more, then re-rank to top_k
        )

        # Filter by minimum score
        filtered = [r for r in raw_results if r.get("score", 0.0) >= min_score]

        # Re-rank
        reranked = self._rerank(filtered, query, top_k)

        logger.debug(
            "retriever_results",
            query_preview=query[:60],
            raw_count=len(raw_results),
            filtered_count=len(filtered),
            returned=len(reranked),
        )
        return reranked

    async def retrieve_multi_vector(
        self,
        query_vectors: list[list[float]],
        dataset_id: str,
        top_k: int = DEFAULT_TOP_K,
    ) -> list[dict]:
        """Search with multiple query vectors and merge results.

        Used with HyDE multi-expansion to average across N hypothetical answers.

        Args:
            query_vectors: List of embedding vectors (one per HyDE expansion).
            dataset_id:    Dataset UUID.
            top_k:         Maximum chunks to return after deduplication.

        Returns:
            Deduplicated and score-averaged result list.
        """
        import asyncio

        tasks = [
            self._qdrant.search(vector=v, dataset_id=dataset_id, top_k=top_k)
            for v in query_vectors
        ]
        all_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Merge and average scores by chunk ID
        merged: dict[str, dict] = {}
        counts: dict[str, int]  = {}
        for results in all_results:
            if isinstance(results, Exception):
                continue
            for r in results:
                chunk_id = r.get("id", "")
                if chunk_id in merged:
                    merged[chunk_id]["score"] = (
                        merged[chunk_id]["score"] * counts[chunk_id] + r.get("score", 0.0)
                    ) / (counts[chunk_id] + 1)
                    counts[chunk_id] += 1
                else:
                    merged[chunk_id] = dict(r)
                    counts[chunk_id] = 1

        deduped = sorted(merged.values(), key=lambda r: r.get("score", 0.0), reverse=True)
        return deduped[:top_k]

    @staticmethod
    def _rerank(results: list[dict], query: str, top_k: int) -> list[dict]:
        """Boost chunks that contain query keywords (BM25-lite re-ranking)."""
        query_terms = set(query.lower().split())
        scored = []
        for r in results:
            content       = (r.get("payload", {}).get("content") or r.get("content", "")).lower()
            keyword_hits  = sum(1 for term in query_terms if term in content)
            boost         = min(RERANK_BOOST * keyword_hits, 0.30)
            final_score   = min(1.0, r.get("score", 0.0) + boost)
            scored.append({**r, "score": round(final_score, 4)})

        scored.sort(key=lambda r: r["score"], reverse=True)
        return scored[:top_k]

    def build_context_string(
        self,
        results: list[dict],
        max_chars: int = 3000,
    ) -> str:
        """Join retrieved chunks into a single context string for the LLM.

        Args:
            results:   List of chunk dicts from ``retrieve()``.
            max_chars: Maximum total characters in the context string.

        Returns:
            Concatenated chunk content, truncated to max_chars.
        """
        parts  = []
        total  = 0
        for r in results:
            payload = r.get("payload", {})
            content = payload.get("content") or r.get("content", "")
            if not content:
                continue
            chunk_type = payload.get("chunk_type") or r.get("chunk_type", "")
            block      = f"[{chunk_type.upper()}]\n{content}"
            if total + len(block) > max_chars:
                break
            parts.append(block)
            total += len(block)

        return "\n\n".join(parts)
