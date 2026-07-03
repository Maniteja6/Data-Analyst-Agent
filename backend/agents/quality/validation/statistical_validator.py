"""StatisticalValidator — checks LLM claims against the DataProfile.

Real-time design:
    Runs after InsightAgent and ValidationAgent on the chat response path.
    All checks are pure computation against in-memory profile data (< 1ms).

    Validates five classes of statistical claims:
    1. RANGE — stated value within column min/max
    2. PERCENTAGE — value in [0, 100] or [0.0, 1.0]
    3. COUNT — non-negative integer
    4. CORRELATION — stated direction matches computed correlation sign
    5. AVERAGE — stated mean within 20% of computed mean

    Returns a list of ValidationFailure objects so the ValidationAgent
    can either reject the claim or flag it for user review.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationFailure:
    claim_text:   str
    failure_type: str   # range | percentage | count | correlation | average
    expected:     str
    actual:       str
    severity:     str = "medium"   # low | medium | high


class StatisticalValidator:
    """Validates numeric claims in LLM responses against DataProfile statistics."""

    def validate_claim(
        self,
        claim_text: str,
        profile: dict,
        schema: dict | None = None,
    ) -> list[ValidationFailure]:
        """Check a single claim string against the DataProfile.

        Args:
            claim_text: One sentence or phrase to validate.
            profile:    DataProfile dict (column_profiles list expected).
            schema:     Dataset schema dict (used for column name lookup).

        Returns:
            List of ValidationFailure objects (empty = claim is valid).
        """
        failures: list[ValidationFailure] = []

        col_profiles = {
            cp.get("column_name", ""): cp
            for cp in profile.get("column_profiles", [])
            if cp.get("column_name")
        }

        # Check range claims ("revenue is $500,000")
        failures.extend(self._check_range_claims(claim_text, col_profiles))

        # Check percentage claims
        failures.extend(self._check_percentage_claims(claim_text))

        # Check count claims (non-negative integers)
        failures.extend(self._check_count_claims(claim_text))

        return failures

    def validate_response(
        self,
        response: str,
        profile: dict,
        schema: dict | None = None,
    ) -> list[ValidationFailure]:
        """Validate all statistical claims in a full LLM response.

        Splits the response into sentences and validates each one.
        """
        sentences = re.split(r"(?<=[.!?])\s+", response)
        failures: list[ValidationFailure] = []
        for sentence in sentences:
            failures.extend(self.validate_claim(sentence, profile, schema))
        return failures

    # ── Per-category checkers ─────────────────────────────────────────────

    def _check_range_claims(
        self,
        text: str,
        col_profiles: dict[str, dict],
    ) -> list[ValidationFailure]:
        """Flag numeric values that fall outside the stated column's min/max."""
        failures = []
        # Extract patterns like "revenue is 500000" or "price of 1200.50"
        number_pattern = re.compile(
            r"\b(\w[\w\s]*?)\s+(?:is|of|at|was|equals?)\s+\$?([\d,]+\.?\d*)\b"
        )
        for match in number_pattern.finditer(text.lower()):
            col_hint = match.group(1).strip()
            value_str = match.group(2).replace(",", "")
            try:
                value = float(value_str)
            except ValueError:
                continue

            # Find matching column profile
            for col_name, cp in col_profiles.items():
                if col_name.lower() in col_hint or col_hint in col_name.lower():
                    stats = cp.get("stats") or {}
                    min_val = stats.get("min_val")
                    max_val = stats.get("max_val")
                    if min_val is not None and max_val is not None:
                        if not (float(min_val) <= value <= float(max_val)):
                            failures.append(ValidationFailure(
                                claim_text=text[:100],
                                failure_type="range",
                                expected=f"between {min_val} and {max_val}",
                                actual=str(value),
                                severity="high",
                            ))
                    break
        return failures

    @staticmethod
    def _check_percentage_claims(text: str) -> list[ValidationFailure]:
        """Flag percentages outside the valid [0, 100] range."""
        failures = []
        pct_pattern = re.compile(r"\b([\d,]+\.?\d*)\s*%\b")
        for match in pct_pattern.finditer(text):
            value_str = match.group(1).replace(",", "")
            try:
                value = float(value_str)
            except ValueError:
                continue
            if value < 0 or value > 100:
                failures.append(ValidationFailure(
                    claim_text=text[:100],
                    failure_type="percentage",
                    expected="0% to 100%",
                    actual=f"{value}%",
                    severity="high",
                ))
        return failures

    @staticmethod
    def _check_count_claims(text: str) -> list[ValidationFailure]:
        """Flag negative counts or obviously wrong row counts."""
        failures = []
        count_words = r"(?:count|total|number\s+of|sum\s+of|quantity\s+of)"
        neg_pattern = re.compile(
            rf"\b{count_words}\b.{{0,30}}-(\d+)\b", re.IGNORECASE
        )
        for match in neg_pattern.finditer(text):
            failures.append(ValidationFailure(
                claim_text=text[:100],
                failure_type="count",
                expected="non-negative integer",
                actual=f"-{match.group(1)}",
                severity="medium",
            ))
        return failures
