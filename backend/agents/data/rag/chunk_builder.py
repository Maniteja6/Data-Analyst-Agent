"""ChunkBuilder — builds searchable text chunks from dataset metadata.

Real-time design:
    Chunk building is CPU-bound and runs in a thread pool so it doesn't
    block the event loop. After each batch of chunks is indexed, the agent
    emits a ``rag:chunks_indexed`` Socket.IO event so the frontend can
    show a "Knowledge base building…" progress indicator.

Chunk types:
    column_description — one chunk per column: name, type, null rate, samples
    profile_summary    — one chunk for the full dataset profile
    insight_chunk      — one chunk per generated insight (indexed post-analysis)
    correlation_chunk  — one chunk per significant pairwise correlation

Chunking strategy:
    Each chunk is sized to fit within Titan Embed v2's 8,192 token limit.
    Column description chunks are ~50-80 tokens. Profile summaries are ~200 tokens.
    HyDE expansion during retrieval adds context so chunks can be compact.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog
from backend.shared.utils.uuid_factory import new_uuid

logger = structlog.get_logger(__name__)


@dataclass
class DataChunk:
    """One unit of text to be embedded and stored in Qdrant."""
    id:           str
    dataset_id:   str
    chunk_type:   str           # column_description | profile_summary | insight | correlation
    content:      str           # text that will be embedded
    column_name:  str | None = None
    metadata:     dict[str, Any] = field(default_factory=dict)


class ChunkBuilder:
    """Builds DataChunk objects from schema, profile, and insight data."""

    # ── Schema chunks ─────────────────────────────────────────────────────

    def build_schema_chunks(
        self,
        dataset_id: str,
        schema: dict,
    ) -> list[DataChunk]:
        """Build one chunk per column from the schema dict.

        Each chunk includes the column name, semantic type, null rate,
        unique count, and sample values. This is enough for RAG to answer
        questions like "what columns contain dates?" or "which column has
        the most missing values?".
        """
        chunks = []
        for col in schema.get("columns", []):
            content = (
                f"Column: {col['name']}\n"
                f"Type: {col.get('data_type', 'unknown')} "
                f"(semantic: {col.get('semantic_type', 'unknown')})\n"
                f"Null rate: {col.get('null_rate', 0) * 100:.1f}%\n"
                f"Unique values: {col.get('unique_count', 0)}\n"
                f"Sample values: {col.get('sample_values', [])[:5]}\n"
                f"Is primary key: {col.get('is_primary_key', False)}"
            )
            chunks.append(DataChunk(
                id=new_uuid(),
                dataset_id=dataset_id,
                chunk_type="column_description",
                content=content,
                column_name=col["name"],
                metadata={
                    "semantic_type": col.get("semantic_type"),
                    "null_rate":     col.get("null_rate"),
                    "unique_count":  col.get("unique_count"),
                },
            ))

        logger.debug("schema_chunks_built", dataset_id=dataset_id, count=len(chunks))
        return chunks

    # ── Profile chunks ────────────────────────────────────────────────────

    def build_profile_chunks(
        self,
        dataset_id: str,
        profile: dict,
    ) -> list[DataChunk]:
        """Build a summary chunk from the DataProfile dict.

        Returns a single chunk containing dataset-level statistics that
        RAG can use to answer questions like "how many rows does the dataset
        have?" or "what is the completeness score?".
        """
        content = (
            f"Dataset profile summary:\n"
            f"Total rows: {profile.get('row_count', 'unknown')}\n"
            f"Total columns: {profile.get('column_count', 'unknown')}\n"
            f"Completeness score: {profile.get('completeness_score', 0):.1%}\n"
            f"Consistency score: {profile.get('consistency_score', 0):.1%}\n"
            f"Duplicate rows: {profile.get('duplicate_count', 0)}\n"
            f"Has time series: {profile.get('has_time_series', False)}"
        )
        chunks = [DataChunk(
            id=new_uuid(),
            dataset_id=dataset_id,
            chunk_type="profile_summary",
            content=content,
            metadata={
                "row_count":         profile.get("row_count"),
                "completeness_score": profile.get("completeness_score"),
            },
        )]

        # One chunk per numeric column with statistics
        for col_profile in profile.get("column_profiles", []):
            stats = col_profile.get("stats") or {}
            if not stats:
                continue
            content = (
                f"Statistics for column '{col_profile.get('column_name')}':\n"
                f"Mean: {stats.get('mean')}\n"
                f"Std dev: {stats.get('stddev')}\n"
                f"Min: {stats.get('min_val')}, Max: {stats.get('max_val')}\n"
                f"Median (P50): {stats.get('p50')}\n"
                f"Skewness: {stats.get('skewness')}"
            )
            chunks.append(DataChunk(
                id=new_uuid(),
                dataset_id=dataset_id,
                chunk_type="column_statistics",
                content=content,
                column_name=col_profile.get("column_name"),
                metadata={"stats": stats},
            ))

        logger.debug("profile_chunks_built", dataset_id=dataset_id, count=len(chunks))
        return chunks

    # ── Insight chunks ────────────────────────────────────────────────────

    def build_insight_chunks(
        self,
        dataset_id: str,
        insights: list[dict],
    ) -> list[DataChunk]:
        """Build one chunk per insight for post-analysis RAG queries."""
        chunks = []
        for insight in insights:
            content = (
                f"Insight: {insight.get('headline', '')}\n"
                f"{insight.get('explanation', '')}\n"
                f"Business impact: {insight.get('business_impact', 'unknown')}\n"
                f"Related columns: {insight.get('source_columns', [])}"
            )
            chunks.append(DataChunk(
                id=new_uuid(),
                dataset_id=dataset_id,
                chunk_type="insight",
                content=content,
                metadata={
                    "business_impact": insight.get("business_impact"),
                    "confidence":      insight.get("confidence"),
                },
            ))
        return chunks

    # ── Correlation chunks ────────────────────────────────────────────────

    def build_correlation_chunks(
        self,
        dataset_id: str,
        correlations: list[dict],
    ) -> list[DataChunk]:
        """Build chunks for pairwise correlations (strong correlations only)."""
        chunks = []
        for corr in correlations:
            if abs(corr.get("r", 0)) < 0.5:
                continue   # skip weak correlations
            direction = "positive" if corr.get("r", 0) > 0 else "negative"
            content = (
                f"Correlation: '{corr.get('column_a')}' and '{corr.get('column_b')}' "
                f"have a {corr.get('strength', '')} {direction} correlation "
                f"(r = {corr.get('r', 0):.3f})."
            )
            chunks.append(DataChunk(
                id=new_uuid(),
                dataset_id=dataset_id,
                chunk_type="correlation",
                content=content,
                metadata={"r": corr.get("r"), "strength": corr.get("strength")},
            ))
        return chunks

    def to_qdrant_dicts(self, chunks: list[DataChunk]) -> list[dict]:
        """Convert DataChunk objects to Qdrant point dicts (ready for upsert)."""
        return [
            {
                "id":         chunk.id,
                "dataset_id": chunk.dataset_id,
                "chunk_type": chunk.chunk_type,
                "content":    chunk.content,
                "column_name": chunk.column_name,
                "payload":    {
                    "content":     chunk.content,
                    "chunk_type":  chunk.chunk_type,
                    "column_name": chunk.column_name,
                    **chunk.metadata,
                },
            }
            for chunk in chunks
        ]
