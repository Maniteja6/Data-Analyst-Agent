"""LocalStorageAdapter — filesystem-backed storage for local development and tests.

A drop-in replacement for ``S3StorageAdapter`` when running DataPilot without
Docker or S3/MinIO. Files are stored in a configurable base directory
(default: ``/tmp/datapilot_storage``).

Differences from the S3 adapter:
- No authentication or credentials required
- Presigned URLs are ``file://`` URIs (frontend cannot use them; direct path used instead)
- ``delete_prefix`` does a recursive directory scan
- No multipart upload support — files are written atomically via ``shutil``

Switching between adapters is done in ``api/dependencies.py`` by checking
whether ``Settings.s3_endpoint_url`` is set to ``local://``:

    def _get_storage():
        if settings.s3_endpoint_url == "local://":
            return LocalStorageAdapter()
        return S3StorageAdapter()

Usage in tests::

    from backend.infrastructure.storage.local_storage_adapter import LocalStorageAdapter
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        storage = LocalStorageAdapter(base_path=tmp)
        key = await storage.upload_fileobj(io.BytesIO(b"csv,data"), "datasets/1/f.csv")
        assert await storage.exists(key)
        content = await storage.download_bytes(key)
        assert content == b"csv,data"
"""

from __future__ import annotations

import asyncio
import io
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, BinaryIO

import structlog

logger = structlog.get_logger(__name__)

DEFAULT_BASE_PATH = str(Path(tempfile.gettempdir()) / "datapilot_storage")


