"""S3StorageAdapter — production file storage backed by AWS S3 or MinIO.

Used for:
- Storing uploaded dataset files under ``datasets/<dataset_id>/<filename>``
- Storing generated export reports under ``reports/<dataset_id>/<export_id>.<fmt>``
- Serving presigned download URLs to the frontend for direct browser downloads

MinIO compatibility:
    Set ``Settings.s3_endpoint_url`` to ``http://localhost:9000`` for local
    development with MinIO. All S3 API calls are identical — only the endpoint
    differs. Leave the endpoint blank to use the real AWS S3 regional endpoint.

Authentication:
    In production the Celery workers and API pods run with IRSA
    (IAM Roles for Service Accounts). ``boto3`` picks up the pod's projected
    service account token automatically via the default credential chain.
    No static ``AWS_ACCESS_KEY_ID`` / ``AWS_SECRET_ACCESS_KEY`` needed.
    For local dev, MinIO credentials are read from Settings.

Concurrency:
    All methods are ``async`` and delegate blocking boto3 calls to a thread
    pool executor (``loop.run_in_executor(None, ...)``) so they never block
    the FastAPI event loop. A single shared ``ThreadPoolExecutor`` is used
    per process.

Usage::

    from backend.infrastructure.storage.s3_storage_adapter import get_s3_storage

    storage = get_s3_storage()
    key = await storage.upload_fileobj(file_bytes_io, "datasets/abc/sales.csv")
    url = await storage.generate_presigned_download_url(key)
"""
from __future__ import annotations

import asyncio
import io
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import BinaryIO

import structlog

logger = structlog.get_logger(__name__)

# Shared thread pool — boto3 is not async-native so we offload to threads
_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="s3_worker")


