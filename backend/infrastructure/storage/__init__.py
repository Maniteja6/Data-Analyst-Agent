"""Storage adapters — S3 (production) and local filesystem (dev/tests).

S3StorageAdapter:     upload_fileobj, download_bytes, delete, exists,
                      generate_presigned_download_url (15-min TTL default).
                      All boto3 calls run in a dedicated ThreadPoolExecutor.
LocalStorageAdapter:  identical interface; base_path=/tmp/datapilot_storage/;
                      clear() removes all files (used in test fixtures).
"""

from backend.infrastructure.storage.local_storage_adapter import LocalStorageAdapter
from backend.infrastructure.storage.s3_storage_adapter import S3StorageAdapter

__all__ = ["S3StorageAdapter", "LocalStorageAdapter"]
