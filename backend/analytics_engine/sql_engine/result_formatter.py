"""ResultFormatter — converts DuckDB result rows to Markdown and chart-ready dicts."""

from __future__ import annotations

import json
from typing import Any


class ResultFormatter:
    """Formats DuckDB query results for Insight Agent consumption and frontend display."""

    def to_markdown_table(self, rows: list[dict], max_rows: int = 20) -> str:
        """Convert rows to a Markdown table string."""
        if not rows:
            return "_No results._"

        display = rows[:max_rows]
        headers = list(display[0].keys())
        header_row = "| " + " | ".join(headers) + " |"
        sep_row = "| " + " | ".join("---" for _ in headers) + " |"
        data_rows = [
            "| " + " | ".join(str(row.get(h, "")) for h in headers) + " |" for row in display
        ]
        result = "\n".join([header_row, sep_row] + data_rows)
        if len(rows) > max_rows:
            result += f"\n\n_... {len(rows) - max_rows} more rows_"
        return result

    def to_vega_data(self, rows: list[dict]) -> list[dict]:
        """Return rows in the format expected by Vega-Lite's ``data.values`` field."""
        return [{k: self._json_safe(v) for k, v in row.items()} for row in rows]

    def summarise(self, rows: list[dict]) -> str:
        """Produce a one-line natural-language summary of the result."""
        if not rows:
            return "The query returned no results."
        n = len(rows)
        headers = list(rows[0].keys())
        if n == 1 and len(headers) == 1:
            val = list(rows[0].values())[0]
            return f"Result: **{val}**"
        return (
            f"Query returned {n:,} row{'s' if n != 1 else ''} with columns: {', '.join(headers)}."
        )

    def to_json(self, rows: list[dict], indent: int = 2) -> str:
        """Serialise rows to a JSON string."""
        return json.dumps(
            [{k: self._json_safe(v) for k, v in row.items()} for row in rows],
            indent=indent,
            default=str,
        )

    @staticmethod
    def _json_safe(value: Any) -> Any:  # noqa: ANN401
        """Coerce non-JSON-serialisable values to strings."""
        if value is None or isinstance(value, int | float | bool | str):
            return value
        return str(value)
