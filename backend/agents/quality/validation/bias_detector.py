"""BiasDetector — flags absolute and biased language in LLM responses.

Real-time design:
    Pure regex, synchronous, < 1ms per response.
    Runs on every InsightAgent and chat response before delivery.

Bias categories:
    ABSOLUTE   — "always", "never", "all", "every", "none", "impossible"
    HEDGING    — "might", "could", "possibly" used to overstate uncertainty
    ANCHORING  — references to specific unverifiable external benchmarks
    RECENCY    — assumes current data is the most recent ("as of today")
    CAUSATION  — implies causation from correlation ("X causes Y")
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class BiasFlag:
    bias_type:  str
    matched:    str
    suggestion: str
    severity:   str = "low"


_BIAS_PATTERNS: list[tuple[str, str, list[str], str]] = [
    # (bias_type, severity, patterns, suggestion_template)
    (
        "absolute_language",
        "medium",
        [
            r"\b(always|never|all|every|none|no\s+one|everyone|impossible|certain)\b",
        ],
        "Replace absolute terms with quantified statements (e.g. '95% of' instead of 'all').",
    ),
    (
        "causation_from_correlation",
        "high",
        [
            r"\b(\w+)\s+(causes?|leads?\s+to|results?\s+in|makes?\s+\w+\s+(?:go\s+up|go\s+down|increase|decrease))\b",
            r"\bproven\s+to\s+(cause|create|drive|reduce|increase)\b",
        ],
        "Use correlation language: 'is associated with' or 'correlates with'.",
    ),
    (
        "unverified_benchmark",
        "medium",
        [
            r"\b(industry\s+standard|market\s+average|typical\s+company|normal|average\s+company)\s+(is|are|has|have)\b",
            r"\bcompared\s+to\s+(the\s+)?industry\b",
        ],
        "Provide the source of the benchmark or remove the comparison.",
    ),
    (
        "false_precision",
        "low",
        [
            r"\b\d+\.\d{3,}\s*%\b",   # more than 2 decimal places in a percentage
        ],
        "Round to 1-2 decimal places for percentages derived from small samples.",
    ),
    (
        "overgeneralisation",
        "medium",
        [
            r"\b(this|the)\s+data\s+(proves?|confirms?|shows\s+definitively|demonstrates\s+conclusively)\b",
            r"\bconclusive\s+(evidence|proof|data)\b",
        ],
        "Replace 'proves' with 'suggests' or 'indicates'.",
    ),
]

_COMPILED_BIAS: list[tuple[str, str, list[re.Pattern], str]] = [
    (btype, sev, [re.compile(p, re.IGNORECASE) for p in pats], sugg)
    for btype, sev, pats, sugg in _BIAS_PATTERNS
]


def detect_bias(text: str) -> list[BiasFlag]:
    """Detect biased or absolute language in a text string.

    Args:
        text: Any text string (insight headline, explanation, chat response).

    Returns:
        List of BiasFlag objects. Empty list = no bias detected.
    """
    flags: list[BiasFlag] = []
    for bias_type, severity, patterns, suggestion in _COMPILED_BIAS:
        for pattern in patterns:
            for match in pattern.finditer(text):
                flags.append(BiasFlag(
                    bias_type=bias_type,
                    matched=match.group(0),
                    suggestion=suggestion,
                    severity=severity,
                ))
    return flags


def is_biased(text: str) -> bool:
    """Return True when medium or high severity bias is detected."""
    return any(f.severity in ("medium", "high") for f in detect_bias(text))


def bias_score(text: str) -> float:
    """Return a 0.0–1.0 bias score (higher = more biased).

    Weights: high=1.0, medium=0.5, low=0.2.
    Capped at 1.0.
    """
    weights = {"high": 1.0, "medium": 0.5, "low": 0.2}
    total = sum(weights.get(f.severity, 0.2) for f in detect_bias(text))
    return min(1.0, round(total / 3, 4))   # normalise: 3 high flags = max score
