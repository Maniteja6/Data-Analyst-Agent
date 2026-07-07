"""Sandboxed Python executor — runs generated code in a restricted subprocess.

Security model:
- Code runs in a fresh Python subprocess with no inherited open file handles
- Input is passed as a CSV path (read-only, limited to 50k rows)
- stdout is captured as JSON; stderr is captured for error messages
- Wall-clock timeout (default 60s) kills the subprocess on overrun
- Import pre-flight check blocks obviously dangerous modules before exec

The wrapper script provides the df variable and captures the ``result``
variable as JSON on stdout.
"""
from __future__ import annotations

import asyncio
import json
import textwrap
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

TIMEOUT_SECONDS = 60
MAX_INPUT_ROWS  = 50_000
MAX_OUTPUT_CHARS = 10_000

_WRAPPER_TEMPLATE = """\
import pandas as pd
import numpy as np
import json
import math
import statistics
from collections import Counter, defaultdict

# Load dataset (read-only, row-limited)
try:
    df = pd.read_csv({csv_path!r}, nrows={max_rows})
except Exception as _e:
    df = pd.DataFrame()

# --- User-generated code ---
{user_code}
# --- End user code ---

# Capture result as JSON
if 'result' in dir():
    _out = result
else:
    _out = {{"error": "No variable named 'result' was assigned."}}

print(json.dumps(_out if isinstance(_out, (dict, list)) else str(_out), default=str))
"""


async def execute_code(
    code: str,
    csv_path: str,
    timeout: int = TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Execute Python code in a subprocess and return the captured result.

    Args:
        code:     Python source from ``code_generator.generate_code()``.
        csv_path: Local filesystem path to the dataset CSV.
        timeout:  Maximum wall-clock seconds before killing the process.

    Returns:
        Dict with keys:
        - ``result``:  The value assigned to ``result`` in the code.
        - ``code``:    The original code that was executed.
        - ``error``:   Error message (None on success).
        - ``duration_ms``: Execution time in milliseconds.
    """
    import time

    # Pre-flight: block obvious dangerous imports
    from backend.agents.analysis.python.code_generator import validate_imports
    blocked = validate_imports(code)
    if blocked:
        logger.warning("python_blocked_imports", modules=blocked)
        return {
            "result":      None,
            "code":        code,
            "error":       f"Blocked import(s): {blocked}",
            "duration_ms": 0,
        }

    wrapped = _WRAPPER_TEMPLATE.format(
        csv_path=csv_path,
        max_rows=MAX_INPUT_ROWS,
        user_code=textwrap.indent(code, ""),
    )

    start = time.monotonic()
    proc  = await asyncio.create_subprocess_exec(
        "python3", "-c", wrapped,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except TimeoutError:
        proc.kill()
        await proc.wait()
        logger.warning("python_sandbox_timeout", timeout=timeout)
        return {
            "result":      None,
            "code":        code,
            "error":       f"Execution timed out after {timeout}s",
            "duration_ms": timeout * 1000,
        }

    duration_ms = int((time.monotonic() - start) * 1000)
    stdout_text = stdout.decode("utf-8", errors="replace").strip()
    stderr_text = stderr.decode("utf-8", errors="replace").strip()

    if proc.returncode != 0:
        logger.warning(
            "python_sandbox_error",
            returncode=proc.returncode,
            stderr=stderr_text[:500],
        )
        return {
            "result":      None,
            "code":        code,
            "error":       stderr_text[:500] or f"Process exited with code {proc.returncode}",
            "duration_ms": duration_ms,
        }

    # Parse stdout as JSON
    try:
        result_value = json.loads(stdout_text[:MAX_OUTPUT_CHARS])
        logger.info(
            "python_sandbox_success",
            result_type=type(result_value).__name__,
            duration_ms=duration_ms,
        )
        return {
            "result":      result_value,
            "code":        code,
            "error":       None,
            "duration_ms": duration_ms,
        }
    except json.JSONDecodeError:
        # Return raw stdout as a string result
        return {
            "result":      stdout_text[:MAX_OUTPUT_CHARS],
            "code":        code,
            "error":       None,
            "duration_ms": duration_ms,
        }
