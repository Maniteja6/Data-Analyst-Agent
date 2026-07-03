"""Intelligence bounded context exceptions."""
from __future__ import annotations

from backend.shared.exceptions import DomainException, AgentException


class IntelligenceException(DomainException):
    """Base exception for the intelligence bounded context."""


class ExecutionPlanNotFoundException(IntelligenceException):
    def __init__(self, plan_id: str) -> None:
        super().__init__(
            f"ExecutionPlan '{plan_id}' not found.",
            code="EXECUTION_PLAN_NOT_FOUND",
        )
        self.plan_id = plan_id


class InvalidExecutionPlanError(IntelligenceException):
    """Raised when a Planner Agent generates an ExecutionPlan with
    invalid task dependencies (e.g. a cycle or missing dependency).
    """

    def __init__(self, plan_id: str, reason: str) -> None:
        super().__init__(
            f"ExecutionPlan '{plan_id}' is invalid: {reason}",
            code="INVALID_EXECUTION_PLAN",
        )
        self.plan_id = plan_id
        self.reason  = reason


class DAGCycleDetectedError(IntelligenceException):
    """Raised when the DAG executor detects a dependency cycle in the plan."""

    def __init__(self, task_ids: list[str]) -> None:
        super().__init__(
            f"Dependency cycle detected among tasks: {task_ids}",
            code="DAG_CYCLE_DETECTED",
        )
        self.task_ids = task_ids


class AgentRegistrationError(IntelligenceException):
    """Raised when an agent name in an ExecutionPlan has no registered
    implementation in the agent registry.
    """

    def __init__(self, agent_name: str) -> None:
        super().__init__(
            f"No agent registered for name '{agent_name}'. "
            "Check the agent_registry in the orchestrator setup.",
            code="AGENT_NOT_REGISTERED",
        )
        self.agent_name = agent_name


class IntentClassificationError(IntelligenceException):
    """Raised when the Intent Agent fails to classify a user message."""

    def __init__(self, message_preview: str) -> None:
        super().__init__(
            f"Intent classification failed for message: '{message_preview[:60]}…'",
            code="INTENT_CLASSIFICATION_FAILED",
        )
        self.message_preview = message_preview


class LLMResponseParsingError(IntelligenceException):
    """Raised when an agent cannot parse the LLM response into the expected schema."""

    def __init__(self, agent_name: str, expected_schema: str, raw_response: str) -> None:
        super().__init__(
            f"Agent '{agent_name}' could not parse LLM response as {expected_schema}. "
            f"Raw (first 200 chars): {raw_response[:200]}",
            code="LLM_RESPONSE_PARSING_FAILED",
        )
        self.agent_name      = agent_name
        self.expected_schema = expected_schema
        self.raw_response    = raw_response


class MaxRetriesExceededError(AgentException):
    """Raised when an agent exhausts all retry attempts."""

    def __init__(self, agent_name: str, attempts: int) -> None:
        super().__init__(
            agent_name,
            f"Exceeded {attempts} retry attempts.",
        )
        self.attempts = attempts
