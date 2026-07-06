"""Agent sub-package."""
"""Recommendation agent — converts insights into prioritised business actions.

ImpactEstimator enriches each recommendation with a quantified impact range
(min_pct, max_pct) in < 1ms using heuristic scoring — no LLM call needed.
Emits: recommendation:start, recommendation:ready (3 events), recommendation:complete.
"""
from backend.agents.output.recommendation.recommendation_agent import RecommendationAgent
from backend.agents.output.recommendation.impact_estimator     import ImpactEstimator

__all__ = ["RecommendationAgent", "ImpactEstimator"]
