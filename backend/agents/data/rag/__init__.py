"""Agent sub-package."""
"""RAG agent — vector store indexing and real-time context retrieval.

Index mode:   ChunkBuilder → BedrockEmbeddingService (concurrent, semaphore=4)
              → QdrantAdapter.upsert(); emits rag:chunk_indexed every 10 chunks.
Retrieval:    HyDEExpander → embed → QdrantAdapter.search() → BM25 rerank.
Target:       embed + search + rerank < 100ms on the WebSocket hot path.
"""
from backend.agents.data.rag.rag_agent     import RAGAgent
from backend.agents.data.rag.chunk_builder import ChunkBuilder, DataChunk
from backend.agents.data.rag.hyde_expander import HyDEExpander
from backend.agents.data.rag.retriever     import Retriever

__all__ = ["RAGAgent", "ChunkBuilder", "DataChunk", "HyDEExpander", "Retriever"]
