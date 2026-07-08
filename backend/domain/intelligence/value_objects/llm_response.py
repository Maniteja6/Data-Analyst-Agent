"""LLMResponse value object — typed wrapper for Bedrock API responses."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum

from backend.shared.value_object import ValueObject


class ResponseType(str, Enum):
    TEXT = "text"  # plain prose answer
    JSON = "json"  # structured JSON (insight list, SQL, Vega spec, etc.)
    SQL = "sql"  # a SQL SELECT statement
    PYTHON = "python"  # executable Python code
    VEGA_SPEC = "vega_spec"  # Vega-Lite JSON specification


@dataclass(frozen=True)
class LLMResponse(ValueObject):
    """Immutable wrapper for a single Bedrock Converse API response.

    Centralising the response in a typed VO means:
    - Parsing errors are caught and reported uniformly
    - Token counts and model info are always co-located with the content
    - The ``AgentResult`` entity can reference this VO for audit logging

    Attributes:
        content:       Raw text content of the model response.
        model_id:      Bedrock model ID that produced this response.
        input_tokens:  Number of input (prompt) tokens consumed.
        output_tokens: Number of output (completion) tokens consumed.
        stop_reason:   Bedrock stop reason: ``'end_turn'``, ``'max_tokens'``, etc.
        response_type: Declared type of the content (used for parsing).
        latency_ms:    Round-trip latency in milliseconds.
    """

    content: str
    model_id: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = "end_turn"
    response_type: ResponseType = ResponseType.TEXT
    latency_ms: int = 0

    def _validate(self) -> None:
        if not self.content and self.stop_reason != "max_tokens":
            raise ValueError("LLMResponse content must not be empty")
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise ValueError("Token counts must be non-negative")

    # ── Parsing helpers ───────────────────────────────────────────────────

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def was_truncated(self) -> bool:
        """True when the model hit max_tokens before finishing."""
        return self.stop_reason == "max_tokens"

    def as_json(self) -> dict | list:
        """Parse content as JSON. Strips markdown code fences if present.

        Raises:
            json.JSONDecodeError: When content cannot be parsed as JSON.
        """
        text = self.content.strip()
        # Strip ```json ... ``` or ``` ... ``` fences
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return json.loads(text.strip())

    def as_json_safe(self, default: dict | list | None = None) -> dict | list | None:
        """Like ``as_json`` but returns ``default`` instead of raising on parse error."""
        try:
            return self.as_json()
        except (json.JSONDecodeError, ValueError):
            return default if default is not None else {}

    def as_sql(self) -> str:
        """Extract SQL from the response, stripping markdown code fences."""
        text = self.content.strip()
        if "```sql" in text:
            start = text.find("```sql") + 6
            end = text.find("```", start)
            text = text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            text = text[start:end].strip()
        return text.rstrip(";").strip()

    def as_python(self) -> str:
        """Extract Python code from the response."""
        text = self.content.strip()
        if "```python" in text:
            start = text.find("```python") + 9
            end = text.find("```", start)
            return text[start:end].strip()
        if "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            return text[start:end].strip()
        return text

    @property
    def estimated_cost_usd(self) -> float:
        """Rough cost estimate based on standard Sonnet 4.5 pricing."""
        input_cost = (self.input_tokens / 1_000_000) * 3.00
        output_cost = (self.output_tokens / 1_000_000) * 15.00
        return round(input_cost + output_cost, 6)

    def to_dict(self) -> dict:
        return {
            "model_id": self.model_id,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "stop_reason": self.stop_reason,
            "latency_ms": self.latency_ms,
            "was_truncated": self.was_truncated,
            "cost_usd": self.estimated_cost_usd,
        }
