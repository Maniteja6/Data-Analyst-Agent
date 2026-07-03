"""GovernanceEngine — combines PII and injection results into a final access decision.

Real-time design:
    The GovernanceEngine is the single decision point for all security checks.
    It runs synchronously on the WebSocket message path (< 2ms) so it never
    adds perceptible latency to the chat experience.

    Decision tree:
        1. Run injection classifier (< 1ms, sync)
        2. Run PII detector (< 1ms, sync regex)
        3. Combine results into GovernanceDecision
        4. If BLOCK: abort the request, emit ``security:blocked`` event
        5. If SANITISE: replace PII with redacted tokens, continue
        6. If ALLOW: pass the original message through unchanged

    All decisions are logged with a structured audit event for compliance.
    PII content is never written to audit logs.

Governance policies (configurable per environment):
    STRICT   — block on any injection or PII detection (production default)
    MODERATE — block injection, sanitise PII (development default)
    PERMISSIVE — warn only, never block (testing/CI only)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

from backend.agents.quality.security.injection_classifier import classify, InjectionResult
from backend.agents.quality.security.pii_detector import detect_pii_sync, PIIResult

logger = structlog.get_logger(__name__)


class Action(str, Enum):
    ALLOW    = "allow"
    SANITISE = "sanitise"
    BLOCK    = "block"


class Policy(str, Enum):
    STRICT     = "strict"
    MODERATE   = "moderate"
    PERMISSIVE = "permissive"


@dataclass
class GovernanceDecision:
    action:              Action
    policy:              Policy
    injection_result:    InjectionResult | None
    pii_result:          PIIResult | None
    sanitised_message:   str = ""
    block_reason:        str = ""
    audit_metadata:      dict[str, Any] = field(default_factory=dict)

    @property
    def is_blocked(self) -> bool:
        return self.action == Action.BLOCK

    @property
    def is_sanitised(self) -> bool:
        return self.action == Action.SANITISE

    @property
    def safe_message(self) -> str:
        """Return the message to forward to the LLM (original or sanitised)."""
        if self.action == Action.SANITISE:
            return self.sanitised_message
        return self.sanitised_message   # original stored here when ALLOW


class GovernanceEngine:
    """Makes access control decisions for incoming user messages and agent outputs.

    Args:
        policy:           Governance policy controlling block/sanitise thresholds.
        run_pii_check:    Whether to check for PII (default True).
        run_inject_check: Whether to check for injection (default True).
    """

    def __init__(
        self,
        policy:           Policy = Policy.MODERATE,
        run_pii_check:    bool   = True,
        run_inject_check: bool   = True,
    ) -> None:
        self._policy          = policy
        self._run_pii         = run_pii_check
        self._run_injection   = run_inject_check

    def check_user_input(self, message: str) -> GovernanceDecision:
        """Check an incoming user message for injection and PII.

        Args:
            message: Raw user message from the WebSocket.

        Returns:
            GovernanceDecision with action, block_reason, and safe_message.
        """
        injection_result: InjectionResult | None = None
        pii_result:       PIIResult | None        = None

        # ── Injection check ───────────────────────────────────────────────
        if self._run_injection:
            injection_result = classify(message)

        # ── PII check ─────────────────────────────────────────────────────
        if self._run_pii:
            pii_result = detect_pii_sync(message)

        # ── Decision ──────────────────────────────────────────────────────
        action, reason = self._decide(injection_result, pii_result)

        safe_msg = message
        if pii_result and pii_result.detected:
            safe_msg = pii_result.redacted

        decision = GovernanceDecision(
            action=action,
            policy=self._policy,
            injection_result=injection_result,
            pii_result=pii_result,
            sanitised_message=safe_msg,
            block_reason=reason,
            audit_metadata={
                "policy":              self._policy.value,
                "action":              action.value,
                "injection_detected":  injection_result.detected if injection_result else False,
                "injection_score":     injection_result.score if injection_result else 0.0,
                "injection_risk":      injection_result.risk_level if injection_result else "none",
                "pii_detected":        pii_result.detected if pii_result else False,
                "pii_categories":      pii_result.categories if pii_result else [],
                "message_length":      len(message),
            },
        )

        # Structured audit log (never includes raw message or PII content)
        logger.info(
            "governance_decision",
            **decision.audit_metadata,
        )

        return decision

    def check_agent_output(self, response: str) -> GovernanceDecision:
        """Scan an agent's response for accidental PII leakage before sending to user.

        For example, if the dataset contains email addresses and the LLM
        directly quotes them in the response, this check will sanitise them.
        """
        pii = detect_pii_sync(response)
        if not pii.detected:
            return GovernanceDecision(
                action=Action.ALLOW,
                policy=self._policy,
                injection_result=None,
                pii_result=pii,
                sanitised_message=response,
            )
        return GovernanceDecision(
            action=Action.SANITISE,
            policy=self._policy,
            injection_result=None,
            pii_result=pii,
            sanitised_message=pii.redacted,
            block_reason="PII detected in agent output; content sanitised.",
        )

    def _decide(
        self,
        injection: InjectionResult | None,
        pii:       PIIResult | None,
    ) -> tuple[Action, str]:
        """Apply the configured policy to produce an Action and reason."""

        if self._policy == Policy.PERMISSIVE:
            return Action.ALLOW, ""

        # Injection takes priority in all non-permissive policies
        if injection and injection.detected:
            if injection.risk_level in ("high", "critical"):
                return Action.BLOCK, (
                    f"Prompt injection detected "
                    f"(risk={injection.risk_level}, "
                    f"patterns={injection.matched_patterns}). "
                    "Request blocked."
                )
            if injection.risk_level == "medium":
                if self._policy == Policy.STRICT:
                    return Action.BLOCK, "Possible injection (STRICT policy). Request blocked."
                return Action.SANITISE, "Possible injection; message sanitised."

        # PII handling
        if pii and pii.detected:
            if self._policy == Policy.STRICT:
                return Action.BLOCK, (
                    f"PII detected ({pii.categories}). "
                    "Request blocked under STRICT policy."
                )
            return Action.SANITISE, f"PII sanitised ({pii.categories})."

        return Action.ALLOW, ""
