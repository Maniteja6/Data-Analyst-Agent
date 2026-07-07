"""Data agents — schema inference, profiling, and RAG indexing/retrieval.

SchemaAgent    — TypeInferencer + SemanticClassifier; per-column Socket.IO events
ProfilingAgent — DataProfiler wrapper; per-column Socket.IO events via threadsafe bridge
RAGAgent       — dual-mode: index dataset chunks OR retrieve context for chat
"""

from backend.agents.data.profiling.profiling_agent import ProfilingAgent
from backend.agents.data.rag.rag_agent import RAGAgent
from backend.agents.data.schema.schema_agent import SchemaAgent

__all__ = ["SchemaAgent", "ProfilingAgent", "RAGAgent"]
