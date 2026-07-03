"""QdrantAdapter — async vector store client for RAG chunk retrieval.

Qdrant is the vector database used for RAG (Retrieval-Augmented Generation).
After each dataset profiling run, the ``RAGAgent`` embeds the schema
descriptions and column profile summaries via ``BedrockEmbeddingService``
and upserts them here. During chat, the same service embeds the user's
question and retrieves the most semantically similar chunks to inject as
context into the Bedrock prompt.

Collection schema
-----------------
Each point in the ``datapilot_chunks`` collection has:

    vector:   float[1536]   — Titan Embed v2 embedding of the chunk text
    payload:
        dataset_id:  str   — for dataset-scoped searches and deletion
        chunk_type:  str   — 'column_description' | 'profile_summary' | 'insight'
        column_name: str | None
        content:     str   — full chunk text (returned with results)
        metadata:    dict  — arbitrary extra fields (e.g. data_type, semantic_type)

Why Qdrant over pgvector?
    - Qdrant runs as a separate self-hostable service, decoupling vector
      workload from the transactional Postgres instance.
    - Supports payload filtering at the HNSW level (fast dataset-scoped retrieval
      without a full collection scan).
    - Native Python async client (``AsyncQdrantClient``).
    - IRSA-compatible — Qdrant itself uses an API key, stored in Secrets Manager.

Usage::

    from backend.infrastructure.vector_store.qdrant_adapter import get_qdrant_adapter

    qdrant = get_qdrant_adapter()
    await qdrant.ensure_collection()
    await qdrant.upsert([{"id": uuid, "vector": [...], "payload": {...}}])
    results = await qdrant.search(query_vector, dataset_id="abc-123", top_k=8)
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class QdrantAdapter:
    """Async Qdrant vector store adapter.

    Wraps ``qdrant_client.AsyncQdrantClient`` to provide a DataPilot-specific
    interface with standardised payload schema and dataset-scoped filtering.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        api_key: str | None = None,
        collection_name: str | None = None,
        vector_size: int | None = None,
    ) -> None:
        from backend.config.settings import get_settings
        settings = get_settings()

        self._host       = host            or settings.qdrant_host
        self._port       = port            or settings.qdrant_port
        self._api_key    = api_key         or settings.qdrant_api_key or None
        self._collection = collection_name or settings.qdrant_collection_name
        self._vector_size = vector_size    or settings.qdrant_vector_size
        self._client     = None   # lazily initialised

    # ── Client factory ────────────────────────────────────────────────────

    async def _get_client(self):
        """Return the async Qdrant client, creating it on first use."""
        if self._client is None:
            try:
                from qdrant_client import AsyncQdrantClient
                kwargs: dict = {"host": self._host, "port": self._port}
                if self._api_key:
                    kwargs["api_key"] = self._api_key
                self._client = AsyncQdrantClient(**kwargs)
                logger.info("qdrant_connected", host=self._host, port=self._port)
            except ImportError:
                raise RuntimeError(
                    "qdrant-client is not installed. "
                    "Add it to pyproject.toml or disable the RAG feature flag."
                )
        return self._client

    # ── Collection lifecycle ──────────────────────────────────────────────

    async def ensure_collection(self) -> None:
        """Create the collection if it does not already exist.

        Called once at application startup (when ``FEATURE_RAG`` is enabled)
        and again at the start of each indexing run as an idempotency guard.

        Uses HNSW (Hierarchical Navigable Small World) with Cosine distance —
        appropriate for normalised Titan Embed v2 vectors.
        """
        from qdrant_client.models import Distance, VectorParams

        client      = await self._get_client()
        collections = await client.get_collections()
        names       = [c.name for c in collections.collections]

        if self._collection not in names:
            await client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(
                    size=self._vector_size,
                    distance=Distance.COSINE,
                    on_disk=False,         # keep in RAM for low retrieval latency
                ),
            )
            logger.info(
                "qdrant_collection_created",
                collection=self._collection,
                vector_size=self._vector_size,
            )
        else:
            logger.debug("qdrant_collection_exists", collection=self._collection)

    async def delete_collection(self) -> None:
        """Delete the entire collection. Use with care — destroys all vectors."""
        client = await self._get_client()
        await client.delete_collection(self._collection)
        logger.warning("qdrant_collection_deleted", collection=self._collection)

    async def collection_info(self) -> dict:
        """Return collection metadata (point count, config, status)."""
        from qdrant_client import models
        client = await self._get_client()
        info   = await client.get_collection(self._collection)
        return {
            "name":        self._collection,
            "point_count": info.points_count,
            "status":      info.status.value if info.status else "unknown",
            "vector_size": self._vector_size,
        }

    # ── Upsert ────────────────────────────────────────────────────────────

    async def upsert(self, points: list[dict[str, Any]]) -> None:
        """Insert or update a list of vector points.

        Each dict must have:
            ``id``      — unique UUID string for the point
            ``vector``  — float list of length ``vector_size``
            ``payload`` — dict with at least ``dataset_id`` and ``content``

        Idempotent — re-upserting the same ``id`` updates the vector and payload.

        Args:
            points: List of point dicts.

        Raises:
            ValueError: When ``points`` is empty.
        """
        if not points:
            raise ValueError("Cannot upsert empty points list")

        from qdrant_client.models import PointStruct

        structs = [
            PointStruct(
                id=p["id"],
                vector=p["vector"],
                payload=p.get("payload", {}),
            )
            for p in points
        ]

        client = await self._get_client()
        await client.upsert(
            collection_name=self._collection,
            points=structs,
            wait=True,   # confirm indexing before returning
        )
        logger.info(
            "qdrant_upsert_complete",
            collection=self._collection,
            point_count=len(points),
        )

    # ── Search ────────────────────────────────────────────────────────────

    async def search(
        self,
        query_vector: list[float],
        dataset_id: str,
        top_k: int = 8,
        score_threshold: float = 0.72,
        chunk_type: str | None = None,
    ) -> list[dict]:
        """Search for the most similar chunks within a dataset.

        Args:
            query_vector:    Embedded query from BedrockEmbeddingService.
            dataset_id:      Restricts search to chunks belonging to this dataset.
                             Without this filter, RAG retrieves chunks from all
                             datasets in the collection — a significant data leak.
            top_k:           Maximum number of results to return.
            score_threshold: Minimum cosine similarity (0–1). Chunks below this
                             threshold are excluded to avoid irrelevant context injection.
            chunk_type:      Optional filter: ``'column_description'`` or ``'profile_summary'``.

        Returns:
            List of result dicts sorted by score (descending):
            ``[{"id": str, "score": float, "payload": dict}, …]``
        """
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        must_conditions = [
            FieldCondition(key="dataset_id", match=MatchValue(value=dataset_id))
        ]
        if chunk_type:
            must_conditions.append(
                FieldCondition(key="chunk_type", match=MatchValue(value=chunk_type))
            )

        filter_ = Filter(must=must_conditions)
        client  = await self._get_client()

        results = await client.search(
            collection_name=self._collection,
            query_vector=query_vector,
            query_filter=filter_,
            limit=top_k,
            score_threshold=score_threshold,
            with_payload=True,
            with_vectors=False,   # don't return the vector itself — saves bandwidth
        )

        hits = [
            {
                "id":      str(r.id),
                "score":   round(r.score, 6),
                "payload": r.payload or {},
            }
            for r in results
        ]

        logger.debug(
            "qdrant_search_complete",
            dataset_id=dataset_id,
            top_k=top_k,
            hits=len(hits),
            score_threshold=score_threshold,
        )
        return hits

    # ── Deletion ──────────────────────────────────────────────────────────

    async def delete_by_dataset(self, dataset_id: str) -> None:
        """Delete all chunks belonging to a dataset.

        Called when a dataset is deleted or re-analysed (to replace stale
        chunks with fresh embeddings from the updated profile).

        Qdrant ``delete`` with a payload filter is O(n) on point count —
        efficient for typical dataset sizes (< 500 columns → < 500 points).
        """
        from qdrant_client.models import Filter, FieldCondition, MatchValue, FilterSelector

        client = await self._get_client()
        await client.delete(
            collection_name=self._collection,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[FieldCondition(key="dataset_id", match=MatchValue(value=dataset_id))]
                )
            ),
        )
        logger.info("qdrant_dataset_chunks_deleted", dataset_id=dataset_id)

    async def delete_points(self, point_ids: list[str]) -> None:
        """Delete specific points by their IDs."""
        if not point_ids:
            return
        from qdrant_client.models import PointIdsList
        client = await self._get_client()
        await client.delete(
            collection_name=self._collection,
            points_selector=PointIdsList(points=point_ids),
        )

    # ── Health check ──────────────────────────────────────────────────────

    async def ping(self) -> bool:
        """Return True when Qdrant is reachable (used by /ready endpoint)."""
        try:
            client = await self._get_client()
            await client.get_collections()
            return True
        except Exception as exc:
            logger.warning("qdrant_ping_failed", error=str(exc))
            return False

    # ── Scroll (admin / eval) ─────────────────────────────────────────────

    async def scroll_dataset(
        self,
        dataset_id: str,
        limit: int = 100,
        offset: str | None = None,
    ) -> tuple[list[dict], str | None]:
        """Page through all chunks for a dataset.

        Returns:
            Tuple of (list of point dicts, next_offset).
            ``next_offset`` is None when the final page has been reached.

        Used by the eval runner to inspect indexed chunks for a dataset.
        """
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        client  = await self._get_client()
        results, next_page_offset = await client.scroll(
            collection_name=self._collection,
            scroll_filter=Filter(
                must=[FieldCondition(key="dataset_id", match=MatchValue(value=dataset_id))]
            ),
            limit=limit,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        points = [
            {"id": str(r.id), "payload": r.payload or {}}
            for r in results
        ]
        return points, str(next_page_offset) if next_page_offset else None


@lru_cache(maxsize=1)
def get_qdrant_adapter() -> QdrantAdapter:
    """Return the cached QdrantAdapter singleton.

    Call ``get_qdrant_adapter.cache_clear()`` in tests that need a fresh adapter.
    """
    return QdrantAdapter()
