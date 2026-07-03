"""CollectionManager — manages Qdrant collection lifecycle and chunk indexing.

Provides a higher-level interface on top of ``QdrantAdapter`` for the
application layer. The ``RAGAgent`` calls this service to index a dataset
after profiling and to clean up stale chunks before re-indexing.

Responsibilities:
1. **Initialise** — create the collection on startup if it doesn't exist.
2. **Index dataset** — build chunk texts from a DataProfile and upsert embeddings.
3. **Reindex dataset** — delete stale chunks then re-index fresh ones.
4. **Delete dataset** — remove all chunks when a dataset is deleted.
5. **Stats** — report point counts per dataset for monitoring.

Chunk construction strategy:
    One chunk per column (``column_description``) + one summary chunk per dataset
    (``profile_summary``). For datasets with > 200 columns, only columns with
    null_rate < 0.5 or semantic_type in ('currency', 'datetime', 'categorical')
    are indexed to keep Qdrant memory bounded.

Usage::

    from backend.infrastructure.vector_store.collection_manager import CollectionManager

    manager = CollectionManager()
    await manager.initialise()
    indexed = await manager.index_dataset(dataset_id="abc-123", profile=data_profile)
    print(f"Indexed {indexed} chunks for dataset abc-123")
"""
from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Maximum columns indexed per dataset to bound Qdrant memory usage
MAX_COLUMNS_PER_DATASET = 300


