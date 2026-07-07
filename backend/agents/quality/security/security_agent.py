"""SecurityAgent — gates every chat message through injection and PII checks.

Real-time design:
    The SecurityAgent is the FIRST node in the chat query LangGraph.
    It must complete in < 5ms for injection/PII checks so the user
    perceives zero added latency on safe messages.

    Socket.IO events emitted:
        security:pii_detected       — PII found; emitted before sanitising
        security:injection_detected — injection attempt; message blocked
        security:blocked            — request blocked, reason included
        security:cleared            — all checks passed, forwarding to agents

    When a message is blocked:
        1. ``security:blocked`` event is emitted with the reason
        2. The LangGraph routes to END (skips all downstream agents)
        3. The chat handler sends a polite refusal message to the user
        4. An audit log entry is created for compliance review

    When PII is detected but policy = MODERATE:
        1. ``security:pii_detected`` is emitted
        2. The sanitised (redacted) message is forwarded to downstream agents
        3. The user sees a note: "Note: personal information was redacted."

    All security events are emitted to the conversation room
    (``conversation:<id>``) rather than the dataset room so they are only
    visible to the client that sent the message.
"""
from __future__ import annotations

from typing import Any

import structlog
from backend.agents.base.agent_context import AgentContext
from backend.agents.base.base_agent import BaseAgent
from backend.agents.quality.security.governance_engine import (
    GovernanceDecision,
    GovernanceEngine,
    Policy,
)
from backend.config.feature_flags import flags

logger = structlog.get_logger(__name__)


class SecurityAgent(BaseAgent):
    """First-pass security gate for real-time chat messages.

    Args:
        policy:    Governance policy (STRICT | MODERATE | PERMISSIVE).
        llm_client: Optional — reserved for future LLM-based content moderation.
    """

    def __init__(
        self,
        policy:     Policy = Policy.MODERATE,
        llm_client: Any    = None,
    ) -> None:
        super().__init__("security")
        self._engine = GovernanceEngine(
            policy=policy,
            run_pii_check=flags.pii_detection_enabled,
            run_inject_check=flags.injection_detection_enabled,
        )
        self._llm = llm_client

    async def _execute(
        self,
        context: AgentContext,
        message: str = "",
        **kwargs: Any,
    ) -> dict:
        """Run all security checks and return a decision dict.

        Args:
            context: Shared pipeline state.
            message: Raw user message from the WebSocket.

        Returns:
            Dict with keys: safe (bool), action, sanitised_message,
            pii_detected, pii_categories, injection_detected, injection_score,
            injection_risk, block_reason.
        """
        sio             = context._sio
        conversation_id = context.get("conversation_id", "")
        dataset_id      = context.dataset_id

        if not message:
            return self._allow_result("", "empty_message")

        # Feature flags — skip checks in permissive/test mode
        if not flags.pii_detection_enabled and not flags.injection_detection_enabled:
            return self._allow_result(message, "checks_disabled")

        # ── Run governance check (synchronous, < 2ms) ─────────────────────
        decision: GovernanceDecision = self._engine.check_user_input(message)

        # ── Real-time Socket.IO events ────────────────────────────────────
        room = f"conversation:{conversation_id}" if conversation_id else f"dataset:{dataset_id}"

        if decision.pii_result and decision.pii_result.detected and sio:
            try:
                await sio.emit(
                    "security:pii_detected",
                    {
                        "conversation_id": conversation_id,
                        "categories":      decision.pii_result.categories,
                        "action":          decision.action.value,
                    },
                    room=room,
                )
            except Exception:
                pass

        if decision.injection_result and decision.injection_result.detected and sio:
            try:
                await sio.emit(
                    "security:injection_detected",
                    {
                        "conversation_id":   conversation_id,
                        "risk_level":        decision.injection_result.risk_level,
                        "matched_patterns":  decision.injection_result.matched_patterns,
                        "action":            decision.action.value,
                    },
                    room=room,
                )
            except Exception:
                pass

        # ── Block path ────────────────────────────────────────────────────
        if decision.is_blocked:
            if sio:
                try:
                    await sio.emit(
                        "security:blocked",
                        {
                            "conversation_id": conversation_id,
                            "reason":          decision.block_reason,
                        },
                        room=room,
                    )
                except Exception:
                    pass

            logger.warning(
                "security_message_blocked",
                reason=decision.block_reason,
                injection_risk=decision.injection_result.risk_level if decision.injection_result else "none",
                pii_categories=decision.pii_result.categories if decision.pii_result else [],
            )

            return {
                "safe":                False,
                "action":              "block",
                "sanitised_message":   None,
                "pii_detected":        bool(decision.pii_result and decision.pii_result.detected),
                "pii_categories":      decision.pii_result.categories if decision.pii_result else [],
                "injection_detected":  bool(decision.injection_result and decision.injection_result.detected),
                "injection_score":     decision.injection_result.score if decision.injection_result else 0.0,
                "injection_risk":      decision.injection_result.risk_level if decision.injection_result else "none",
                "block_reason":        decision.block_reason,
            }

        # ── Allow / sanitise path ─────────────────────────────────────────
        if sio:
            try:
                await sio.emit(
                    "security:cleared",
                    {
                        "conversation_id": conversation_id,
                        "pii_sanitised":   decision.is_sanitised,
                        "pii_categories":  decision.pii_result.categories if decision.pii_result else [],
                    },
                    room=room,
                )
            except Exception:
                pass

        logger.info(
            "security_cleared",
            action=decision.action.value,
            pii_sanitised=decision.is_sanitised,
            injection_score=decision.injection_result.score if decision.injection_result else 0.0,
        )

        return {
            "safe":               True,
            "action":             decision.action.value,
            "sanitised_message":  decision.safe_message,
            "pii_detected":       bool(decision.pii_result and decision.pii_result.detected),
            "pii_categories":     decision.pii_result.categories if decision.pii_result else [],
            "injection_detected": bool(decision.injection_result and decision.injection_result.detected),
            "injection_score":    decision.injection_result.score if decision.injection_result else 0.0,
            "injection_risk":     decision.injection_result.risk_level if decision.injection_result else "none",
            "block_reason":       None,
        }

    async def scan_agent_output(self, response: str, context: AgentContext) -> str:
        """Scan an LLM response for PII before delivering to the user.

        Returns the sanitised response string.
        """
        decision = self._engine.check_agent_output(response)
        if decision.is_sanitised:
            logger.info("security_output_pii_sanitised",
                        categories=decision.pii_result.categories if decision.pii_result else [])
        return decision.safe_message

    @staticmethod
    def _allow_result(message: str, reason: str) -> dict:
        return {
            "safe":               True,
            "action":             "allow",
            "sanitised_message":  message,
            "pii_detected":       False,
            "pii_categories":     [],
            "injection_detected": False,
            "injection_score":    0.0,
            "injection_risk":     "none",
            "block_reason":       None,
            "skip_reason":        reason,
        }
