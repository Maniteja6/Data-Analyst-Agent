"""Dataset ORM model — maps the Dataset aggregate to the ``datasets`` table."""

from __future__ import annotations

from datetime import datetime

from backend.infrastructure.persistence.database import Base
from sqlalchemy import BigInteger, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class DatasetModel(Base):
    """SQLAlchemy ORM model for the ``datasets`` table.

    Stores Dataset aggregate state. Schema / cleaning / profiling results
    are stored as JSONB in ``schema_json`` rather than separate tables so
    the full Dataset state can be loaded in a single SELECT.

    Columns
    -------
    id               — UUID primary key (same as Dataset.id)
    project_id       — optional workspace project grouping (nullable)
    original_name    — user-supplied filename
    storage_key      — S3/MinIO object key
    size_bytes       — file size at upload
    mime_type        — detected MIME type
    status           — lifecycle state: uploaded|profiling|profiled|cleaning|ready|failed
    row_count        — populated after profiling (nullable until then)
    column_count     — populated after profiling (nullable until then)
    checksum_sha256  — SHA-256 of raw file bytes; used for deduplication
    schema_json      — JSONB column schema from Schema Agent
    error_message    — failure reason; non-null only when status=failed
    deleted_at       — soft-delete timestamp; NULL = not deleted
    created_at       — upload timestamp
    updated_at       — last status-change timestamp
    """

    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    original_name: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="uploaded")
    row_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    column_count: Mapped[int | None] = mapped_column(nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    schema_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # Fast lookup by status — used by the stale-job watchdog
        Index("ix_datasets_status", "status"),
        # Deduplication lookup
        Index("ix_datasets_checksum", "checksum_sha256"),
        # Project listing (all non-deleted datasets for a project)
        Index("ix_datasets_project_deleted", "project_id", "deleted_at"),
        # Partial index: only active (non-deleted) datasets
        Index(
            "ix_datasets_active",
            "status",
            postgresql_where="deleted_at IS NULL",
        ),
    )
