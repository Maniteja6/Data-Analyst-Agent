"""Security agents — injection detection, PII scanning, and governance.

All checks run synchronously (regex-only) in < 2ms — never adds latency
to the WebSocket message path.

InjectionClassifier: 10-category weighted scoring; risk levels none→critical.
PIIDetector:         10 regex patterns + optional Presidio NER fallback.
GovernanceEngine:    STRICT | MODERATE | PERMISSIVE policy; ALLOW/SANITISE/BLOCK.
SecurityAgent:       first LangGraph node; emits security:cleared | security:blocked
                     to conversation:<id> room (private to the requesting client).
"""

from backend.agents.quality.security.governance_engine import (
    Action,
    GovernanceEngine,
    Policy,
)
from backend.agents.quality.security.injection_classifier import classify as classify_injection
from backend.agents.quality.security.pii_detector import detect_pii_sync
from backend.agents.quality.security.security_agent import SecurityAgent

__all__ = [
    "SecurityAgent",
    "GovernanceEngine",
    "Policy",
    "Action",
    "classify_injection",
    "detect_pii_sync",
]
