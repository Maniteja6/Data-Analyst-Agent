"""LLM-based Python analysis code generator.

Produces sandboxable pandas/numpy code that assigns a final ``result``
variable. Scoped to a restricted set of imports to prevent filesystem
access or network calls inside the sandbox.
"""
from __future__ import annotations

import structlog

from backend.infrastructure.llm.model_id_registry import get_model_id

logger = structlog.get_logger(__name__)

ALLOWED_IMPORTS = frozenset({
    "pandas", "numpy", "scipy", "math",
    "statistics", "collections", "datetime",
    "itertools", "functools",
})

_SYSTEM = (
    "You are a Python data analyst. "
    "Write concise pandas code that computes the answer. "
    "Return ONLY valid Python. No markdown. No explanation."
)


async def generate_code(task: str, schema: dict, llm_client) -> str:
    """Generate pandas analysis code for the given task.

    Args:
        task:       Natural-language description of what to compute.
        schema:     Dataset schema dict with a ``columns`` list.
        llm_client: Async LLM client.

    Returns:
        Python source code string (not yet executed).
    """
    columns = schema.get("columns", [])
    col_desc = ", ".join(
        f"{c['name']} ({c['data_type']}, {c.get('semantic_type', 'unknown')})"
        for c in columns[:30]
    )

    prompt = f"""Write Python pandas code to complete this analytics task.

DATASET: Loaded as a pandas DataFrame called `df`.
COLUMNS: {col_desc}

TASK: {task}

STRICT RULES:
- Only import from: {sorted(ALLOWED_IMPORTS)}
- NO file I/O (open, read, write). NO network calls. NO os/sys/subprocess.
- Handle NaN: use .dropna() or .fillna() before computing statistics.
- Assign the final answer to a variable called `result`.
- `result` must be a Python dict, list, int, or float — NOT a DataFrame.
- Keep code under 40 lines.

Return ONLY Python code. No backticks. No explanation."""

    response = await llm_client.complete(
        prompt=prompt,
        system=_SYSTEM,
        model_id=get_model_id("python"),
    )

    # Strip markdown fences if the model added them
    code = response.strip()
    if code.startswith("```"):
        lines = code.splitlines()
        code = "\n".join(
            line for line in lines if not line.startswith("```")
        ).strip()

    logger.debug("code_generated", task=task[:80], lines=code.count("\n") + 1)
    return code


def validate_imports(code: str) -> list[str]:
    """Return a list of imported modules not in the allowed set.

    Used by ``sandboxed_executor`` as a pre-flight check.
    """
    import ast
    blocked = []
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root not in ALLOWED_IMPORTS:
                        blocked.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                if root not in ALLOWED_IMPORTS:
                    blocked.append(node.module or "?")
    except SyntaxError:
        pass
    return blocked
