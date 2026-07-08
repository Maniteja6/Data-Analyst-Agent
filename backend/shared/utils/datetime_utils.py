"""Datetime utilities.

All timestamps in DataPilot are stored and compared as UTC.
These helpers enforce that convention and provide consistent
ISO-8601 formatting across the codebase.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

# ---------------------------------------------------------------------------
# Now
# ---------------------------------------------------------------------------


def utcnow() -> datetime:
    """Return the current UTC datetime as a timezone-aware object.

    Always use this instead of ``datetime.utcnow()`` (which returns a
    naive datetime and is deprecated in Python 3.12).
    """
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def to_iso8601(dt: datetime) -> str:
    """Serialise a datetime to an ISO-8601 string with UTC offset.

    Example: ``'2024-11-01T14:32:00+00:00'``

    Args:
        dt: A timezone-aware datetime. If naive, it is assumed to be UTC.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def from_iso8601(value: str) -> datetime:
    """Parse an ISO-8601 string into a timezone-aware UTC datetime.

    Handles both offset-aware strings (``'2024-11-01T14:32:00+00:00'``)
    and naive UTC strings (``'2024-11-01T14:32:00'``).
    """
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------


def is_past(dt: datetime) -> bool:
    """Return True if ``dt`` is before the current UTC time."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt < utcnow()


def is_future(dt: datetime) -> bool:
    """Return True if ``dt`` is after the current UTC time."""
    return not is_past(dt)


def seconds_since(dt: datetime) -> float:
    """Return the number of seconds elapsed since ``dt``."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return (utcnow() - dt).total_seconds()


def add_seconds(dt: datetime, seconds: int) -> datetime:
    """Return a new datetime offset by ``seconds`` from ``dt``."""
    return dt + timedelta(seconds=seconds)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def format_human(dt: datetime) -> str:
    """Return a human-readable UTC string, e.g. ``'2024-11-01 14:32 UTC'``."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def date_only(dt: datetime) -> str:
    """Return only the date portion as ``'YYYY-MM-DD'``."""
    return dt.strftime("%Y-%m-%d")
