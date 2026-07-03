"""ValidationAgent — validates LLM responses for statistical accuracy and bias.

Real-time design:
    Runs on the chat response path after the LLM generates an answer and
    before the response is delivered to the user via ``chat:complete``.
    Target: < 50ms total (all checks are synchronous regex + in-memory profile).

    Socket.IO events emitted to the conversation room:
        validation:checking      — "Checking response accuracy…"
        validation:issue_found   — per validation failure (real-time)
        validation:approved      — all checks passed
        validation:flagged       — issues found but response forwarded with note

    When issues are found:
        MODERATE policy: response forwarded with a ``_validation_note`` suffix
        STRICT policy:   response rejected and InsightAgent is asked to revise

Socket.IO room:
    ``conversation:<id>`` (not the dataset room) so validation events are
    private to the client that asked the question.
"""
from __future__ import annotations

from typing import Any

import structlog

from backend.agents.base.base_agent import BaseAgent
from backend.agents.base.agent_context import AgentContext
from backend.agents.quality.validation.statistical_validator import (
    StatisticalValidator,
    ValidationFailure,
)
from backend.agents.quality.validation.bias_detector import detect_bias, bias_score

logger = structlog.get_logger(__name__)

_BIAS_SCORE_THRESHOLD = 0.40     # flag responses above this bias score
_VALIDATION_NOTE = (
    "\n\n*Note: Some statements in this response have been flagged for statistical accuracy. "
    "Please verify key figures against the raw data before acting on them.*"
)


class ValidationAgent(BaseAgent):
    """Validates chat response accuracy and bias before delivery.

    Args:
        llm_client: Reserved for future LLM-based fact-checking.
    """

    def __init__(self, llm_client=None) -> None:
        super().__init__("validation")
        self._validator = StatisticalValidator()
        self._llm       = llm_client

    async def _execute(
        self,
        context: AgentContext,
        response: str = "",
        **kwargs: Any,
    ) -> dict:
        """Validate a chat response and return a validation result.

        Args:
            context:  Shared pipeline state (profile and schema used for checks).
            response: The LLM's draft response text.

        Returns:
            Dict with keys: is_valid (bool), issues (list[dict]),
            bias_score (float), validated_response (str).
        """
        sio             = context._sio
        conversation_id = context.get("conversation_id", "")
        room = f"conversation:{conversation_id}" if conversation_id else f"dataset:{context.dataset_id}"

        if not response:
            return {"is_valid": True, "issues": [], "bias_score": 0.0, "validated_response": ""}

        if sio:
            try:
                await sio.emit(
                    "validation:checking",
                    {"conversation_id": conversation_id, "response_length": len(response)},
                    room=room,
                )
            except Exception:
                pass

        profile = context.profile or {}
        schema  = context.schema  or {}

        # ── Statistical validation ─────────────────────────────────────────
        stat_failures = self._validator.validate_response(response, profile, schema)

        # ── Bias detection ────────────────────────────────────────────────
        bias_flags = detect_bias(response)
        b_score    = bias_score(response)

        # Combine all issues
        all_issues = []
        for f in stat_failures:
            all_issues.append({
                "type":       f.failure_type,
                "severity":   f.severity,
                "claim":      f.claim_text[:100],
                "expected":   f.expected,
                "actual":     f.actual,
            })
        for b in bias_flags:
            if b.severity in ("medium", "high"):
                all_issues.append({
                    "type":       f"bias_{b.bias_type}",
                    "severity":   b.severity,
                    "matched":    b.matched,
                    "suggestion": b.suggestion,
                })

        # ── Emit per-issue events ─────────────────────────────────────────
        if sio and all_issues:
            for issue in all_issues:
                try:
                    await sio.emit(
                        "validation:issue_found",
                        {"conversation_id": conversation_id, "issue": issue},
                        room=room,
                    )
                except Exception:
                    pass

        high_severity = [i for i in all_issues if i.get("severity") == "high"]
        is_valid      = len(high_severity) == 0 and b_score < _BIAS_SCORE_THRESHOLD

        # ── Build validated response ──────────────────────────────────────
        validated_response = response
        if all_issues and not is_valid:
            validated_response = response + _VALIDATION_NOTE

        # ── Emit final verdict ────────────────────────────────────────────
        verdict_event = "validation:approved" if is_valid else "validation:flagged"
        if sio:
            try:
                await sio.emit(
                    verdict_event,
                    {
                        "conversation_id": conversation_id,
                        "issue_count":     len(all_issues),
                        "bias_score":      b_score,
                        "is_valid":        is_valid,
                    },
                    room=room,
                )
            except Exception:
                pass

        logger.info(
            "validation_complete",
            is_valid=is_valid,
            issues=len(all_issues),
            bias_score=b_score,
            high_severity=len(high_severity),
        )

        return {
            "is_valid":          is_valid,
            "issues":            all_issues,
            "bias_score":        b_score,
            "validated_response": validated_response,
        }
