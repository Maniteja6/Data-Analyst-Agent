"""SemanticType value object — domain-level column type classification."""

from __future__ import annotations

from enum import StrEnum


class SemanticType(StrEnum):
    """Domain-level semantic type of a dataset column.

    Inferred by the SchemaAgent (LLM + rule-based heuristics).
    Drives agent routing — e.g. currency columns get specialised
    aggregation prompts, datetime columns trigger the Forecast agent.

    Grouped by kind:
    - Identifiers:       IDENTIFIER
    - Quantitative:      CURRENCY, PERCENTAGE, NUMERIC_MEASURE, NUMERIC_COUNT
    - Temporal:          DATE, DATETIME, DURATION
    - Qualitative:       CATEGORICAL, FREE_TEXT, BOOLEAN
    - Contact / PII:     EMAIL, PHONE, GEOGRAPHIC, URL
    - Fallback:          UNKNOWN
    """

    # ── Identifiers ───────────────────────────────────────────────────────
    IDENTIFIER = "identifier"
    """Primary or foreign key — high cardinality, usually not analysed."""

    # ── Quantitative ──────────────────────────────────────────────────────
    CURRENCY = "currency"
    """Monetary amount — e.g. price, revenue, cost.
    Insight Agent uses currency formatting and non-negative validation."""

    PERCENTAGE = "percentage"
    """Rate or ratio stored as 0-100 or 0.0-1.0."""

    NUMERIC_MEASURE = "numeric_measure"
    """Continuous numeric measurement — temperature, weight, score."""

    NUMERIC_COUNT = "numeric_count"
    """Discrete non-negative count — quantity, clicks, page_views."""

    # ── Temporal ──────────────────────────────────────────────────────────
    DATE = "date"
    """Calendar date without time component."""

    DATETIME = "datetime"
    """Date and time — triggers Forecast Agent if present."""

    DURATION = "duration"
    """Time span — e.g. session_duration_seconds."""

    # ── Qualitative ───────────────────────────────────────────────────────
    CATEGORICAL = "categorical"
    """Low-cardinality text — country, product_category, status."""

    FREE_TEXT = "free_text"
    """High-cardinality unstructured text — comments, descriptions."""

    BOOLEAN = "boolean"
    """True/False or Yes/No column."""

    # ── Contact / PII ─────────────────────────────────────────────────────
    EMAIL = "email"
    """Email address — triggers PII redaction in the Security Agent."""

    PHONE = "phone"
    """Phone number — triggers PII redaction."""

    GEOGRAPHIC = "geographic"
    """Location string — city, country, lat/lon pair."""

    URL = "url"
    """Web address."""

    # ── Fallback ──────────────────────────────────────────────────────────
    UNKNOWN = "unknown"
    """Could not be classified — LLM disambiguation attempted next."""

    # ── Derived helpers ───────────────────────────────────────────────────

    @property
    def is_numeric(self) -> bool:
        """True for all quantitative types that support arithmetic operations."""
        return self in (
            SemanticType.CURRENCY,
            SemanticType.PERCENTAGE,
            SemanticType.NUMERIC_MEASURE,
            SemanticType.NUMERIC_COUNT,
        )

    @property
    def is_temporal(self) -> bool:
        return self in (SemanticType.DATE, SemanticType.DATETIME, SemanticType.DURATION)

    @property
    def is_pii(self) -> bool:
        """True for types that may contain personally identifiable information."""
        return self in (SemanticType.EMAIL, SemanticType.PHONE, SemanticType.IDENTIFIER)

    @property
    def triggers_forecast(self) -> bool:
        """True when this column should be offered as a time axis for the Forecast Agent."""
        return self in (SemanticType.DATE, SemanticType.DATETIME)

    @property
    def display_label(self) -> str:
        """Human-readable label for the frontend schema table."""
        return self.value.replace("_", " ").title()
