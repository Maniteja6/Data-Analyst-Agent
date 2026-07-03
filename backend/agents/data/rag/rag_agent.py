"""RAGAgent — vector store indexing and real-time context retrieval.

Real-time pipeline (two modes):

MODE 1 — INDEXING (runs once, triggered by ``schema:complete`` event):
    1. Build column + profile chunks via ChunkBuilder
    2. Embed each chunk via BedrockEmbeddingService (Titan Embed v2)
    3. Upsert all vectors into Qdrant
    4. Emit ``rag:indexed`` Socket.IO event when complete

MODE 2 — RETRIEVAL (runs on every chat message):
    1. Apply HyDE expansion (optional, adds ~200ms but improves quality)
    2. Embed the expanded query via Titan Embed v2 (~80ms)
    3. Search Qdrant with BM25-lite re-ranking (~10ms)
    4. Return the context string for the system prompt

Concurrent indexing:
    Chunks are embedded concurrently using asyncio.gather with a semaphore
    (max_concurrent=4) to stay within Bedrock rate limits while processing
    wide datasets (50+ columns) quickly.

Socket.IO events emitted:
    rag:indexing_start   — "Indexing N chunks…"
    rag:chunk_indexed    — emitted every 10 chunks for progress feedback
    rag:indexed          — final count of indexed chunks
    rag:retrieval_start  — "Searching knowledge base…"
"""
from __future__ import annotations

import asyncio
from typing import Any

import structlog

from backend.agents.base.base_agent import BaseAgent
from backend.agents.base.agent_context import AgentContext
from backend.agents.data.rag.chunk_builder import ChunkBuilder, DataChunk
from backend.agents.data.rag.hyde_expander  import HyDEExpander
from backend.agents.data.rag.retriever       import Retriever

logger = structlog.get_logger(__name__)

MAX_CONCURRENT_EMBEDS = 4    # Bedrock concurrency limit


