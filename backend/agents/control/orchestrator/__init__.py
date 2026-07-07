"""DAG orchestrator — executes ExecutionPlan with real-time Socket.IO events.

DAGExecutor:      topological wave execution; asyncio.gather per wave;
                  emits job:progress + agent:complete after each wave.
ResultAggregator: merges AgentResult payloads into AgentContext fields.
OrchestratorAgent:top-level coordinator; emits analysis.complete on finish.
"""

from backend.agents.control.orchestrator.dag_executor import DAGExecutor
from backend.agents.control.orchestrator.orchestrator_agent import OrchestratorAgent
from backend.agents.control.orchestrator.result_aggregator import ResultAggregator

__all__ = ["OrchestratorAgent", "DAGExecutor", "ResultAggregator"]
