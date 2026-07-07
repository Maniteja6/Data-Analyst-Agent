"""DataPilot Agent System — 19-agent pipeline for real-time data analytics.

Package structure
-----------------
agents/
├── base/           — BaseAgent, AgentContext, AgentResult, ToolRegistry
├── control/        — PlannerAgent, OrchestratorAgent, IntentAgent, MemoryAgent
├── data/           — SchemaAgent, ProfilingAgent, RAGAgent
├── analysis/       — SQLAgent, PythonAgent, ForecastAgent, MLAgent, VisualizationAgent
├── output/         — InsightAgent, RecommendationAgent, ReportAgent
└── quality/        — CriticAgent, SecurityAgent, ValidationAgent, MonitoringAgent

Real-time architecture
----------------------
Every agent in this package is designed for the WebSocket-first, real-time
application model:

1. STREAMING TOKENS — NarrativeGenerator streams executive summary tokens
   token-by-token via ``context.push_token()`` so users see the AI response
   as it's generated, not after a multi-second wait.

2. PROGRESSIVE REVEAL — InsightAgent and RecommendationAgent emit one
   Socket.IO event per insight/recommendation as they're generated, so
   the frontend renders cards one-by-one rather than all at once.

3. LIVE PIPELINE PROGRESS — DAGExecutor emits ``job:progress`` and
   ``agent:complete`` events after each wave of agents, driving a real-time
   pipeline topology diagram in the browser.

4. PER-COLUMN EVENTS — SchemaAgent and ProfilingAgent emit
   ``schema:column_classified`` and ``profiling:column_complete`` events
   for each column as it's processed, enabling live-updating data tables.

5. SECURE STREAMING — SecurityAgent gates every chat message before any
   LLM call and emits ``security:cleared`` / ``security:blocked`` events to
   the conversation room (private to the requesting client).

6. INCREMENTAL INDEXING — RAGAgent emits ``rag:chunk_indexed`` every 10
   chunks during vector store indexing so users see "Knowledge base: 45/120
   chunks indexed" progress.

Agent registry
--------------
``build_agent_registry()`` returns the dict used by OrchestratorAgent and
DAGExecutor. Call it once during application startup and pass the result to
``OrchestratorAgent(agent_registry=...)``.

Dependency injection ensures every agent receives its LLM client, storage
adapter, and Socket.IO server reference without singletons or global state.

Usage (in Celery task or FastAPI route)::

    from backend.agents import build_agent_registry
    from backend.agents.control.orchestrator.orchestrator_agent import OrchestratorAgent
    from backend.agents.base.agent_context import AgentContext

    registry      = build_agent_registry(llm_client=llm, sio=sio)
    orchestrator  = OrchestratorAgent(agent_registry=registry)
    context       = AgentContext(
        session_id=session_id,
        dataset_id=dataset_id,
        correlation_id=correlation_id,
        storage_key=storage_key,
        _sio=sio,
    )
    plan   = await planner.run(context)
    result = await orchestrator.run(context, plan=plan)

Socket.IO room conventions
--------------------------
dataset:<id>          — pipeline progress, agent events, analysis.complete
conversation:<id>     — chat tokens, security events, validation events (private)
monitoring:<id>       — admin performance dashboard events
job:<job_id>          — job status for polling clients

All agents respect these conventions and never emit private events to the
wrong room.
"""
from __future__ import annotations

from typing import Any

__version__ = "1.0.0"

__all__ = [
    "build_agent_registry",
    "get_agent",
]


