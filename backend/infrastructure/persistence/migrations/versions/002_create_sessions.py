"""002 — create analysis_sessions and insight_reports tables.

Revision ID: 002
Revises:     001
Create Date: 2024-11-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision      = "002"
down_revision = "001"
branch_labels = None
depends_on    = None


def upgrade() -> None:
    # ── analysis_sessions ─────────────────────────────────────────────────
    op.create_table(
        "analysis_sessions",
        sa.Column("id",                   sa.String(36),  primary_key=True, nullable=False),
        sa.Column("dataset_id",           sa.String(36),  sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("correlation_id",       sa.String(36),  nullable=False),
        sa.Column("status",               sa.String(32),  nullable=False, server_default="pending"),
        sa.Column("error_message",        sa.Text(),      nullable=True),
        sa.Column("profile_json",         postgresql.JSONB(), nullable=True),
        sa.Column("cleaning_report_json", postgresql.JSONB(), nullable=True),
        sa.Column("anomaly_ids",          postgresql.JSONB(), nullable=True),
        sa.Column("started_at",           sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at",         sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_sessions_dataset_id",      "analysis_sessions", ["dataset_id"])
    op.create_index("ix_sessions_status",           "analysis_sessions", ["status"])
    op.create_index("ix_sessions_dataset_status",  "analysis_sessions", ["dataset_id", "status"])

    # ── insight_reports ───────────────────────────────────────────────────
    op.create_table(
        "insight_reports",
        sa.Column("id",                  sa.String(36),   primary_key=True, nullable=False),
        sa.Column("session_id",          sa.String(36),   sa.ForeignKey("analysis_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset_id",          sa.String(36),   sa.ForeignKey("datasets.id",          ondelete="CASCADE"), nullable=False),
        sa.Column("executive_summary",   postgresql.JSONB(), nullable=True),
        sa.Column("report_json",         postgresql.JSONB(), nullable=True),
        sa.Column("insight_count",       sa.Integer(),    nullable=False, server_default="0"),
        sa.Column("has_forecasts",       sa.Boolean(),    nullable=False, server_default=sa.false()),
        sa.Column("is_critic_validated", sa.Boolean(),    nullable=False, server_default=sa.false()),
        sa.Column("report_pdf_key",      sa.String(1024), nullable=True),
        sa.Column("generated_at",        sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_insight_reports_dataset_id", "insight_reports", ["dataset_id"])
    op.create_index("ix_insight_reports_session_id", "insight_reports", ["session_id"])
    op.create_index(
        "ix_insight_reports_json_gin", "insight_reports", ["report_json"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_table("insight_reports")
    op.drop_table("analysis_sessions")