class LocalStorageAdapter:
    """Async local filesystem storage adapter.

    All methods mirror the ``S3StorageAdapter`` public interface so that
    either adapter can be substituted without changing application code.
    """

    def __init__(self, base_path: str = DEFAULT_BASE_PATH) -> None:
        """
        Args:
            base_path: Root directory for all stored files.
                       Created automatically if it does not exist.
        """
        self._base = Path(base_path)
        self._base.mkdir(parents=True, exist_ok=True)
        logger.debug("local_storage_initialised", base_path=str(self._base))

    # ── Internal helpers ──────────────────────────────────────────────────

    def _resolve(self, key: str) -> Path:
        """Resolve a storage key to an absolute filesystem path.

        Protects against path-traversal attacks by ensuring the resolved
        path is always under ``self._base``.

        Args:
            key: Storage key, e.g. ``'datasets/abc-123/sales.csv'``.

        Returns:
            Absolute ``Path`` under ``self._base``.

        Raises:
            ValueError: If the resolved path escapes ``self._base``.
        """
        resolved = (self._base / key).resolve()
        if not str(resolved).startswith(str(self._base.resolve())):
            raise ValueError(f"Path traversal detected for key: {key!r}")
        return resolved

    async def _run(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        """Run a blocking filesystem call in the default thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

    # ── Upload ────────────────────────────────────────────────────────────

    async def upload_fileobj(
        self,
        file_obj: BinaryIO,
        key: str,
        content_type: str | None = None,  # ignored in local adapter
    ) -> str:
        """Write a file-like object to the local filesystem.

        Creates parent directories automatically (mirrors S3 key hierarchy).
        """
        dest = self._resolve(key)

        def _write() -> int:
            dest.parent.mkdir(parents=True, exist_ok=True)
            data = file_obj.read()
            dest.write_bytes(data)
            return len(data)

        size = await self._run(_write)
        logger.debug("local_upload_complete", key=key, bytes_written=size)
        return key

    async def upload_bytes(
        self,
        data: bytes,
        key: str,
        content_type: str | None = None,
    ) -> str:
        """Write raw bytes to the local filesystem."""
        return await self.upload_fileobj(io.BytesIO(data), key, content_type)

    async def upload_from_path(
        self,
        local_path: str,
        key: str,
        content_type: str | None = None,
    ) -> str:
        """Copy a local file to the storage directory under the given key."""
        dest = self._resolve(key)

        def _copy() -> None:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local_path, dest)

        await self._run(_copy)
        return key

    # ── Download ──────────────────────────────────────────────────────────

    async def download_bytes(self, key: str) -> bytes:
        """Read a file and return its bytes."""
        path = self._resolve(key)
        if not path.exists():
            raise FileNotFoundError(f"Storage key not found: {key!r}")
        return await self._run(path.read_bytes)

    async def download_to_path(self, key: str, local_path: str) -> None:
        """Copy a stored file to ``local_path``."""
        src = self._resolve(key)
        if not src.exists():
            raise FileNotFoundError(f"Storage key not found: {key!r}")
        await self._run(shutil.copy2, str(src), local_path)

    # ── Presigned URLs (local file URIs) ──────────────────────────────────

    async def generate_presigned_download_url(
        self,
        key: str,
        ttl: int | None = None,  # ignored in local adapter — no expiry
    ) -> str:
        """Return a ``file://`` URI for the stored file.

        Note: ``file://`` URIs are not usable from a browser pointed at
        a remote server. In local development the frontend is expected to
        call ``GET /api/v1/datasets/<id>/file`` which streams the file
        through the API instead. This method exists solely to satisfy
        the adapter interface contract.
        """
        path = self._resolve(key)
        return f"file://{path}"

    async def generate_presigned_upload_url(
        self,
        key: str,
        content_type: str,
        ttl: int = 300,
    ) -> dict:
        """Return a stub upload URL — direct multipart upload not supported locally."""
        return {
            "url": f"http://localhost:8000/api/v1/uploads/local/{key}",
            "fields": {"key": key, "Content-Type": content_type},
        }

    # ── Existence and metadata ────────────────────────────────────────────

    async def exists(self, key: str) -> bool:
        """Return True if the key exists in the storage directory."""
        return self._resolve(key).exists()

    async def get_object_size(self, key: str) -> int | None:
        """Return the file size in bytes, or None if not found."""
        path = self._resolve(key)
        if not path.exists():
            return None
        stat = await self._run(path.stat)
        return stat.st_size

    # ── Deletion ──────────────────────────────────────────────────────────

    async def delete(self, key: str) -> None:
        """Delete a stored file (no-op if not found)."""
        path = self._resolve(key)

        def _delete() -> None:
            if path.exists():
                path.unlink()
                # Remove empty parent directories up to base_path
                parent = path.parent
                while parent != self._base and not any(parent.iterdir()):
                    parent.rmdir()
                    parent = parent.parent

        await self._run(_delete)
        logger.debug("local_object_deleted", key=key)

    async def delete_prefix(self, prefix: str, max_objects: int = 1000) -> int:
        """Delete all files under a path prefix.

        Args:
            prefix:      Key prefix, e.g. ``'datasets/abc-123/'``.
            max_objects: Safety cap — raises if more files are found.

        Returns:
            Number of files deleted.
        """
        base = self._resolve(prefix.rstrip("/"))
        if not base.exists():
            return 0

        def _collect() -> list[Path]:
            files = list(base.rglob("*"))
            return [f for f in files if f.is_file()]

        files = await self._run(_collect)
        if len(files) > max_objects:
            raise ValueError(
                f"delete_prefix: found {len(files)} files under '{prefix}', "
                f"exceeding safety cap of {max_objects}"
            )

        def _delete_all() -> int:
            count = 0
            for f in files:
                f.unlink(missing_ok=True)
                count += 1
            if base.exists():
                shutil.rmtree(base, ignore_errors=True)
            return count

        count = await self._run(_delete_all)
        logger.debug("local_prefix_deleted", prefix=prefix, count=count)
        return count

    async def copy(self, source_key: str, destination_key: str) -> None:
        """Copy a file within the storage directory."""
        src = self._resolve(source_key)
        dest = self._resolve(destination_key)

        def _copy() -> None:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)

        await self._run(_copy)

    # ── Health check ──────────────────────────────────────────────────────

    async def ping(self) -> bool:
        """Return True when the base directory is writable."""
        try:
            test_path = self._base / ".health_check"
            await self._run(test_path.touch)
            await self._run(test_path.unlink)
            return True
        except Exception as exc:
            logger.warning("local_storage_ping_failed", error=str(exc))
            return False

    # ── Test helpers ──────────────────────────────────────────────────────

    def list_keys(self, prefix: str = "") -> list[str]:
        """Return all stored keys under a prefix (relative to base_path).

        Useful in test assertions:
            keys = storage.list_keys("datasets/")
            assert "datasets/abc-123/sales.csv" in keys
        """
        base = (self._base / prefix) if prefix else self._base
        result = []
        for path in base.rglob("*"):
            if path.is_file():
                result.append(str(path.relative_to(self._base)))
        return sorted(result)

    def clear(self) -> None:
        """Delete all stored files — call between test cases."""
        if self._base.exists():
            shutil.rmtree(self._base)
        self._base.mkdir(parents=True, exist_ok=True)

    def file_count(self) -> int:
        """Return the total number of stored files."""
        return sum(1 for f in self._base.rglob("*") if f.is_file())