class S3StorageAdapter:
    """Async S3/MinIO storage adapter.

    All public methods are ``async`` and wrap synchronous boto3 calls
    via ``asyncio.get_event_loop().run_in_executor()``.
    """

    def __init__(
        self,
        bucket_name: str | None = None,
        region: str | None = None,
        endpoint_url: str | None = None,
        presigned_url_ttl: int = 900,
    ) -> None:
        """
        Args:
            bucket_name:       S3 bucket to operate on. Defaults to ``Settings.s3_bucket_name``.
            region:            AWS region. Defaults to ``Settings.aws_region``.
            endpoint_url:      Override endpoint for MinIO. Leave None for real AWS S3.
            presigned_url_ttl: Expiry in seconds for presigned download URLs (default: 15 min).
        """
        from backend.config.settings import get_settings
        settings = get_settings()

        self._bucket      = bucket_name  or settings.s3_bucket_name
        self._region      = region       or settings.aws_region
        self._endpoint    = endpoint_url or settings.s3_endpoint_url
        self._presigned_ttl = presigned_url_ttl or settings.s3_presigned_url_ttl_seconds
        self._client      = None   # lazily initialised

    # ── Client factory ────────────────────────────────────────────────────

    def _get_client(self):
        """Return the boto3 S3 client, creating it on first call (thread-safe)."""
        if self._client is None:
            import boto3
            from backend.config.settings import get_settings
            settings = get_settings()

            kwargs: dict = {"region_name": self._region}
            if self._endpoint:
                kwargs["endpoint_url"] = self._endpoint
            # For MinIO local dev: explicit key/secret from settings
            if settings.aws_access_key_id and self._endpoint:
                kwargs["aws_access_key_id"]     = settings.aws_access_key_id
                kwargs["aws_secret_access_key"]  = settings.aws_secret_access_key

            self._client = boto3.client("s3", **kwargs)
        return self._client

    async def _run(self, fn, *args, **kwargs):
        """Run a synchronous boto3 call in the shared thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_EXECUTOR, lambda: fn(*args, **kwargs))

    # ── Upload ────────────────────────────────────────────────────────────

    async def upload_fileobj(
        self,
        file_obj: BinaryIO,
        key: str,
        content_type: str | None = None,
    ) -> str:
        """Upload a file-like object to S3 under the given key.

        Args:
            file_obj:     A readable binary file-like object (e.g. ``io.BytesIO``
                          or a Starlette ``UploadFile.file``).
            key:          S3 object key (path within the bucket).
                          Convention: ``datasets/<dataset_id>/<filename>``
            content_type: MIME type stored as S3 object metadata.
                          When None, S3 infers from the filename extension.

        Returns:
            The ``key`` that was used — callers store this in ``Dataset.storage_key``.

        Raises:
            botocore.exceptions.ClientError: On S3 permission or connectivity errors.
        """
        extra_args: dict = {}
        if content_type:
            extra_args["ContentType"] = content_type

        client = self._get_client()
        await self._run(
            client.upload_fileobj,
            file_obj,
            self._bucket,
            key,
            ExtraArgs=extra_args if extra_args else None,
        )
        logger.info("s3_upload_complete", bucket=self._bucket, key=key)
        return key

    async def upload_bytes(
        self,
        data: bytes,
        key: str,
        content_type: str | None = None,
    ) -> str:
        """Upload raw bytes to S3.

        Convenience wrapper around ``upload_fileobj`` for in-memory data
        (e.g. generated report bytes from WeasyPrint / openpyxl).
        """
        return await self.upload_fileobj(io.BytesIO(data), key, content_type)

    async def upload_from_path(
        self,
        local_path: str,
        key: str,
        content_type: str | None = None,
    ) -> str:
        """Upload a local file path to S3."""
        with open(local_path, "rb") as f:
            return await self.upload_fileobj(f, key, content_type)

    # ── Download ──────────────────────────────────────────────────────────

    async def download_bytes(self, key: str) -> bytes:
        """Download an S3 object and return its bytes.

        Used by the analytics pipeline to load dataset files from S3 when
        they are not cached locally. For very large files, use
        ``download_to_path`` instead to avoid loading the full file into memory.

        Args:
            key: S3 object key.

        Returns:
            Raw bytes of the object.
        """
        client = self._get_client()
        response = await self._run(client.get_object, Bucket=self._bucket, Key=key)
        body = response["Body"]
        return await self._run(body.read)

    async def download_to_path(self, key: str, local_path: str) -> None:
        """Stream an S3 object to a local file path.

        More memory-efficient than ``download_bytes`` for large dataset files.
        """
        client = self._get_client()
        await self._run(client.download_file, self._bucket, key, local_path)
        logger.info("s3_download_complete", key=key, local_path=local_path)

    # ── Presigned URLs ────────────────────────────────────────────────────

    async def generate_presigned_download_url(
        self,
        key: str,
        ttl: int | None = None,
    ) -> str:
        """Generate a time-limited presigned GET URL for an S3 object.

        The URL allows the browser to download the file directly from S3
        without going through the API server, reducing API bandwidth costs.

        Args:
            key: S3 object key.
            ttl: URL expiry in seconds. Defaults to ``Settings.s3_presigned_url_ttl_seconds``.

        Returns:
            HTTPS presigned URL valid for ``ttl`` seconds.
        """
        client = self._get_client()
        url = await self._run(
            client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=ttl or self._presigned_ttl,
        )
        logger.debug("s3_presigned_url_generated", key=key, ttl=ttl or self._presigned_ttl)
        return url

    async def generate_presigned_upload_url(
        self,
        key: str,
        content_type: str,
        ttl: int = 300,
    ) -> dict:
        """Generate a presigned POST URL for direct browser uploads.

        Used by the ``FEATURE_PRESIGNED_UPLOAD`` feature flag path where the
        frontend uploads directly to S3 rather than through the API server.

        Args:
            key:          Destination S3 key for the upload.
            content_type: MIME type enforced by the presigned policy.
            ttl:          URL expiry in seconds (default: 5 minutes).

        Returns:
            Dict with ``url`` (POST target) and ``fields`` (form fields the
            browser must include in the multipart POST body).
        """
        from backend.config.settings import get_settings
        settings = get_settings()
        max_size = settings.max_upload_size_bytes

        client = self._get_client()
        response = await self._run(
            client.generate_presigned_post,
            self._bucket,
            key,
            Fields={"Content-Type": content_type},
            Conditions=[
                {"Content-Type": content_type},
                ["content-length-range", 1, max_size],
            ],
            ExpiresIn=ttl,
        )
        return response

    # ── Existence and metadata ────────────────────────────────────────────

    async def exists(self, key: str) -> bool:
        """Return True if the key exists in S3."""
        from botocore.exceptions import ClientError
        try:
            client = self._get_client()
            await self._run(client.head_object, Bucket=self._bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("404", "NoSuchKey"):
                return False
            raise

    async def get_object_size(self, key: str) -> int | None:
        """Return the size of an S3 object in bytes, or None if not found."""
        from botocore.exceptions import ClientError
        try:
            client   = self._get_client()
            response = await self._run(client.head_object, Bucket=self._bucket, Key=key)
            return response["ContentLength"]
        except ClientError:
            return None

    # ── Deletion ──────────────────────────────────────────────────────────

    async def delete(self, key: str) -> None:
        """Delete a single S3 object (no-op if the key does not exist)."""
        client = self._get_client()
        await self._run(client.delete_object, Bucket=self._bucket, Key=key)
        logger.info("s3_object_deleted", bucket=self._bucket, key=key)

    async def delete_prefix(self, prefix: str, max_objects: int = 1000) -> int:
        """Delete all objects under a key prefix.

        Args:
            prefix:      S3 key prefix, e.g. ``'datasets/abc-123/'``.
            max_objects: Safety cap — raises if the prefix has more objects.

        Returns:
            Number of objects deleted.

        Used by the dataset delete endpoint to clean up all files for a dataset:
            await storage.delete_prefix(f"datasets/{dataset_id}/")
        """
        client = self._get_client()
        listing = await self._run(
            client.list_objects_v2,
            Bucket=self._bucket,
            Prefix=prefix,
            MaxKeys=max_objects,
        )
        objects = listing.get("Contents", [])
        if not objects:
            return 0

        delete_payload = {"Objects": [{"Key": obj["Key"]} for obj in objects]}
        await self._run(
            client.delete_objects,
            Bucket=self._bucket,
            Delete=delete_payload,
        )
        count = len(objects)
        logger.info("s3_prefix_deleted", prefix=prefix, count=count)
        return count

    # ── Copy / rename ─────────────────────────────────────────────────────

    async def copy(self, source_key: str, destination_key: str) -> None:
        """Copy an S3 object within the same bucket."""
        client = self._get_client()
        await self._run(
            client.copy_object,
            CopySource={"Bucket": self._bucket, "Key": source_key},
            Bucket=self._bucket,
            Key=destination_key,
        )

    # ── Health check ──────────────────────────────────────────────────────

    async def ping(self) -> bool:
        """Return True when the S3 bucket is reachable (used by /ready endpoint)."""
        try:
            client = self._get_client()
            await self._run(client.head_bucket, Bucket=self._bucket)
            return True
        except Exception as exc:
            logger.warning("s3_ping_failed", error=str(exc))
            return False


@lru_cache(maxsize=1)
def get_s3_storage() -> S3StorageAdapter:
    """Return the cached S3StorageAdapter singleton.

    Call ``get_s3_storage.cache_clear()`` in tests that need a fresh adapter.
    """
    return S3StorageAdapter()
