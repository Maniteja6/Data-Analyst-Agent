"""should_retry — edge condition for critic-driven revision cycles.

After the CriticNode reviews the InsightNode's output, this condition
decides whether the InsightNode should be re-invoked with the critique
or whether the graph should proceed to the ReportNode.

The graph enforces a hard limit (``CRITIC_MAX_ROUNDS``) to prevent
infinite revision loops.

Usage in graph definition::

    graph.add_conditional_edges(
        "critic",
        should_retry,
        {"retry": "insight", "done": "report"},
    )
"""

from __future__ import annotations

from backend.config.settings import get_settings
from backend.orchestration.state.pipeline_state import PipelineState


def should_retry(state: PipelineState) -> str:
    """Return 'retry' when the Critic rejects the insights and rounds remain.

    Decision logic:
    - If critique is missing or already approved → 'done'
    - If revision_round counter ≥ CRITIC_MAX_ROUNDS → 'done' (safety stop)
    - Otherwise → 'retry' (InsightNode will incorporate the critique)
    """
    critique = state.get("critique") or {}
    approved = critique.get("approved", True)

    if approved:
        return "done"

    max_rounds = get_settings().critic_max_revision_rounds
    current_round = state.get("metadata", {}).get("revision_round", 0)

    if current_round >= max_rounds:
        return "done"

    return "retry"


def has_errors(state: PipelineState) -> str:
    """Return 'abort' when the state contains critical errors, 'continue' otherwise.

    Used as an early-exit edge condition after the cleaning node.
    Critical errors are those that would make downstream agents produce
    meaningless output (e.g. dataset has 0 rows after cleaning).
    """
    errors = state.get("errors") or []
    profile = state.get("profile_result") or {}
    row_count = profile.get("row_count", 1)

    if any("CRITICAL:" in e for e in errors) or row_count == 0:
        return "abort"
    return "continue"