class CollectionManager:
    """High-level collection lifecycle and chunk indexing manager."""

    def __init__(
        self,
        qdrant_adapter=None,
        embedding_service=None,
    ) -> None:
        """
        Args:
            qdrant_adapter:    ``QdrantAdapter`` instance (or None for singleton).
            embedding_service: ``BedrockEmbeddingService`` instance (or None for singleton).
        """
        self._qdrant = qdrant_adapter
        self._embed  = embedding_service

    def _get_qdrant(self):
        if self._qdrant is None:
            from backend.infrastructure.vector_store.qdrant_adapter import get_qdrant_adapter
            self._qdrant = get_qdrant_adapter()
        return self._qdrant

    def _get_embed(self):
        if self._embed is None:
            from backend.infrastructure.vector_store.bedrock_embedding_service import get_embedding_service
            self._embed = get_embedding_service()
        return self._embed

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def initialise(self) -> None:
        """Create the Qdrant collection if it does not exist.

        Called once per process in the FastAPI lifespan handler when
        ``FEATURE_RAG`` is enabled. Safe to call multiple times.
        """
        qdrant = self._get_qdrant()
        await qdrant.ensure_collection()
        logger.info("collection_manager_initialised")

    async def drop_and_recreate(self) -> None:
        """Destroy and recreate the collection — use only in development.

        Useful when the embedding model dimension changes (e.g. 1536 → 512)
        or when bulk-reindexing all datasets from scratch.
        """
        qdrant = self._get_qdrant()
        await qdrant.delete_collection()
        await qdrant.ensure_collection()
        logger.warning("collection_dropped_and_recreated")

    # ── Indexing ──────────────────────────────────────────────────────────

    async def index_dataset(
        self,
        dataset_id: str,
        profile: Any,
        project_id: str = "",
        schema: dict | None = None,
    ) -> int:
        """Embed and index a dataset profile into Qdrant.

        Builds chunk texts from the ``DataProfile`` entity, embeds them in
        parallel using ``BedrockEmbeddingService``, and upserts the resulting
        vectors into Qdrant.

        Args:
            dataset_id: Source dataset UUID.
            profile:    ``DataProfile`` entity (or dict-like with ``column_profiles``).
            project_id: Optional project UUID stored in the payload for scoped queries.
            schema:     Optional schema dict (``Dataset.schema_json``) for additional
                        column metadata (semantic_type, data_type).

        Returns:
            Number of chunks indexed.
        """
        from backend.config.feature_flags import flags
        if not flags.rag_enabled:
            logger.debug("rag_indexing_skipped", reason="FEATURE_RAG disabled")
            return 0

        chunks = self._build_chunks(dataset_id, profile, project_id, schema)
        if not chunks:
            logger.warning("no_chunks_to_index", dataset_id=dataset_id)
            return 0

        # Embed all chunk texts in parallel
        embed  = self._get_embed()
        texts  = [c["content"] for c in chunks]
        vectors = await embed.embed_batch(texts, concurrency=4)

        # Build Qdrant points
        from backend.shared.utils.uuid_factory import new_uuid
        points = [
            {
                "id":      new_uuid(),
                "vector":  vectors[i],
                "payload": {
                    "dataset_id":  dataset_id,
                    "project_id":  project_id,
                    "chunk_type":  chunks[i]["chunk_type"],
                    "column_name": chunks[i].get("column_name"),
                    "content":     chunks[i]["content"],
                    "metadata":    chunks[i].get("metadata", {}),
                },
            }
            for i in range(len(chunks))
        ]

        qdrant = self._get_qdrant()
        await qdrant.upsert(points)
        logger.info("dataset_indexed", dataset_id=dataset_id, chunks=len(points))
        return len(points)

    async def reindex_dataset(
        self,
        dataset_id: str,
        profile: Any,
        project_id: str = "",
        schema: dict | None = None,
    ) -> int:
        """Delete stale chunks and re-index with fresh embeddings.

        Called after a dataset is re-analysed with an updated profile.
        """
        qdrant = self._get_qdrant()
        await qdrant.delete_by_dataset(dataset_id)
        logger.info("stale_chunks_deleted", dataset_id=dataset_id)
        return await self.index_dataset(dataset_id, profile, project_id, schema)

    # ── Deletion ──────────────────────────────────────────────────────────

    async def delete_dataset_chunks(self, dataset_id: str) -> None:
        """Remove all indexed chunks for a dataset.

        Called when a dataset is soft-deleted or a GDPR erasure request is processed.
        """
        qdrant = self._get_qdrant()
        await qdrant.delete_by_dataset(dataset_id)
        logger.info("dataset_chunks_deleted", dataset_id=dataset_id)

    # ── Stats ─────────────────────────────────────────────────────────────

    async def dataset_chunk_count(self, dataset_id: str) -> int:
        """Return the number of indexed chunks for a dataset.

        Used by the eval runner and the admin monitoring dashboard.
        """
        qdrant  = self._get_qdrant()
        results = await qdrant.scroll_dataset(dataset_id, limit=1000)
        return len(results[0])

    async def collection_stats(self) -> dict:
        """Return overall collection statistics."""
        qdrant = self._get_qdrant()
        return await qdrant.collection_info()

    # ── Chunk construction ────────────────────────────────────────────────

    def _build_chunks(
        self,
        dataset_id: str,
        profile: Any,
        project_id: str,
        schema: dict | None,
    ) -> list[dict]:
        """Convert a DataProfile into indexable text chunks.

        Strategy:
        - One ``column_description`` chunk per column, containing column name,
          data type, semantic type, null rate, unique count, and sample values.
        - One ``profile_summary`` chunk per dataset with overall quality metrics.
        - Columns with > 50% null rate are skipped (too sparse to be useful for RAG).
        - At most ``MAX_COLUMNS_PER_DATASET`` column chunks per dataset.

        Returns:
            List of chunk dicts with ``chunk_type``, ``content``, and ``column_name``.
        """
        chunks: list[dict] = []
        col_profiles = getattr(profile, "column_profiles", []) or []

        # Build schema lookup for type enrichment
        schema_cols: dict[str, dict] = {}
        if schema:
            for col in schema.get("columns", []):
                schema_cols[col.get("name", "")] = col

        # Column description chunks
        indexed = 0
        for col in col_profiles:
            if indexed >= MAX_COLUMNS_PER_DATASET:
                break

            col_name  = getattr(col, "column_name", None) or col.get("column_name", "")
            null_rate = float(getattr(col, "null_rate", 0.0) or col.get("null_rate", 0.0))
            if null_rate > 0.5:
                continue   # skip very sparse columns

            data_type     = str(getattr(col, "data_type",   None) or col.get("data_type", "unknown"))
            semantic_type = str(getattr(col, "semantic_type", None) or col.get("semantic_type", "unknown"))
            if hasattr(semantic_type, "value"):
                semantic_type = semantic_type
            unique_count  = int(getattr(col, "unique_count", 0) or col.get("unique_count", 0))
            sample_vals   = getattr(col, "sample_values", []) or col.get("sample_values", [])

            # Enrich with schema metadata
            schema_meta = schema_cols.get(col_name, {})

            text = (
                f"Column: {col_name}\n"
                f"Data type: {data_type}\n"
                f"Semantic type: {semantic_type}\n"
                f"Null rate: {null_rate * 100:.1f}%\n"
                f"Unique values: {unique_count}\n"
                f"Sample values: {', '.join(str(v) for v in sample_vals[:5])}"
            )
            if schema_meta.get("is_primary_key"):
                text += "\nRole: Primary key / identifier"

            chunks.append({
                "chunk_type":  "column_description",
                "column_name": col_name,
                "content":     text,
                "metadata": {
                    "data_type":     data_type,
                    "semantic_type": semantic_type,
                    "null_rate":     null_rate,
                    "unique_count":  unique_count,
                },
            })
            indexed += 1

        # Profile summary chunk
        row_count    = getattr(profile, "row_count",          None) or 0
        col_count    = getattr(profile, "column_count",       None) or 0
        completeness = getattr(profile, "completeness_score", None) or 1.0
        consistency  = getattr(profile, "consistency_score",  None) or 1.0
        duplicates   = getattr(profile, "duplicate_count",    None) or 0

        summary_text = (
            f"Dataset overview:\n"
            f"Total rows: {row_count:,}\n"
            f"Total columns: {col_count}\n"
            f"Completeness score: {completeness * 100:.1f}%\n"
            f"Consistency score: {consistency * 100:.1f}%\n"
            f"Duplicate rows removed: {duplicates:,}\n"
            f"Columns indexed: {indexed} of {len(col_profiles)}"
        )
        chunks.append({
            "chunk_type":  "profile_summary",
            "column_name": None,
            "content":     summary_text,
            "metadata": {
                "row_count":          row_count,
                "column_count":       col_count,
                "completeness_score": completeness,
            },
        })

        return chunks