def build_agent_registry(
    llm_client: Any = None,
    stream_client: Any = None,
    storage: Any = None,
    embed_service: Any = None,
    qdrant: Any = None,
    redis_client: Any = None,
    sio: Any = None,
) -> dict[str, Any]:
    """Build the complete agent registry for OrchestratorAgent / DAGExecutor.

    Creates one instance of each agent with the provided infrastructure
    dependencies. All agents are lazy-initialised where possible — heavy
    dependencies (boto3 Bedrock client, Qdrant connection) are only created
    when the first request arrives.

    Args:
        llm_client:    Async LLM client for batch completions (Claude Sonnet/Haiku).
                       When None, agents use MockLLMService (safe for tests).
        stream_client: BedrockStreamAdapter for token-by-token streaming.
                       Used by NarrativeGenerator for executive summary streaming.
                       Falls back to llm_client when None.
        storage:       IStorageService (S3 or LocalStorageAdapter).
                       Used by ReportAgent for PDF/XLSX/PPTX uploads.
        embed_service: BedrockEmbeddingService for RAG vector embeddings.
        qdrant:        QdrantAdapter for vector store operations.
        redis_client:  Redis/InMemoryCacheAdapter for MemoryAgent episodic store.
        sio:           Socket.IO AsyncServer for real-time event emission.
                       When None, all push_progress() / push_token() calls are no-ops.

    Returns:
        Dict mapping agent name string → agent instance.
        Keys match AgentName enum values in plan_schema.py.
    """
    # ── Control agents ────────────────────────────────────────────────────
    from backend.agents.analysis.forecast.forecast_agent import ForecastAgent
    from backend.agents.analysis.ml.ml_agent import MLAgent
    from backend.agents.analysis.python.python_agent import PythonAgent

    # ── Analysis agents ───────────────────────────────────────────────────
    from backend.agents.analysis.sql.sql_agent import SQLAgent
    from backend.agents.analysis.visualization.visualization_agent import VisualizationAgent
    from backend.agents.control.intent.intent_agent import IntentAgent
    from backend.agents.control.memory.memory_agent import MemoryAgent
    from backend.agents.control.orchestrator.orchestrator_agent import OrchestratorAgent
    from backend.agents.control.planner.planner_agent import PlannerAgent
    from backend.agents.data.profiling.profiling_agent import ProfilingAgent
    from backend.agents.data.rag.rag_agent import RAGAgent

    # ── Data agents ───────────────────────────────────────────────────────
    from backend.agents.data.schema.schema_agent import SchemaAgent

    # ── Output agents ─────────────────────────────────────────────────────
    from backend.agents.output.insight.insight_agent import InsightAgent
    from backend.agents.output.recommendation.recommendation_agent import RecommendationAgent
    from backend.agents.output.report.report_agent import ReportAgent

    # ── Quality agents ────────────────────────────────────────────────────
    from backend.agents.quality.critic.critic_agent import CriticAgent
    from backend.agents.quality.monitoring.monitoring_agent import MonitoringAgent
    from backend.agents.quality.security.security_agent import SecurityAgent
    from backend.agents.quality.validation.validation_agent import ValidationAgent

    registry = {
        # ── Control ───────────────────────────────────────────────────────
        "planner":        PlannerAgent(llm_client=llm_client),
        "orchestrator":   OrchestratorAgent(agent_registry={}),   # self-reference filled below
        "intent":         IntentAgent(llm_client=llm_client),
        "memory":         MemoryAgent(llm_client=llm_client, redis_client=redis_client),

        # ── Data ──────────────────────────────────────────────────────────
        "schema":         SchemaAgent(llm_client=llm_client),
        "profiling":      ProfilingAgent(),
        "rag":            RAGAgent(
                              llm_client=llm_client,
                              embed_service=embed_service,
                              qdrant=qdrant,
                          ),

        # ── Analysis ──────────────────────────────────────────────────────
        "sql":            SQLAgent(llm_client=llm_client),
        "python":         PythonAgent(llm_client=llm_client),
        "forecast":       ForecastAgent(llm_client=llm_client),
        "ml":             MLAgent(llm_client=llm_client),
        "visualization":  VisualizationAgent(llm_client=llm_client),

        # ── Output ────────────────────────────────────────────────────────
        "insight":        InsightAgent(
                              llm_client=llm_client,
                              stream_client=stream_client,
                          ),
        "recommendation": RecommendationAgent(llm_client=llm_client),
        "report":         ReportAgent(storage=storage, llm_client=llm_client),

        # ── Quality ───────────────────────────────────────────────────────
        "critic":         CriticAgent(llm_client=llm_client),
        "security":       SecurityAgent(llm_client=llm_client),
        "validation":     ValidationAgent(llm_client=llm_client),
        "monitoring":     MonitoringAgent(),
    }

    # Wire OrchestratorAgent's registry back to the full dict so it can
    # call sub-agents by name in nested invocations
    registry["orchestrator"]._executor._registry = registry

    return registry


def get_agent(name: str, registry: dict[str, Any]) -> Any:
    """Retrieve an agent from a registry by name.

    Args:
        name:     Agent name (e.g. ``'sql'``, ``'insight'``).
        registry: Dict returned by ``build_agent_registry()``.

    Returns:
        Agent instance.

    Raises:
        KeyError: When the agent name is not in the registry.
    """
    agent = registry.get(name)
    if agent is None:
        available = sorted(registry.keys())
        raise KeyError(
            f"Agent '{name}' not found in registry. "
            f"Available agents: {available}"
        )
    return agent


def list_agents(registry: dict[str, Any]) -> list[str]:
    """Return a sorted list of agent names in the registry."""
    return sorted(registry.keys())
