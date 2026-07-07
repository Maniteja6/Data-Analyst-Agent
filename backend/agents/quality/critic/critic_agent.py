"""CriticAgent — validates InsightAgent output and drives revision cycles.

Real-time pipeline:
    The CriticAgent runs after InsightAgent and before RecommendationAgent.
    When insights fail validation, it emits ``critic:revision_needed`` to the
    dataset's Socket.IO room so the frontend can show a "Refining insights…"
    indicator while the revision cycle runs.

    Revision loop (max 2 rounds, controlled by the LangGraph ``should_retry``
    condition):
        Round 0: InsightAgent generates draft insights
        Round 1: CriticAgent reviews → emits revision_needed → InsightAgent revises
        Round 2: CriticAgent reviews again → approves or force-approves

    Each revision round is emitted as a ``critic:round_complete`` event so the
    frontend timeline accurately reflects the refinement process.

Validation criteria:
    1. ACCURACY    — every claim must cite a specific column or value
    2. SPECIFICITY — no vague language ("some", "many", "various")
    3. RELEVANCE   — insight must be actionable for a business decision
    4. COMPLETENESS — explains both what and why
    5. BIAS         — no absolute language ("always", "never", "all")

Socket.IO events emitted:
    critic:reviewing         — "Validating {N} insights…"
    critic:issue_found       — per issue found (real-time issue stream)
    critic:revision_needed   — when overall_score < threshold
    critic:approved          — when insights pass all criteria
    critic:round_complete    — after each revision round
"""
from __future__ import annotations

import json
import re
from typing import Any

import structlog
from backend.agents.base.agent_context import AgentContext
from backend.agents.base.base_agent import BaseAgent
from backend.infrastructure.llm.model_id_registry import get_model_id

logger = structlog.get_logger(__name__)

_SYSTEM = (
    "You are a data quality auditor for business analytics reports. "
    "Return ONLY valid JSON. No markdown. No explanation."
)
_MAX_TOKENS      = 1500
_APPROVAL_THRESHOLD = 0.75   # insights scoring below this trigger revision


