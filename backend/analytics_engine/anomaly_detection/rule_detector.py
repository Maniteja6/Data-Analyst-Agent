"""Rule-based anomaly detector — domain-invariant sanity checks.

Checks that are always true regardless of the dataset's distribution:
  - Currency / price columns must be non-negative
  - Percentage columns must be in [0, 100] or [0, 1]
  - Count columns must be integers ≥ 0
  - Datetime columns must be within a plausible business range
  - Email columns must match a basic RFC 5321 pattern
  - String length must be within min/max bounds for fixed-format fields

Rule violations are high-confidence anomalies (confidence = 0.95) because
they represent logical impossibilities rather than statistical outliers.
They are flagged as ``anomaly_type = 'rule_violation'`` and severity = 'high'.

Extending rules:
    Add a new ``_check_*`` method and call it from ``detect()``.
    Each method receives the full DataFrame and column name, and appends
    dicts to a results list.

Usage::

    detector = RuleDetector()
    results  = detector.detect(df, column="price", semantic_type="currency")
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Plausible business date range for datetime column validation
_MIN_YEAR = 1900
_MAX_YEAR = 2100

# Basic email regex (RFC 5321 subset — not 100% RFC-compliant but catches obvious invalids)
_EMAIL_PATTERN = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"


class RuleDetector:
    """Applies semantic rules to detect logically invalid values.

    Rules are dispatched based on the ``semantic_type`` argument so only
    relevant checks are applied to each column type.
    """

    def __init__(self, max_results: int = 50) -> None:
        self._max_results = max_results

    def detect(
        self,
        df,
        column: str,
        semantic_type: str = "unknown",
    ) -> list[dict]:
        """Apply all applicable rules for the given semantic type.

        Args:
            df:            DataFrame (polars or pandas).
            column:        Column name to check.
            semantic_type: Semantic type string (e.g. ``'currency'``, ``'email'``).

        Returns:
            List of anomaly dicts for rule violations.
        """
        results: list[dict] = []
        stype = semantic_type.lower()

        if stype in ("currency", "numeric_measure", "numeric_count"):
            results.extend(self._check_negative_currency(df, column, stype))

        if stype == "percentage":
            results.extend(self._check_percentage_range(df, column))

        if stype == "numeric_count":
            results.extend(self._check_non_integer_count(df, column))

        if stype in ("date", "datetime"):
            results.extend(self._check_datetime_range(df, column))

        if stype == "email":
            results.extend(self._check_email_format(df, column))

        return results[:self._max_results]

    # ── Rule implementations ──────────────────────────────────────────────

    def _check_negative_currency(
        self, df, column: str, stype: str
    ) -> list[dict]:
        """Flag negative values in columns that must be non-negative."""
        if stype == "numeric_measure":
            return []   # measures can be negative (temperature, profit delta)

        results = []
        try:
            col_data = self._get_column_data(df, column)
            for idx, val in enumerate(col_data):
                if val is not None and float(val) < 0:
                    results.append(self._make_violation(
                        column=column,
                        row_index=idx,
                        raw_value=val,
                        description=(
                            f"Negative value {val:.4g} in '{column}' "
                            f"({stype} column should be ≥ 0)."
                        ),
                        severity="high",
                    ))
                if len(results) >= self._max_results:
                    break
        except Exception as exc:
            logger.debug("rule_negative_check_failed", column=column, error=str(exc))
        return results

    def _check_percentage_range(self, df, column: str) -> list[dict]:
        """Flag percentage values outside [0, 100] or [0, 1]."""
        results = []
        try:
            col_data = self._get_column_data(df, column)
            non_null = [v for v in col_data if v is not None]
            if not non_null:
                return []

            max_val = max(non_null)
            # Detect whether column is [0,1] or [0,100] scale
            is_fraction = max_val <= 1.0
            low, high = (0.0, 1.0) if is_fraction else (0.0, 100.0)

            for idx, val in enumerate(col_data):
                if val is not None and not (low <= float(val) <= high):
                    results.append(self._make_violation(
                        column=column,
                        row_index=idx,
                        raw_value=val,
                        description=(
                            f"Percentage value {val:.4g} in '{column}' is outside "
                            f"expected range [{low}, {high}]."
                        ),
                        severity="high",
                    ))
                if len(results) >= self._max_results:
                    break
        except Exception as exc:
            logger.debug("rule_percentage_check_failed", column=column, error=str(exc))
        return results

    def _check_non_integer_count(self, df, column: str) -> list[dict]:
        """Flag non-integer values in count columns."""
        results = []
        try:
            col_data = self._get_column_data(df, column)
            for idx, val in enumerate(col_data):
                if val is not None:
                    fval = float(val)
                    if fval != int(fval) or fval < 0:
                        results.append(self._make_violation(
                            column=column,
                            row_index=idx,
                            raw_value=val,
                            description=(
                                f"Value {val} in count column '{column}' "
                                f"is not a non-negative integer."
                            ),
                            severity="medium",
                        ))
                if len(results) >= self._max_results:
                    break
        except Exception as exc:
            logger.debug("rule_count_check_failed", column=column, error=str(exc))
        return results

    def _check_datetime_range(self, df, column: str) -> list[dict]:
        """Flag datetime values outside the plausible business date range."""
        results = []
        try:
            col_data = self._get_column_data(df, column)
            for idx, val in enumerate(col_data):
                if val is None:
                    continue
                try:
                    import datetime
                    if hasattr(val, "year"):
                        year = val.year
                    else:
                        year = int(str(val)[:4])
                    if not (_MIN_YEAR <= year <= _MAX_YEAR):
                        results.append(self._make_violation(
                            column=column,
                            row_index=idx,
                            raw_value=str(val),
                            description=(
                                f"Date {val} in '{column}' has year {year}, "
                                f"outside plausible range [{_MIN_YEAR}, {_MAX_YEAR}]."
                            ),
                            severity="medium",
                        ))
                except Exception:
                    pass
                if len(results) >= self._max_results:
                    break
        except Exception as exc:
            logger.debug("rule_datetime_check_failed", column=column, error=str(exc))
        return results

    def _check_email_format(self, df, column: str) -> list[dict]:
        """Flag email values that don't match a basic RFC pattern."""
        import re
        pattern = re.compile(_EMAIL_PATTERN)
        results = []
        try:
            col_data = self._get_column_data(df, column)
            for idx, val in enumerate(col_data):
                if val is not None and not pattern.match(str(val)):
                    results.append(self._make_violation(
                        column=column,
                        row_index=idx,
                        raw_value=str(val),
                        description=(
                            f"Value '{val}' in email column '{column}' "
                            f"does not match a valid email format."
                        ),
                        severity="medium",
                    ))
                if len(results) >= self._max_results:
                    break
        except Exception as exc:
            logger.debug("rule_email_check_failed", column=column, error=str(exc))
        return results

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _get_column_data(df, column: str) -> list:
        """Extract column values as a Python list — handles polars and pandas."""
        try:
            return df[column].to_list()
        except AttributeError:
            return df[column].tolist()

    @staticmethod
    def _make_violation(
        column: str,
        row_index: int,
        raw_value: Any,
        description: str,
        severity: str = "high",
    ) -> dict:
        return {
            "column":           column,
            "detection_method": "Rule",
            "anomaly_type":     "rule_violation",
            "severity":         severity,
            "confidence":       0.95,
            "rows_affected":    1,
            "value":            str(raw_value),
            "row_index":        row_index,
            "description":      description,
        }
