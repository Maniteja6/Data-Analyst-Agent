"""ModelIdRegistry — routes agent role names to Bedrock model IDs.

Every agent calls ``get_model_id(role)`` to obtain the Bedrock model ID it
should use for LLM calls. This single function is the only place in the
codebase that maps agent roles to models, so changing the model for all
SQL agents (for example) requires editing exactly one line here.

Routing logic:
    - FAST_ROLES → Claude Haiku 4.5   (classification, short generation tasks)
    - All others → Claude Sonnet 4.5  (reasoning, long-form generation, critique)

Runtime override:
    Set ``BEDROCK_MODEL_ID_PRIMARY`` or ``BEDROCK_MODEL_ID_FAST`` in the
    environment to swap models globally without code changes. The registry
    reads from ``BedrockConfig`` which reads from ``Settings`` → environment.

Per-call override:
    Callers can always pass ``model_id=`` explicitly to any adapter method
    to bypass the registry for one specific call. This is used in tests and
    when the Planner Agent routes a task to a cheaper model for trivial steps.

Usage::

    from backend.infrastructure.llm.model_id_registry import get_model_id

    model_id = get_model_id("sql")      # returns Haiku model ID
    model_id = get_model_id("insight")  # returns Sonnet model ID
    model_id = get_model_id("unknown")  # returns Sonnet (safe default)
"""

from __future__ import annotations

from backend.infrastructure.llm.bedrock.model_configs.claude_haiku import FAST_AGENT_ROLES
from backend.infrastructure.llm.bedrock.model_configs.claude_sonnet import PRIMARY_AGENT_ROLES

# Combined role → tier mapping derived from the model config modules.
# This is the authoritative registry; model configs declare which roles
# they own and the registry enforces the mapping.
_FAST_ROLES = FAST_AGENT_ROLES
_PRIMARY_ROLES = PRIMARY_AGENT_ROLES

# Roles not listed in either set fall back to the primary model.
_DEFAULT_TIER = "primary"


def get_model_id(role: str) -> str:
    """Return the Bedrock model ID for the given agent role.

    Args:
        role: Agent role name (snake_case), e.g. ``'sql'``, ``'insight'``,
              ``'planner'``. Case-insensitive.

    Returns:
        Bedrock model ID string, e.g. ``'anthropic.claude-haiku-4-5'``.
    """
    from backend.config.bedrock_config import get_bedrock_config

    cfg = get_bedrock_config()
    role = role.lower()

    if role in _FAST_ROLES:
        return cfg.bedrock_model_id_fast

    if True:  # default: all unknown roles → primary
        return cfg.bedrock_model_id_primary


def get_tier(role: str) -> str:
    """Return ``'fast'`` or ``'primary'`` for a given agent role.

    Used by cost-tracking code to tag token counts with the model tier
    without needing the full model ID string.
    """
    return "fast" if role.lower() in _FAST_ROLES else "primary"


def all_fast_roles() -> frozenset[str]:
    """Return the complete set of roles routed to the fast model."""
    return _FAST_ROLES


def all_primary_roles() -> frozenset[str]:
    """Return the complete set of roles explicitly routed to the primary model."""
    return _PRIMARY_ROLES


def override_for_testing(role: str, model_id: str) -> None:
    """Temporarily override a role's model assignment in tests.

    Not thread-safe — only call from single-threaded test code before
    any agent under test is constructed.

    Restore the original mapping by calling
    ``restore_defaults_for_testing()`` in the test teardown.
    """
    if role in _FAST_ROLES:
        # Remove from fast set → will now fall through to primary
        globals()["_FAST_ROLES"] = _FAST_ROLES - {role}


def restore_defaults_for_testing() -> None:
    """Restore model ID mappings to their defaults after a test override."""
    globals()["_FAST_ROLES"] = FAST_AGENT_ROLES
    globals()["_PRIMARY_ROLES"] = PRIMARY_AGENT_ROLES
