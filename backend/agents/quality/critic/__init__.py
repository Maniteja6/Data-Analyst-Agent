"""Critic agent — validates InsightAgent output against 5 quality criteria.

Criteria: ACCURACY, SPECIFICITY, RELEVANCE, COMPLETENESS, BIAS.
Emits: critic:reviewing, critic:issue_found (per issue), critic:approved |
       critic:revision_needed, critic:round_complete.
Auto-approves (score=0.90) on LLM failure to avoid blocking the pipeline.
"""

from backend.agents.quality.critic.critic_agent import CriticAgent

__all__ = ["CriticAgent"]
