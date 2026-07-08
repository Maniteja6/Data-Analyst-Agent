"""001 — create datasets and agent_executions tables.

Revision ID: 001
Revises:     (none — initial migration)
Create Date: 2024-11-01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── datasets ─────────────────────────────────────────────────────────
    op.create_table(
        "datasets",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("project_id", sa.String(36), nullable=True),
        sa.Column("original_name", sa.String(512), nullable=False),
        sa.Column("storage_key", sa.String(1024), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("mime_type", sa.String(256), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="uploaded"),
        sa.Column("row_count", sa.BigInteger(), nullable=True),
        sa.Column("column_count", sa.Integer(), nullable=True),
        sa.Column("checksum_sha256", sa.String(64), nullable=True),
        sa.Column("schema_json", postgresql.JSONB(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_datasets_status", "datasets", ["status"])
    op.create_index("ix_datasets_checksum", "datasets", ["checksum_sha256"])
    op.create_index("ix_datasets_project_deleted", "datasets", ["project_id", "deleted_at"])
    op.create_index(
        "ix_datasets_active",
        "datasets",
        ["status"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ── agent_executions ─────────────────────────────────────────────────
    op.create_table(
        "agent_executions",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=True),
        sa.Column("conversation_id", sa.String(36), nullable=True),
        sa.Column("task_id", sa.String(36), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("input_hash", sa.String(64), nullable=True),
        sa.Column("output_hash", sa.String(64), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("model_id", sa.String(128), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("llm_metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_executions_session", "agent_executions", ["session_id"])
    op.create_index("ix_agent_executions_agent", "agent_executions", ["agent_name"])
    op.create_index(
        "ix_agent_executions_input_hash", "agent_executions", ["agent_name", "input_hash"]
    )
    op.create_index(
        "ix_agent_executions_cache_lookup",
        "agent_executions",
        ["agent_name", "input_hash"],
        postgresql_where=sa.text("success = TRUE AND input_hash IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_table("agent_executions")
    op.drop_table("datasets")
