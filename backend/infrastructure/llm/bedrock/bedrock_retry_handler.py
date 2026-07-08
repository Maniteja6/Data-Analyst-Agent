"""Exponential-backoff retry decorator for AWS Bedrock API calls.

Bedrock has per-account and per-model invocation rate limits that vary by
model and region. When requests exceed those limits, Bedrock returns a
``ThrottlingException``. This decorator retries transparently with jittered
exponential backoff so agent code doesn't need to handle throttling itself.

Retryable error codes
---------------------
ThrottlingException          — per-minute or burst rate limit exceeded
ModelNotReadyException       — model is warming up (rare; usually sub-second)
ServiceUnavailableException  — transient Bedrock service disruption
InternalServerException      — transient Bedrock server error
TooManyRequestsException     — alias for throttling in some SDK versions

Non-retryable errors (propagated immediately)
---------------------------------------------
ValidationError          — malformed request; retrying won't help
ModelErrorException          — model returned a hard error (e.g. content policy)
AccessDeniedException        — IAM permission missing; fix the role before retrying
ResourceNotFoundException    — model ID does not exist in this region

Jitter strategy
---------------
``delay = base_delay * 2^(attempt - 1) + random_jitter``
where ``random_jitter ∈ [0, delay * 0.5]``.

Full jitter (randomising the entire delay) is more aggressive but can
produce very short delays on early retries. Half jitter keeps the minimum
backoff floor while reducing thundering-herd collisions in multi-worker envs.

Usage
-----
Apply the ``@with_bedrock_retry`` decorator to any ``async`` function that
calls a Bedrock API method::

    @with_bedrock_retry
    async def my_bedrock_call(client, model_id: str, prompt: str) -> str:
        response = client.converse(modelId=model_id, messages=[...])
        return response["output"]["message"]["content"][0]["text"]

The decorator is already applied in ``BedrockConverseAdapter.complete()``,
``BedrockStreamAdapter.stream()``, and ``BedrockEmbeddingAdapter.embed()``.
Do not stack decorators — applying it to an adapter method and again to a
caller will double the retry count.
"""

from __future__ import annotations

import asyncio
import functools
import random
from collections.abc import Callable
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Error codes that warrant a retry attempt
RETRYABLE_ERROR_CODES: frozenset[str] = frozenset(
    {
        "ThrottlingException",
        "ServiceUnavailableException",
        "ModelNotReadyException",
        "InternalServerException",
        "TooManyRequestsException",
        "RequestThrottledException",  # some SDK versions use this alias
    }
)

# Error codes that should be propagated without retrying
NON_RETRYABLE_ERROR_CODES: frozenset[str] = frozenset(
    {
        "ValidationError",
        "ModelErrorException",
        "AccessDeniedException",
        "ResourceNotFoundException",
        "ModelStreamErrorException",
    }
)


def with_bedrock_retry(
    fn: Callable[..., Any] | None = None, *, max_retries: int | None = None
) -> Callable[..., Any]:
    """Decorator that retries Bedrock API calls on transient errors.

    Can be applied with or without arguments::

        @with_bedrock_retry
        async def my_fn(): ...

        @with_bedrock_retry(max_retries=2)
        async def my_fn(): ...

    Args:
        fn:          The async function to wrap (when used without parentheses).
        max_retries: Override the default retry count from ``BedrockConfig``.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
            from backend.config.bedrock_config import get_bedrock_config
            from botocore.exceptions import ClientError

            cfg = get_bedrock_config()
            retries = max_retries if max_retries is not None else cfg.bedrock_max_retries
            base_del = cfg.bedrock_retry_base_delay_seconds
            max_del = cfg.bedrock_retry_max_delay_seconds

            last_exc: Exception | None = None

            for attempt in range(1, retries + 1):
                try:
                    return await func(*args, **kwargs)

                except ClientError as exc:
                    error_code = exc.response.get("Error", {}).get("Code", "Unknown")

                    # Non-retryable — propagate immediately
                    if error_code in NON_RETRYABLE_ERROR_CODES:
                        logger.error(
                            "bedrock_non_retryable_error",
                            error_code=error_code,
                            attempt=attempt,
                        )
                        raise

                    # Unknown error — propagate on final attempt only
                    if error_code not in RETRYABLE_ERROR_CODES:
                        logger.warning(
                            "bedrock_unknown_error_code",
                            error_code=error_code,
                            attempt=attempt,
                        )
                        if attempt == retries:
                            raise
                        last_exc = exc
                    else:
                        last_exc = exc

                    if attempt == retries:
                        logger.error(
                            "bedrock_max_retries_exceeded",
                            error_code=error_code,
                            attempts=retries,
                        )
                        raise

                    # Compute jittered backoff delay
                    exponential = base_del * (2 ** (attempt - 1))
                    jitter = random.uniform(0, exponential * 0.5)  # noqa: S311 — retry-backoff jitter, not cryptographic
                    delay = min(exponential + jitter, max_del)

                    logger.warning(
                        "bedrock_retry",
                        error_code=error_code,
                        attempt=attempt,
                        max_retries=retries,
                        delay_seconds=round(delay, 2),
                        fn=func.__name__,
                    )
                    await asyncio.sleep(delay)

                except asyncio.CancelledError:
                    # Never swallow CancelledError — propagate immediately
                    raise

                except Exception as exc:
                    # Non-ClientError (e.g. network error, asyncio timeout)
                    # Retry with the same backoff schedule
                    last_exc = exc
                    if attempt == retries:
                        logger.error(
                            "bedrock_unexpected_error_max_retries",
                            error=str(exc),
                            error_type=type(exc).__name__,
                            attempts=retries,
                        )
                        raise

                    exponential = base_del * (2 ** (attempt - 1))
                    jitter = random.uniform(0, exponential * 0.5)  # noqa: S311 — retry-backoff jitter, not cryptographic
                    delay = min(exponential + jitter, max_del)

                    logger.warning(
                        "bedrock_unexpected_error_retry",
                        error=str(exc),
                        error_type=type(exc).__name__,
                        attempt=attempt,
                        delay_seconds=round(delay, 2),
                    )
                    await asyncio.sleep(delay)

            # Should never reach here, but satisfy the type checker
            if last_exc:
                raise last_exc
            raise RuntimeError(f"Retry loop exited without result: {func.__name__}")

        return wrapper

    # Support both @with_bedrock_retry and @with_bedrock_retry(max_retries=2)
    if fn is not None:
        return decorator(fn)
    return decorator
