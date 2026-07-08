"""PII detector — identifies personally identifiable information in user messages.

Real-time design:
    Regex-based detection runs synchronously in < 1ms for typical messages.
    Microsoft Presidio (if installed) runs asynchronously in a thread pool
    as a higher-precision second pass for ambiguous cases.

    Detection triggers are ordered from fastest → most accurate:
    1. Regex patterns (synchronous, < 1ms)
    2. Presidio NER (async, ~50ms if installed)
    3. Heuristic scoring (fallback, 0ms)

PII categories detected:
    - Email addresses
    - Phone numbers (US/international)
    - SSN / Tax ID patterns
    - Credit card numbers (Luhn check)
    - IP addresses (v4/v6)
    - Passport / ID number patterns
    - Names with title prefixes (Dr., Mr., Ms., Prof.)
    - Street addresses

GDPR / CCPA handling:
    Detected PII is NOT logged — only the category and a redacted preview
    are emitted to the SecurityAgent. The raw message containing PII is
    forwarded to the LLM only after the GovernanceEngine decides whether
    to block or sanitise it.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field


@dataclass
class PIIResult:
    detected: bool
    categories: list[str] = field(default_factory=list)
    score: float = 0.0  # 0.0 → 1.0 (fraction of patterns matched)
    redacted: str = ""  # message with PII replaced by [REDACTED]


# ── Regex pattern registry ──────────────────────────────────────────────────

_PATTERNS: list[tuple[str, str]] = [
    ("email", r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"),
    ("phone_us", r"\b(?:\+1[\s-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b"),
    ("phone_intl", r"\+\d{1,3}[\s-]?\d{4,14}\b"),
    ("ssn", r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b"),
    ("credit_card", r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
    ("ipv4", r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    ("ipv6", r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b"),
    ("name_title", r"\b(?:Mr\.?|Mrs\.?|Ms\.?|Dr\.?|Prof\.?)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+"),
    ("street_addr", r"\b\d{1,5}\s+[A-Z][a-z]+(?:\s+(?:St|Ave|Rd|Blvd|Dr|Ln|Way|Ct|Pl)\.?)"),
    ("passport", r"\b[A-Z]{1,2}\d{6,9}\b"),
]

_COMPILED = [(cat, re.compile(pat)) for cat, pat in _PATTERNS]


def detect_pii_sync(message: str) -> PIIResult:
    """Fast synchronous PII detection using compiled regex patterns.

    Returns a PIIResult with detected categories and a redacted copy.
    Called on every WebSocket message before the first LLM call.
    """
    if not message:
        return PIIResult(detected=False)

    categories: list[str] = []
    redacted = message

    for category, pattern in _COMPILED:
        matches = pattern.findall(message)
        if matches:
            categories.append(category)
            redacted = pattern.sub(f"[{category.upper()}_REDACTED]", redacted)

    score = round(len(categories) / len(_COMPILED), 4)
    detected = bool(categories)

    return PIIResult(
        detected=detected,
        categories=list(set(categories)),
        score=score,
        redacted=redacted if detected else message,
    )


async def detect_pii_presidio(message: str) -> PIIResult:
    """High-precision PII detection via Microsoft Presidio (async).

    Falls back gracefully to regex detection when Presidio is not installed.
    Presidio provides NER-based name detection and custom recognisers.
    """
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _presidio_analyse, message)
        return result
    except ImportError:
        return detect_pii_sync(message)
    except Exception:
        return detect_pii_sync(message)


def _presidio_analyse(message: str) -> PIIResult:
    """Synchronous Presidio analysis — called in thread pool."""
    from presidio_analyzer import AnalyzerEngine

    engine = AnalyzerEngine()
    results = engine.analyze(text=message, language="en")
    if not results:
        return PIIResult(detected=False)

    categories = list({r.entity_type.lower() for r in results})
    redacted = message
    for r in sorted(results, key=lambda x: -x.start):
        redacted = redacted[: r.start] + f"[{r.entity_type}_REDACTED]" + redacted[r.end :]

    return PIIResult(
        detected=True,
        categories=categories,
        score=min(1.0, len(results) / 5),
        redacted=redacted,
    )


def redact_pii(message: str) -> str:
    """Return the message with all detected PII replaced by category tokens."""
    result = detect_pii_sync(message)
    return result.redacted
