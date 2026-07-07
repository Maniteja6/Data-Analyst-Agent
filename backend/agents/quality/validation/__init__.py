"""Validation agents — statistical accuracy and bias detection on LLM responses.

StatisticalValidator: checks range, percentage, count claims against DataProfile.
BiasDetector:         5-category regex; returns BiasFlag list + 0.0-1.0 score.
ValidationAgent:      combines both; emits validation:approved | validation:flagged
                      to conversation:<id> room; appends disclaimer on issues.
"""

from backend.agents.quality.validation.bias_detector import bias_score, detect_bias
from backend.agents.quality.validation.statistical_validator import (
    StatisticalValidator,
)
from backend.agents.quality.validation.validation_agent import ValidationAgent

__all__ = ["ValidationAgent", "StatisticalValidator", "detect_bias", "bias_score"]
