"""005 — session disconnection model: disconnected status + NetworkGap table (E3-4)

Revision ID: 005
Revises: 003
Create Date: 2026-05-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "005"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extend sessionstatus enum — must run outside a transaction
    op.execute(sa.text("COMMIT"))
    op.execute(sa.text("ALTER TYPE sessionstatus ADD VALUE IF NOT EXISTS 'disconnected'"))
    op.execute(sa.text("BEGIN"))

    # New column on exam_sessions
    op.add_column(
        "exam_sessions",
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        schema="exam_svc",
    )

    # NetworkGap table
    op.create_table(
        "network_gaps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("exam_svc.exam_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "disconnected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("reconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("missed_heartbeat_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("auto_expired", sa.Boolean(), nullable=False, server_default="false"),
        schema="exam_svc",
    )
    op.create_index(
        "ix_network_gaps_session_id",
        "network_gaps",
        ["session_id"],
        schema="exam_svc",
    )


def downgrade() -> None:
    op.drop_index("ix_network_gaps_session_id", table_name="network_gaps", schema="exam_svc")
    op.drop_table("network_gaps", schema="exam_svc")
    op.drop_column("exam_sessions", "disconnected_at", schema="exam_svc")
    # Note: PostgreSQL does not support removing enum values — no downgrade for 'disconnected'
