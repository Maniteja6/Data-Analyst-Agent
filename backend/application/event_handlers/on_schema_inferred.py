"""on_schema_inferred — triggers async RAG indexing of the schema chunks."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from backend.config.feature_flags import flags

if TYPE_CHECKING:
    from backend.infrastructure.vector_store.collection_manager import CollectionManager

logger = structlog.get_logger(__name__)


async def on_schema_inferred(
    event: dict, collection_manager: CollectionManager | None = None
) -> None:
    """Trigger async RAG indexing of schema columns.

    Called when the Schema Agent completes column type inference. Indexing
    runs asynchronously so it does not block the main profiling pipeline.
    The schema chunks will be available for chat queries before profiling
    fully completes.

    Args:
        event:              SchemaInferred.to_dict() payload.
        collection_manager: CollectionManager instance (or None to use singleton).
    """
    if not flags.rag_enabled:
        return

    dataset_id = event.get("dataset_id", "")
    if not dataset_id:
        return

    try:
        if collection_manager is None:
            from backend.infrastructure.vector_store.collection_manager import CollectionManager

            collection_manager = CollectionManager()

        # Schema-only indexing — profile is not yet available
        # Pass a minimal profile-like object with just the schema columns
        class _MinimalProfile:
            column_profiles: list = []
            row_count = event.get("row_count", 0)
            column_count = event.get("column_count", 0)
            completeness_score = 1.0

        await collection_manager.index_dataset(dataset_id, _MinimalProfile())
        logger.info("on_schema_inferred_rag_indexed", dataset_id=dataset_id)

    except Exception as exc:
        logger.warning("on_schema_inferred_rag_failed", dataset_id=dataset_id, error=str(exc))
