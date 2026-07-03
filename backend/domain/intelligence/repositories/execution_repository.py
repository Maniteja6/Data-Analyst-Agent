"""ExecutionRepository — abstract port for ExecutionPlan and AgentResult persistence."""
from __future__ import annotations

from abc import abstractmethod

from backend.shared.repository import Repository
from backend.domain.intelligence.entities.execution_plan import ExecutionPlan, PlanStatus
from backend.domain.intelligence.entities.agent_result import AgentResult


class ExecutionPlanRepository(Repository[ExecutionPlan, str]):
    """Abstract repository for ExecutionPlan aggregates.

    Concrete implementation:
    ``backend/infrastructure/persistence/repositories/postgres_session_repository.py``
    (Execution plans share the session table; a dedicated table is added in migration 004.)
    """

    @abstractmethod
    async def get_by_id(self, entity_id: str) -> ExecutionPlan | None:
        """Return an ExecutionPlan by its UUID."""

    @abstractmethod
    async def save(self, entity: ExecutionPlan) -> ExecutionPlan:
        """Insert or update an ExecutionPlan and all its TaskNodes."""

    @abstractmethod
    async def delete(self, entity_id: str) -> None:
        """Delete an ExecutionPlan and cascade to its TaskNodes."""

    @abstractmethod
    async def get_by_session_id(self, session_id: str) -> ExecutionPlan | None:
        """Return the ExecutionPlan for a given AnalysisSession."""

    @abstractmethod
    async def get_by_status(self, status: PlanStatus) -> list[ExecutionPlan]:
        """Return all plans in a given status — used by the monitoring worker
        to detect and recover stuck RUNNING plans.
        """

    @abstractmethod
    async def get_running_plans_older_than(self, minutes: int) -> list[ExecutionPlan]:
        """Return RUNNING plans that have been running for longer than ``minutes``.

        Used by the watchdog to detect and recover stalled pipelines.
        """


class AgentResultRepository(Repository[AgentResult, str]):
    """Abstract repository for AgentResult entities.

    Concrete implementation writes to the ``agent_executions`` table.
    Results older than 30 days are archived to S3 via a lifecycle rule.
    """

    @abstractmethod
    async def get_by_id(self, entity_id: str) -> AgentResult | None:
        """Return an AgentResult by its UUID."""

    @abstractmethod
    async def save(self, entity: AgentResult) -> AgentResult:
        """Insert an AgentResult (AgentResults are immutable; no update needed)."""

    @abstractmethod
    async def delete(self, entity_id: str) -> None:
        """Hard-delete an AgentResult (GDPR data erasure)."""

    @abstractmethod
    async def get_by_session(self, session_id: str) -> list[AgentResult]:
        """Return all AgentResults for a session, ordered by created_at."""

    @abstractmethod
    async def get_by_agent_and_input_hash(
        self, agent_name: str, input_hash: str
    ) -> AgentResult | None:
        """Look up a cached AgentResult by (agent_name, input_hash).

        Used by the LLM response cache to serve repeated identical queries
        without calling Bedrock again.
        """

    @abstractmethod
    async def get_failed_by_session(self, session_id: str) -> list[AgentResult]:
        """Return only the failed AgentResults for a session — used in error reports."""
