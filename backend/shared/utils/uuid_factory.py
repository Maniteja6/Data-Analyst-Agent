"""UUID generation utilities.

Centralising UUID creation here means tests can mock ``new_uuid`` once
and control all ID generation across the codebase, rather than patching
``uuid.uuid4`` everywhere.
"""
from __future__ import annotations

import uuid


def new_uuid() -> str:
    """Return a new random UUID4 as a lowercase hyphenated string.

    This is the standard ID format used for all entities in DataPilot:
    ``'550e8400-e29b-41d4-a716-446655440000'``
    """
    return str(uuid.uuid4())


def new_short_id(length: int = 8) -> str:
    """Return a short random hex ID of the given length.

    Useful for human-readable identifiers such as job codes or
    short report names where a full UUID is unnecessarily verbose.

    Example: ``'a3f2b1c4'`` (length=8, the default)
    """
    if not 1 <= length <= 32:
        raise ValueError(f"length must be between 1 and 32, got {length}")
    return uuid.uuid4().hex[:length]


def is_valid_uuid(value: str) -> bool:
    """Return True if ``value`` is a valid UUID string in any standard form."""
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False
