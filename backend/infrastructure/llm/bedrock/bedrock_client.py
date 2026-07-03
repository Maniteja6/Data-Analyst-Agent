"""Bedrock Runtime boto3 client — singleton factory with IRSA credential chain.

All Bedrock adapters (Converse, Stream, Embeddings) obtain the client via
``get_bedrock_runtime_client()``. Using a single shared boto3 client per
process ensures:

- The credential chain (IRSA → instance profile → env vars) is resolved once
- No per-request credential refresh overhead
- boto3 connection pool is shared across all callers

IRSA (IAM Roles for Service Accounts) configuration:
    In EKS, the pod annotation ``eks.amazonaws.com/role-arn`` causes the AWS
    SDK to pick up a projected service account token automatically. No
    ``AWS_ACCESS_KEY_ID`` or ``AWS_SECRET_ACCESS_KEY`` environment variables
    are needed (and must not be set in production).

    For local development with the MinIO/LocalStack stack, the credential
    chain falls through to ``~/.aws/credentials`` or environment variables.

Regional endpoint:
    The client uses the standard Bedrock Runtime regional endpoint:
        https://bedrock-runtime.<region>.amazonaws.com

    When ``Settings.s3_endpoint_url`` (or ``BedrockConfig.bedrock_endpoint_url``)
    is set, the override endpoint is used instead — useful for local mocking
    with ``LocalStack``.

Thread safety:
    ``boto3.client()`` instances are thread-safe for concurrent API calls.
    The ``@lru_cache`` ensures a single instance is created even under
    concurrent import (Python GIL protects the cache write).

Usage::

    from backend.infrastructure.llm.bedrock.bedrock_client import get_bedrock_runtime_client

    client = get_bedrock_runtime_client()
    response = client.converse(modelId="anthropic.claude-sonnet-4-5", messages=[...])
"""
from __future__ import annotations

from functools import lru_cache

import structlog

logger = structlog.get_logger(__name__)


@lru_cache(maxsize=1)
def get_bedrock_runtime_client():
    """Return the cached boto3 Bedrock Runtime client.

    Uses the AWS default credential provider chain:
        1. IRSA projected service account token (EKS production)
        2. EC2 instance profile
        3. ``AWS_ACCESS_KEY_ID`` + ``AWS_SECRET_ACCESS_KEY`` env vars
        4. ``~/.aws/credentials`` file (local development)

    Raises:
        botocore.exceptions.NoCredentialsError: When no credentials are found.
        botocore.exceptions.ClientError: On first API call if credentials lack
            ``bedrock:InvokeModel`` permission.
    """
    import boto3
    from backend.config.bedrock_config import get_bedrock_config

    cfg    = get_bedrock_config()
    kwargs = {"region_name": cfg.bedrock_region}

    if cfg.bedrock_endpoint_url:
        kwargs["endpoint_url"] = cfg.bedrock_endpoint_url
        logger.info(
            "bedrock_custom_endpoint",
            endpoint=cfg.bedrock_endpoint_url,
            region=cfg.bedrock_region,
        )

    client = boto3.client("bedrock-runtime", **kwargs)
    logger.info("bedrock_client_created", region=cfg.bedrock_region)
    return client


def reset_client() -> None:
    """Clear the cached client — call in tests that mock boto3.

    Example::

        with mock.patch("boto3.client") as mock_boto:
            mock_boto.return_value = MagicMock()
            reset_client()                        # force re-creation
            client = get_bedrock_runtime_client() # returns the mock
    """
    get_bedrock_runtime_client.cache_clear()
    logger.debug("bedrock_client_cache_cleared")
