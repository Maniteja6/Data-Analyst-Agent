"""Parses and normalises Python agent sandbox execution output."""
from __future__ import annotations
from typing import Any


def parse_output(raw: dict) -> dict[str, Any]:
    """Convert sandbox execution output into a standardised result dict.

    Args:
        raw: Dict returned by ``sandboxed_executor.execute_code()``.

    Returns:
        Standardised dict with keys:
        - ``success``:     True when no error occurred.
        - ``type``:        'dict' | 'list' | 'scalar' | 'error'
        - ``data``:        The parsed result value.
        - ``error``:       Error string (None on success).
        - ``duration_ms``: Execution duration.
        - ``code``:        The source code that was executed.
    """
    duration_ms = raw.get("duration_ms", 0)
    code        = raw.get("code", "")

    if raw.get("error"):
        return {
            "success":     False,
            "type":        "error",
            "data":        None,
            "error":       raw["error"],
            "duration_ms": duration_ms,
            "code":        code,
        }

    result = raw.get("result")

    if isinstance(result, dict):
        data_type = "dict"
    elif isinstance(result, list):
        data_type = "list"
    elif isinstance(result, (int, float, bool)):
        data_type = "scalar"
    else:
        data_type = "scalar"
        result    = str(result) if result is not None else ""

    return {
        "success":     True,
        "type":        data_type,
        "data":        result,
        "error":       None,
        "duration_ms": duration_ms,
        "code":        code,
    }


def to_markdown(parsed: dict) -> str:
    """Convert parsed output to a readable Markdown snippet."""
    if not parsed["success"]:
        return f"**Error:** {parsed['error']}"

    data = parsed["data"]
    if isinstance(data, dict):
        rows = "\n".join(f"- **{k}**: {v}" for k, v in data.items())
        return rows
    if isinstance(data, list) and data and isinstance(data[0], dict):
        headers = list(data[0].keys())
        header_row = "| " + " | ".join(headers) + " |"
        sep_row    = "| " + " | ".join("---" for _ in headers) + " |"
        body_rows  = [
            "| " + " | ".join(str(row.get(h, "")) for h in headers) + " |"
            for row in data[:20]
        ]
        return "\n".join([header_row, sep_row] + body_rows)
    return str(data)
