"""PythonAgent — generates and executes analysis code in a secure sandbox.

Used for custom analytics tasks that SQL cannot express easily:
- Multi-step statistical computations (rolling averages, cumulative sums)
- Scipy hypothesis tests
- String pattern analysis
- Custom business logic

The agent generates pandas code via Claude Haiku, validates the imports,
then executes it in a subprocess sandbox with a 60-second timeout.
The ``result`` variable from the sandbox is captured and returned.
"""
from __future__ import annotations

from typing import Any

import structlog

from backend.agents.base.base_agent import BaseAgent
from backend.agents.base.agent_context import AgentContext
from backend.agents.analysis.python.code_generator import generate_code
from backend.agents.analysis.python.sandboxed_executor import execute_code
from backend.agents.analysis.python.output_parser import parse_output, to_markdown

logger = structlog.get_logger(__name__)


class PythonAgent(BaseAgent):
    """Generates sandboxed pandas analysis code and executes it.

    Args:
        llm_client: Async LLM client for code generation (Claude Haiku).
    """

    SANDBOX_TIMEOUT = 60

    def __init__(self, llm_client) -> None:
        super().__init__("python")
        self._llm = llm_client

    async def _execute(
        self,
        context: AgentContext,
        task: str = "",
        **kwargs: Any,
    ) -> dict:
        """Generate and execute a pandas code snippet for the given task.

        Args:
            context: Shared pipeline state (schema, storage_key).
            task:    Natural-language description of the analytics task.

        Returns:
            Dict with keys: task, success, type, data, error, code,
            duration_ms, markdown_output.
        """
        schema      = context.schema or {}
        storage_key = context.storage_key

        if not task:
            return {
                "task":   "",
                "success": False,
                "error":  "No task provided to PythonAgent.",
                "data":   None,
            }

        # Step 1: Generate code via LLM
        code = await generate_code(task, schema, self._llm)

        # Step 2: Execute in subprocess sandbox
        raw_result = await execute_code(
            code=code,
            csv_path=storage_key,
            timeout=self.SANDBOX_TIMEOUT,
        )

        # Step 3: Parse and normalise output
        parsed = parse_output(raw_result)
        parsed["task"]            = task
        parsed["markdown_output"] = to_markdown(parsed)

        if parsed["success"]:
            logger.info(
                "python_agent_complete",
                task=task[:80],
                result_type=parsed["type"],
                duration_ms=parsed["duration_ms"],
            )
        else:
            logger.warning(
                "python_agent_failed",
                task=task[:80],
                error=parsed["error"],
            )

        return parsed