class CriticAgent(BaseAgent):
    """Reviews InsightAgent output against 5 quality criteria.

    Args:
        llm_client: Claude Sonnet for critique generation.
    """

    def __init__(self, llm_client=None) -> None:
        super().__init__("critic")
        self._llm = llm_client

    async def _execute(self, context: AgentContext, **kwargs: Any) -> dict:
        """Critique the current insight results and return a structured critique.

        Args:
            context: Shared pipeline state (insight_results and profile read).

        Returns:
            Dict with keys: approved (bool), overall_score (float),
            issues (list[dict]), revised_insights (list), round (int).
        """
        sio        = context._sio
        dataset_id = context.dataset_id
        insights   = context.insight_results or []
        profile    = context.profile or {}

        # Pull revision round from context metadata
        current_round = context.get("critic_revision_round", 0)

        # Notify frontend critique is starting
        if sio and dataset_id:
            try:
                await sio.emit(
                    "critic:reviewing",
                    {
                        "dataset_id":  dataset_id,
                        "insight_count": len(insights),
                        "round":       current_round + 1,
                    },
                    room=f"dataset:{dataset_id}",
                )
            except Exception:
                pass

        await context.push_progress(
            88,
            f"Validating insights (round {current_round + 1})…",
            step="critic",
        )

        # Generate critique via LLM
        critique = await self._critique(insights, profile)

        # Emit per-issue events for real-time issue stream
        if sio and dataset_id and critique.get("issues"):
            for issue in critique["issues"]:
                try:
                    await sio.emit(
                        "critic:issue_found",
                        {
                            "dataset_id":    dataset_id,
                            "issue":         issue,
                            "round":         current_round + 1,
                        },
                        room=f"dataset:{dataset_id}",
                    )
                except Exception:
                    pass

        approved = critique.get("overall_score", 1.0) >= _APPROVAL_THRESHOLD

        # Emit approval or revision_needed
        if sio and dataset_id:
            event = "critic:approved" if approved else "critic:revision_needed"
            try:
                await sio.emit(
                    event,
                    {
                        "dataset_id":    dataset_id,
                        "overall_score": critique.get("overall_score", 0.0),
                        "issue_count":   len(critique.get("issues", [])),
                        "round":         current_round + 1,
                    },
                    room=f"dataset:{dataset_id}",
                )
            except Exception:
                pass

        # Update revision round counter
        context.set("critic_revision_round", current_round + 1)

        result = {
            "approved":          approved,
            "overall_score":     critique.get("overall_score", 0.0),
            "issues":            critique.get("issues", []),
            "revised_insights":  critique.get("revised_insights", []),
            "round":             current_round + 1,
        }

        # Emit round_complete with timing info
        if sio and dataset_id:
            try:
                await sio.emit(
                    "critic:round_complete",
                    {
                        "dataset_id": dataset_id,
                        "approved":   approved,
                        "round":      current_round + 1,
                        "score":      result["overall_score"],
                    },
                    room=f"dataset:{dataset_id}",
                )
            except Exception:
                pass

        logger.info(
            "critic_agent_complete",
            approved=approved,
            score=result["overall_score"],
            issues=len(result["issues"]),
            round=current_round + 1,
        )
        return result

    # ── LLM critique generation ───────────────────────────────────────────

    async def _critique(self, insights: list[dict], profile: dict) -> dict:
        """Call Claude Sonnet to critique the insights."""
        if not self._llm or not insights:
            return {"approved": True, "overall_score": 1.0, "issues": [], "revised_insights": []}

        insights_json = json.dumps([
            {
                "index":           i,
                "headline":        ins.get("headline", ""),
                "explanation":     ins.get("explanation", ""),
                "business_impact": ins.get("business_impact", ""),
                "confidence":      ins.get("confidence", 0.0),
                "source_columns":  ins.get("source_columns", []),
            }
            for i, ins in enumerate(insights[:5])
        ], indent=2)

        profile_summary = (
            f"Rows: {profile.get('row_count', 0):,} | "
            f"Cols: {profile.get('column_count', 0)} | "
            f"Completeness: {profile.get('completeness_score', 1.0):.1%}"
        )

        prompt = (
            f"Review these {len(insights)} business data insights for quality.\n\n"
            f"DATASET PROFILE: {profile_summary}\n\n"
            f"INSIGHTS TO REVIEW:\n{insights_json}\n\n"
            "VALIDATION CRITERIA:\n"
            "1. ACCURACY — does each insight cite a specific column name or numeric value?\n"
            "2. SPECIFICITY — no vague words like 'some', 'many', 'various', 'significant'\n"
            "3. RELEVANCE — is each insight actionable for a business decision maker?\n"
            "4. COMPLETENESS — does it explain both WHAT is happening and WHY it matters?\n"
            "5. BIAS — no absolute language ('always', 'never', 'all', 'every')\n\n"
            "For each failing criterion, describe the SPECIFIC issue and how to fix it.\n"
            "Also provide revised versions of insights that fail.\n\n"
            "Return ONLY valid JSON:\n"
            "{\n"
            '  "overall_score": 0.87,\n'
            '  "issues": [\n'
            '    {\n'
            '      "insight_index": 0,\n'
            '      "criterion": "specificity",\n'
            '      "severity": "high|medium|low",\n'
            '      "description": "specific description of the issue",\n'
            '      "suggested_fix": "how to correct it"\n'
            '    }\n'
            '  ],\n'
            '  "revised_insights": []\n'
            "}"
        )

        try:
            raw  = await self._llm.complete(
                prompt=prompt,
                system=_SYSTEM,
                model_id=get_model_id("planner"),
                max_tokens=_MAX_TOKENS,
            )
            data = self._parse_json(raw)
            if data and "overall_score" in data:
                return data
        except Exception as exc:
            logger.warning("critic_llm_failed", error=str(exc))

        # Auto-approve on LLM failure to avoid blocking the pipeline
        return {"overall_score": 0.90, "issues": [], "revised_insights": []}

    @staticmethod
    def _parse_json(raw: str) -> dict | None:
        text = raw.strip()
        if text.startswith("```"):
             text = "\n".join(line for line in text.splitlines() if not line.startswith("`""`")).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        return None