class RAGAgent(BaseAgent):
    """Indexes dataset knowledge and retrieves context for chat queries.

    Args:
        llm_client:    LLM client for HyDE expansion (Haiku).
        embed_service: Embedding service (Titan Embed v2).
        qdrant:        Qdrant vector store adapter.
    """

    def __init__(
        self,
        llm_client=None,
        embed_service=None,
        qdrant=None,
    ) -> None:
        super().__init__("rag")
        self._builder  = ChunkBuilder()
        self._hyde     = HyDEExpander(llm_client)
        self._retriever = Retriever(qdrant, embed_service)

        # Lazy-initialised
        self._embed  = embed_service
        self._qdrant = qdrant

    async def _execute(
        self,
        context: AgentContext,
        query: str = "",
        index_dataset: bool = False,
        top_k: int = 8,
        use_hyde: bool = True,
        **kwargs: Any,
    ) -> dict:
        """Route to indexing or retrieval based on ``index_dataset`` flag.

        Args:
            context:       Shared pipeline state.
            query:         User question (for retrieval mode).
            index_dataset: When True, index the dataset into Qdrant.
            top_k:         Number of chunks to retrieve.
            use_hyde:      Whether to apply HyDE query expansion.

        Returns:
            Indexing: ``{"indexed": True, "chunk_count": N}``
            Retrieval: ``{"context": str, "retrieved_chunks": N, "scores": [float]}``
        """
        if index_dataset:
            return await self._index_dataset(context)
        return await self._retrieve(context, query, top_k, use_hyde)

    # ── Mode 1: Indexing ──────────────────────────────────────────────────

    async def _index_dataset(self, context: AgentContext) -> dict:
        """Build and upsert all dataset chunks into Qdrant."""
        sio        = context._sio
        dataset_id = context.dataset_id

        # Build chunks from schema and profile
        chunks: list[DataChunk] = []
        if context.schema:
            chunks.extend(self._builder.build_schema_chunks(dataset_id, context.schema))
        if context.profile:
            chunks.extend(self._builder.build_profile_chunks(dataset_id, context.profile))

        total = len(chunks)
        if total == 0:
            logger.warning("rag_index_no_chunks", dataset_id=dataset_id)
            return {"indexed": True, "chunk_count": 0}

        # Emit start event
        if sio and dataset_id:
            try:
                await sio.emit(
                    "rag:indexing_start",
                    {"dataset_id": dataset_id, "chunk_count": total},
                    room=f"dataset:{dataset_id}",
                )
            except Exception:
                pass

        await context.push_progress(
            15, f"Indexing {total} knowledge base chunks…", step="rag"
        )

        # Embed all chunks concurrently (rate-limited)
        embed_svc = await self._get_embed()
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_EMBEDS)
        indexed   = 0

        async def _embed_and_track(chunk: DataChunk) -> dict:
            nonlocal indexed
            async with semaphore:
                vector = await embed_svc.embed(chunk.content)
                result = {
                    "id":          chunk.id,
                    "dataset_id":  chunk.dataset_id,
                    "chunk_type":  chunk.chunk_type,
                    "column_name": chunk.column_name,
                    "content":     chunk.content,
                    "vector":      vector,
                    "payload":     {
                        "content":     chunk.content,
                        "chunk_type":  chunk.chunk_type,
                        "column_name": chunk.column_name,
                        **chunk.metadata,
                    },
                }
                indexed += 1
                # Emit progress every 10 chunks
                if sio and dataset_id and indexed % 10 == 0:
                    try:
                        await sio.emit(
                            "rag:chunk_indexed",
                            {"dataset_id": dataset_id, "indexed": indexed, "total": total},
                            room=f"dataset:{dataset_id}",
                        )
                    except Exception:
                        pass
                return result

        embedded_chunks = await asyncio.gather(
            *[_embed_and_track(chunk) for chunk in chunks]
        )

        # Upsert to Qdrant
        qdrant = await self._get_qdrant()
        await qdrant.ensure_collection()
        await qdrant.upsert(list(embedded_chunks))

        # Emit complete event
        if sio and dataset_id:
            try:
                await sio.emit(
                    "rag:indexed",
                    {"dataset_id": dataset_id, "chunk_count": total},
                    room=f"dataset:{dataset_id}",
                )
            except Exception:
                pass

        logger.info(
            "rag_indexed",
            dataset_id=dataset_id,
            chunk_count=total,
        )
        return {"indexed": True, "chunk_count": total}

    # ── Mode 2: Retrieval ─────────────────────────────────────────────────

    async def _retrieve(
        self,
        context: AgentContext,
        query: str,
        top_k: int,
        use_hyde: bool,
    ) -> dict:
        """Retrieve relevant chunks for a user query."""
        sio        = context._sio
        dataset_id = context.dataset_id

        if not query:
            return {"context": "", "retrieved_chunks": 0, "scores": []}

        if sio and dataset_id:
            try:
                await sio.emit(
                    "rag:retrieval_start",
                    {"dataset_id": dataset_id, "query": query[:80]},
                    room=f"dataset:{dataset_id}",
                )
            except Exception:
                pass

        # Build schema summary for HyDE context hint
        schema_summary = ""
        if context.schema:
            col_names    = [c["name"] for c in context.schema.get("columns", [])[:10]]
            schema_summary = f"Columns: {', '.join(col_names)}"

        # Apply HyDE expansion
        if use_hyde:
            expanded = await self._hyde.expand(
                query=query,
                schema_summary=schema_summary,
            )
        else:
            expanded = query

        # Retrieve from Qdrant
        results = await self._retriever.retrieve(
            query=expanded,
            dataset_id=dataset_id,
            top_k=top_k,
        )

        context_str = self._retriever.build_context_string(results)
        context.rag_context = context_str

        scores = [round(r.get("score", 0.0), 4) for r in results]
        logger.debug(
            "rag_retrieved",
            dataset_id=dataset_id,
            chunks=len(results),
            top_score=scores[0] if scores else 0.0,
        )

        return {
            "context":          context_str,
            "retrieved_chunks": len(results),
            "scores":           scores,
            "expanded_query":   expanded if expanded != query else None,
        }

    # ── Lazy service initialisation ───────────────────────────────────────

    async def _get_embed(self):
        if self._embed is None:
            from backend.infrastructure.vector_store.bedrock_embedding_service import BedrockEmbeddingService
            self._embed = BedrockEmbeddingService()
        return self._embed

    async def _get_qdrant(self):
        if self._qdrant is None:
            from backend.infrastructure.vector_store.qdrant_adapter import QdrantAdapter
            self._qdrant = QdrantAdapter()
        return self._qdrant
