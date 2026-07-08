"""InjectionClassifier — detects prompt injection attempts in user messages.

Real-time design:
    Runs synchronously (regex-only, zero I/O) so it completes in < 1ms and
    never adds latency to the WebSocket message handling path. If an injection
    is detected, the SecurityAgent blocks the request before any LLM call,
    preventing both the attack and the associated token cost.

Injection patterns:
    The classifier checks for 10 pattern categories that attempt to:
    - Override the system prompt or agent persona
    - Extract training data or system instructions
    - Exfiltrate dataset contents through LLM output
    - Trigger tool calls not authorised by the user
    - Jailbreak content policies via roleplay or encoding

Score: matched_categories / total_patterns (weighted)
Threshold: 0.35 (default — conservative to minimise false negatives in production)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class InjectionResult:
    detected: bool
    score: float
    matched_patterns: list[str] = field(default_factory=list)
    risk_level: str = "none"  # none | low | medium | high | critical


# Pattern registry — each entry is (category_name, regex_list, weight)
_PATTERNS: list[tuple[str, list[str], float]] = [
    (
        "persona_override",
        [
            r"(?i)\bignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|context)",
            r"(?i)\bforget\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|context)",
            r"(?i)\byou\s+are\s+now\s+(a|an)\s+\w+",
            r"(?i)\bact\s+as\s+(a|an)\s+(different|new|unrestricted|free)",
            r"(?i)\bpretend\s+(you\s+are|to\s+be)\s+(a|an)\s+\w+",
        ],
        2.0,
    ),
    (
        "system_prompt_extraction",
        [
            r"(?i)\b(repeat|print|output|reveal|show|display|tell\s+me)\s+(your\s+)?(system\s+prompt|instructions?|context|directives?)",
            r"(?i)\bwhat\s+(are\s+)?(your|the)\s+(instructions?|system\s+prompt|prompts?)",
            r"(?i)\brepeat\s+everything\s+(above|before)",
        ],
        2.0,
    ),
    (
        "instruction_override",
        [
            r"(?i)\b(new\s+)?(instruction|directive|command|rule)s?:\s*\w",
            r"(?i)\bdisregard\s+(all\s+)?(safety|content|ethical)\s+(guidelines?|policies?|rules?)",
            r"(?i)\boverride\s+(all\s+)?(previous|current|existing)\s+(instructions?|guidelines?|rules?)",
        ],
        1.5,
    ),
    (
        "role_jailbreak",
        [
            r"(?i)\b(DAN|DUDE|STAN|JailGPT|ChatGPT\s+Developer\s+Mode)",
            r"(?i)\bdo\s+anything\s+now\b",
            r"(?i)\bunrestricted\s+mode\b",
            r"(?i)\bno\s+filter\s+mode\b",
        ],
        2.0,
    ),
    (
        "data_exfiltration",
        [
            r"(?i)\b(send|export|upload|transmit)\s+(all\s+)?(data|dataset|contents?|rows?)\s+to\b",
            r"(?i)\bprint\s+all\s+(rows?|records?|data|contents?)",
            r"(?i)\bshow\s+me\s+(all\s+)?(the\s+)?(raw\s+)?(dataset|data|rows?|records?)",
        ],
        1.5,
    ),
    (
        "code_injection",
        [
            r"(?i)\bexecute\s+(this|the\s+following)\s+(code|script|command)",
            r"(?i)\brun\s+(rm|del|format|shutdown|curl|wget)\b",
            r"(?i)\b__import__\s*\(",
            r"(?i)\bos\.system\s*\(",
            r"(?i)\bsubprocess\.(run|call|Popen)\s*\(",
        ],
        2.5,
    ),
    (
        "delimiter_injection",
        [
            r"(?i)```\s*(system|human|assistant|user)\b",
            r"(?i)<\|im_start\|>",
            r"(?i)\[INST\]",
            r"(?i)###\s*(Instruction|System|Human|Assistant)\b",
        ],
        1.5,
    ),
    (
        "multi_step_injection",
        [
            r"(?i)\bfirst\b.{0,100}\bthen\s+(ignore|forget|override)\b",
            r"(?i)\bstep\s+1\b.{0,200}\bstep\s+2\s*:\s*(ignore|forget|override|disable)\b",
        ],
        1.5,
    ),
    (
        "social_engineering",
        [
            r"(?i)\bpretend\s+(this\s+is|it's)\s+(a\s+)?(test|drill|simulation|fictional|hypothetical)",
            r"(?i)\bfor\s+(educational|research|academic)\s+purposes",
            r"(?i)\bmy\s+(boss|manager|company|client)\s+(said|told|asked)\s+(you|me)\s+to\s+(ignore|override)",
        ],
        1.0,
    ),
    (
        "evasion_encoding",
        [
            r"(?i)\b(base64|ROT13|hex\s+encode|morse\s+code)\s+(this|the\s+following|decode)\b",
            r"(?i)ignore.{0,10}prev.{0,10}inst",  # abbreviated injection
            r"(?i)\bp(lease\s+)?i(gnore\s+)?a(ll\s+)?p(revious\s+)?i(nstructions?)?",  # spaced out
        ],
        1.5,
    ),
]

# Total weighted score for normalisation
_MAX_SCORE = sum(weight for _, _, weight in _PATTERNS)

# Risk levels by score
_RISK_LEVELS = [
    (0.00, "none"),
    (0.20, "low"),
    (0.40, "medium"),
    (0.70, "high"),
    (1.00, "critical"),
]


def classify(message: str) -> InjectionResult:
    """Classify a user message for prompt injection attempts.

    Args:
        message: Raw user message string.

    Returns:
        InjectionResult with detected flag, score, matched patterns, risk level.
    """
    if not message or len(message) < 5:
        return InjectionResult(detected=False, score=0.0)

    matched: list[str] = []
    weighted_score = 0.0

    for category, patterns, weight in _PATTERNS:
        for pattern in patterns:
            if re.search(pattern, message):
                matched.append(category)
                weighted_score += weight
                break  # only score each category once per message

    score = min(1.0, round(weighted_score / _MAX_SCORE, 4))
    risk_level = "none"
    for threshold, level in reversed(_RISK_LEVELS):
        if score >= threshold:
            risk_level = level
            break

    # Default detection threshold: any match at medium+ risk
    detected = risk_level in ("medium", "high", "critical")

    return InjectionResult(
        detected=detected,
        score=score,
        matched_patterns=matched,
        risk_level=risk_level,
    )


def is_safe(message: str) -> bool:
    """Quick boolean check — returns True when no injection is detected."""
    return not classify(message).detected
